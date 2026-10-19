"""Write datasets to CSV, Parquet and JSON with a manifest.

Data files are byte-for-byte reproducible: rows are sorted deterministically, no timestamps are
written into them, and Parquet metadata carries only the schema and cleaning versions. The
generation time lives in the manifest, next to each file's SHA-256 so anyone can check the
data has not changed.

Decimal amounts are written as exact decimals in Parquet and as decimal strings in CSV and JSON,
never as floating point. CSV cannot hold lists, so list columns are JSON-encoded there.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel

from .. import __version__
from ..models.schema import flatten_nested
from ..versions import CLEANING_VERSION, SCHEMA_VERSION

Format = Literal["csv", "parquet", "json"]
FORMATS: tuple[Format, ...] = ("csv", "parquet", "json")
SOURCE = "U.S. SEC EDGAR, Forms 4 and 4/A ownership XML (https://www.sec.gov/edgar)"


class ManifestFile(BaseModel):
    path: str
    dataset: str
    format: str
    record_count: int | None
    sha256: str
    bytes: int


class DatasetManifest(BaseModel):
    form4clean_version: str = __version__
    schema_version: str = SCHEMA_VERSION
    cleaning_version: str = CLEANING_VERSION
    generation_timestamp: str
    source: str = SOURCE
    company: dict[str, Any]
    filing_date_range: tuple[str | None, str | None]
    amendment_policy: str
    filters: dict[str, Any]
    record_count: int
    quality_summary: dict[str, Any]
    files: list[ManifestFile]
    columns: list[str]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_frame(df: pl.DataFrame, path: Path, fmt: Format) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "parquet":
        df.write_parquet(
            path,
            compression="zstd",
            metadata={
                "form4clean.schema_version": SCHEMA_VERSION,
                "form4clean.cleaning_version": CLEANING_VERSION,
            },
        )
    elif fmt == "csv":
        flatten_nested(df).write_csv(path)
    elif fmt == "json":
        path.write_text(df.write_json() + "\n", encoding="utf-8")
    else:
        raise ValueError(f"Unsupported format {fmt!r}. Use one of: {', '.join(FORMATS)}.")
    return path


def write_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return path


def manifest_file(
    path: Path, root: Path, dataset: str, fmt: str, records: int | None
) -> ManifestFile:
    return ManifestFile(
        path=path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path),
        dataset=dataset,
        format=fmt,
        record_count=records,
        sha256=sha256(path),
        bytes=path.stat().st_size,
    )


def build_manifest(
    *,
    company: dict[str, Any],
    clean: pl.DataFrame,
    files: list[ManifestFile],
    amendment_policy: str,
    filters: dict[str, Any],
    quality_summary: dict[str, Any],
) -> DatasetManifest:
    dates = clean.get_column("filing_date").drop_nulls() if clean.height else pl.Series([])
    return DatasetManifest(
        generation_timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        company=company,
        filing_date_range=(
            str(dates.min()) if dates.len() else None,
            str(dates.max()) if dates.len() else None,
        ),
        amendment_policy=amendment_policy,
        filters=filters,
        record_count=clean.height,
        quality_summary=quality_summary,
        files=files,
        columns=clean.columns,
    )


def amendment_policy(*, reconciled: bool, include_superseded: bool, as_of: datetime | None) -> str:
    if not reconciled:
        return (
            "not reconciled: every record from every original and amended filing is "
            "included as filed"
        )
    base = (
        (
            "point-in-time as of " + as_of.isoformat() + ": only filings public by then, "
            "reconciled with the amendments public by then"
        )
        if as_of
        else "current"
    )
    if include_superseded:
        return base + "; superseded and ambiguous records included (see is_current)"
    return base + "; superseded and ambiguous amendment records excluded"
