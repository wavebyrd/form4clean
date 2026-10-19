from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from form4clean import InsiderData
from form4clean.api.app import create_app
from form4clean.cli import app as cli
from form4clean.config import Settings, save_settings
from form4clean.exports.writer import sha256
from form4clean.service import Form4Service
from tests.conftest import INDEX, FakeEdgar


def test_fetch_downloads_parses_and_stores(service: Form4Service, fake_edgar: FakeEdgar) -> None:
    summary = asyncio.run(service.fetch("EXRB", start=date(2015, 1, 1)))
    assert summary.company.cik == "0000999001"
    assert summary.listed == len(INDEX)
    assert summary.downloaded == len(INDEX)
    assert summary.parse_errors == []
    assert summary.download_errors == []
    agents = {r.headers["User-Agent"] for r in fake_edgar.requests}
    assert agents == {"Form4Clean tests@example.com"}


def test_refetch_only_downloads_new_filings(service: Form4Service, fake_edgar: FakeEdgar) -> None:
    asyncio.run(service.fetch("EXRB", start=date(2015, 1, 1)))
    before = len(fake_edgar.requests)
    again = asyncio.run(service.fetch("EXRB", start=date(2015, 1, 1)))
    assert again.already_stored == len(INDEX)
    assert again.downloaded == 0
    assert len(fake_edgar.requests) == before  # submissions JSON came from cache too


def test_transient_errors_are_retried(make_service: Callable[[FakeEdgar], Form4Service]) -> None:
    edgar = FakeEdgar()
    edgar.fail_once = {INDEX["f01_sale_10b5_1.xml"]["accession"]: 429}
    svc = make_service(edgar)
    summary = asyncio.run(svc.fetch("EXRB", start=date(2015, 1, 1)))
    assert summary.downloaded == len(INDEX)


def test_failed_download_is_reported_not_hidden(
    make_service: Callable[[FakeEdgar], Form4Service],
) -> None:
    edgar = FakeEdgar()
    svc = make_service(edgar)
    missing = INDEX["f02_option_exercise.xml"]["accession"]
    edgar.names = [n for n in INDEX if INDEX[n]["accession"] != missing]
    # The listing still includes it, but the document is gone.
    edgar_listing = FakeEdgar()

    def handler_listing_all(request):  # type: ignore[no-untyped-def]
        if str(request.url).endswith("CIK0000999001.json"):
            return edgar_listing(request)
        return edgar(request)

    import httpx

    svc._transport = httpx.MockTransport(handler_listing_all)
    summary = asyncio.run(svc.fetch("EXRB", start=date(2015, 1, 1)))
    assert [a for a, _ in summary.download_errors] == [missing]
    assert summary.downloaded == len(INDEX) - 1


def test_stored_dataset_matches_pipeline(loaded_service: Form4Service) -> None:
    company = loaded_service.require_company("EXRB")
    df, report = loaded_service.transactions(company)
    assert report is not None
    assert df.height == report.current_transactions
    raw = loaded_service.raw_transactions(company)
    assert raw.height == report.transactions_extracted
    assert raw["shares"].to_list().count("6,800") == 1  # raw keeps the source string


def test_export_bundle(loaded_service: Form4Service, tmp_path: Path) -> None:
    company = loaded_service.require_company("EXRB")
    manifest, path = loaded_service.export_bundle(company, tmp_path, "parquet")
    data = json.loads(path.read_text("utf-8"))
    assert data["schema_version"] == "1.0.0"
    assert data["record_count"] == manifest.record_count
    assert {f["dataset"] for f in data["files"]} == {"clean", "raw", "quality_report"}
    for f in data["files"]:
        assert sha256(tmp_path / f["path"]) == f["sha256"]
    assert data["amendment_policy"].startswith("current")
    assert data["filing_date_range"][0] is not None
    # Same data exported twice: identical files.
    manifest2, _ = loaded_service.export_bundle(company, tmp_path / "again", "parquet")
    assert [f.sha256 for f in manifest.files] == [f.sha256 for f in manifest2.files]


def test_python_api(settings: Settings, loaded_service: Form4Service, tmp_path: Path) -> None:
    data = InsiderData("EXRB", service=loaded_service, auto_fetch=False)
    tx = data.transactions(
        start="2025-01-01", end="2026-01-01", clean=True, reconcile_amendments=True
    )
    df = tx.to_pandas()
    assert len(df) == len(tx) > 0
    assert isinstance(df["transaction_value"].dropna().iloc[0], Decimal)
    out = tx.to_parquet(tmp_path / "exrb.parquet")
    assert pl.read_parquet(out).height == len(tx)
    assert (tmp_path / "exrb.manifest.json").exists()

    sales = data.transactions(transaction_types=["Market Sale"], roles=["CEO"], min_value=50_000)
    assert len(sales) > 0
    assert all(r["insider_role"] == "CEO" for r in sales)

    raw = data.transactions(clean=False)
    assert raw.kind == "raw"
    assert "transaction_code" in raw.to_polars().columns

    past = data.transactions(as_of="2025-04-20")
    assert all(r["filing_timestamp"].date() <= date(2025, 4, 20) for r in past)

    unreconciled = data.transactions(reconcile_amendments=False)
    assert len(unreconciled) > len(data.transactions())


