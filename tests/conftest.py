"""Shared fixtures.

Filings in tests/fixtures/filings are realistic ownership XML for a fictional issuer, Example
Robotics Inc. (CIK 0000999001, ticker EXRB). ``index.json`` gives each one an accession number,
form type, filing date and acceptance timestamp. ``sec_transport`` serves them from a fake EDGAR,
so no test touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from form4clean.cleaning.records import CompanyInfo
from form4clean.config import Settings
from form4clean.models.raw import ParsedFiling
from form4clean.parsing.ownership import parse_ownership_xml
from form4clean.service import Form4Service

FIXTURES = Path(__file__).parent / "fixtures"
FILINGS = FIXTURES / "filings"
INDEX: dict[str, dict[str, str]] = json.loads((FILINGS / "index.json").read_text("utf-8"))
COMPANY = CompanyInfo(cik="0000999001", ticker="EXRB", name="EXAMPLE ROBOTICS INC")
CIK = "0000999001"


def header(name: str) -> dict[str, str]:
    meta = INDEX[name]
    return {
        "accession_number": meta["accession"],
        "form_type": meta["form"],
        "filed_as_of_date": meta["filed"],
        "acceptance_datetime": meta["accepted"],
    }


def parsed(name: str) -> ParsedFiling:
    meta = INDEX[name]
    return parse_ownership_xml(
        (FILINGS / name).read_text("utf-8"),
        accession_number=meta["accession"],
        form_type=meta["form"],
        header=header(name),
        source_document=name,
    )


def all_parsed() -> list[ParsedFiling]:
    return [parsed(name) for name in INDEX]


def submission_text(name: str) -> str:
    meta = INDEX[name]
    xml = (FILINGS / name).read_text("utf-8").strip()
    return (
        f"<SEC-DOCUMENT>{meta['accession']}.txt : {meta['filed']}\n"
        f"<SEC-HEADER>{meta['accession']}.hdr.sgml : {meta['filed']}\n"
        f"<ACCEPTANCE-DATETIME>{meta['accepted']}\n"
        f"ACCESSION NUMBER:\t\t{meta['accession']}\n"
        f"CONFORMED SUBMISSION TYPE:\t{meta['form']}\n"
        f"FILED AS OF DATE:\t\t{meta['filed']}\n"
        "</SEC-HEADER>\n<DOCUMENT>\n"
        f"<TYPE>{meta['form']}\n<SEQUENCE>1\n<FILENAME>{name}\n<TEXT>\n<XML>\n{xml}\n</XML>\n"
        "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    )


def submissions_json(names: list[str] | None = None) -> dict[str, Any]:
    names = names if names is not None else list(INDEX)
    metas = sorted((INDEX[n] | {"name": n} for n in names), key=lambda m: m["filed"], reverse=True)

    def iso(d: str) -> str:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"

    return {
        "cik": "999001",
        "name": "EXAMPLE ROBOTICS INC",
        "tickers": ["EXRB"],
        "filings": {
            "recent": {
                "accessionNumber": [m["accession"] for m in metas] + ["0000999001-25-000099"],
                "filingDate": [iso(m["filed"]) for m in metas] + ["2025-02-20"],
                "reportDate": ["" for _ in metas] + ["2024-12-31"],
                # EDGAR lists acceptance times with a misleading "Z" suffix; the parser must
                # use the filing header instead, so these values are deliberately wrong.
                "acceptanceDateTime": ["2000-01-01T00:00:00.000Z" for _ in metas]
                + ["2025-02-20T21:00:00.000Z"],
                "form": [m["form"] for m in metas] + ["10-K"],
                "primaryDocument": [f"xslF345X05/{m['name']}" for m in metas] + ["exrb-10k.htm"],
            },
            "files": [],
        },
    }


TICKERS = {
    "0": {"cik_str": 999001, "ticker": "EXRB", "title": "EXAMPLE ROBOTICS INC"},
    "1": {"cik_str": 999002, "ticker": "OTHR", "title": "OTHER EXAMPLE CORP"},
}


class FakeEdgar:
    """A minimal EDGAR: ticker file, submissions JSON and full-text submissions."""

    def __init__(self, names: list[str] | None = None) -> None:
        self.names = names if names is not None else list(INDEX)
        self.requests: list[httpx.Request] = []
        self.fail_once: dict[str, int] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        for fragment, status in list(self.fail_once.items()):
            if fragment in url:
                del self.fail_once[fragment]
                return httpx.Response(status, headers={"Retry-After": "0"})
        if url.endswith("company_tickers.json"):
            return httpx.Response(200, json=TICKERS)
        if url.endswith(f"CIK{CIK}.json"):
            return httpx.Response(200, json=submissions_json(self.names))
        for name in self.names:
            if url.endswith(f"{INDEX[name]['accession']}.txt"):
                return httpx.Response(200, text=submission_text(name))
        return httpx.Response(404)


@pytest.fixture
def fake_edgar() -> FakeEdgar:
    return FakeEdgar()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        home=tmp_path / "home",
        contact_email="tests@example.com",
        requests_per_second=10,
        max_retries=2,
    )


@pytest.fixture
def make_service(settings: Settings) -> Callable[[FakeEdgar], Form4Service]:
    def build(edgar: FakeEdgar) -> Form4Service:
        return Form4Service(settings, transport=httpx.MockTransport(edgar))

    return build


@pytest.fixture
def service(
    make_service: Callable[[FakeEdgar], Form4Service], fake_edgar: FakeEdgar
) -> Form4Service:
    return make_service(fake_edgar)


@pytest.fixture
def loaded_service(service: Form4Service) -> Form4Service:
    import asyncio

    summary = asyncio.run(service.fetch("EXRB", start=date(2015, 1, 1)))
    service.clean(summary.company)
    return service