def test_python_api_auto_fetch(
    settings: Settings, make_service: Callable[[FakeEdgar], Form4Service]
) -> None:
    svc = make_service(FakeEdgar())
    tx = InsiderData("EXRB", service=svc).transactions(start="2015-01-01")
    assert len(tx) > 0


def test_cli(
    settings: Settings,
    loaded_service: Form4Service,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORM4CLEAN_HOME", str(settings.home))
    monkeypatch.setenv("COLUMNS", "200")
    save_settings(settings)
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "export" in result.output

    result = runner.invoke(cli, ["transactions", "EXRB", "--role", "CEO"])
    assert result.exit_code == 0, result.output
    assert "Jane A Doe" in result.output

    result = runner.invoke(cli, ["quality", "EXRB"])
    assert result.exit_code == 0, result.output
    assert "Transactions extracted" in result.output

    result = runner.invoke(cli, ["quality", "EXRB", "--json"])
    assert json.loads(result.output)["company_cik"] == "0000999001"

    out = tmp_path / "exports"
    result = runner.invoke(
        cli, ["export", "EXRB", "--format", "csv", "-o", str(out), "--as-of", "2025-05-01"]
    )
    assert result.exit_code == 0, result.output
    assert (out / "EXRB" / "exrb_transactions_asof_2025-05-01.csv").exists()

    result = runner.invoke(cli, ["clean", "EXRB"])
    assert result.exit_code == 0

    result = runner.invoke(cli, ["transactions", "NOPE"])
    assert result.exit_code == 1
    assert "form4clean fetch NOPE" in result.output

    result = runner.invoke(cli, ["export", "EXRB", "--format", "xlsx"])
    assert result.exit_code == 1
    assert "Unknown format" in result.output


def test_http_api(loaded_service: Form4Service) -> None:
    client = TestClient(create_app(loaded_service))
    assert client.get("/api/health").json()["schema_version"] == "1.0.0"
    assert client.get("/api/companies").json()[0]["ticker"] == "EXRB"

    r = client.get(
        "/api/companies/EXRB/transactions",
        params={"roles": ["CEO", "CFO"], "categories": "Market Sale", "min_value": "100000"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 4
    assert all(rec["insider_role"] in ("CEO", "CFO") for rec in body["records"])
    assert isinstance(body["records"][0]["transaction_value"], str)  # exact decimal

    tid = body["records"][0]["transaction_id"]
    detail = client.get(f"/api/companies/EXRB/transactions/{tid}").json()
    assert detail["record"]["source_values"]["filing"]["accession_number"]
    assert isinstance(detail["cleaning_log"], list)

    quality = client.get("/api/companies/EXRB/quality").json()
    assert quality["report"]["amendments"]["ambiguous"] == 1
    assert len(quality["amendment_links"]) == 4

    flagged = client.get(
        "/api/companies/EXRB/transactions",
        params={"flags": "AMENDMENT_AMBIGUOUS", "include_superseded": True},
    )
    assert flagged.json()["count"] == 1

    overview = client.get("/api/companies/EXRB/overview").json()["overview"]
    assert "sales" in overview

    prices = client.get("/api/companies/EXRB/prices").json()
    assert prices["status"] == "unavailable"
    assert prices["bars"] == []

    export = client.get("/api/companies/EXRB/export", params={"format": "csv", "codes": "S"})
    assert export.status_code == 200
    assert "exrb_transactions.csv" in export.headers["content-disposition"]

    assert client.get("/api/companies/NOPE/transactions").status_code == 404
    assert (
        client.get("/api/companies/EXRB/transactions", params={"as_of": "yesterday"}).status_code
        == 400
    )
    assert client.get("/api/jobs/missing").status_code == 404


def test_http_fetch_job(service: Form4Service) -> None:
    import time

    with TestClient(create_app(service)) as client:
        job = client.post("/api/companies/EXRB/fetch", json={"start": "2015-01-01"}).json()
        status: dict[str, object] = {}
        for _ in range(100):
            status = client.get(f"/api/jobs/{job['job_id']}").json()
            if status["state"] != "running":
                break
            time.sleep(0.05)
        assert status["state"] == "done", status
        assert status["summary"]["downloaded"] == len(INDEX)  # type: ignore[index]


def test_settings_endpoint(service: Form4Service) -> None:
    client = TestClient(create_app(service))
    updated = client.put("/api/settings", json={"price_provider": "csv"}).json()
    assert updated["price_provider"] == "csv"
    assert client.put("/api/settings", json={"price_provider": "nope"}).status_code == 400
    assert client.put("/api/settings", json={"contact_email": "bad"}).status_code == 400
