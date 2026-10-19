"""Optional tests against the real SEC EDGAR. Skipped by default.

Run with:  FORM4CLEAN_SEC_EMAIL=you@example.com pytest -m live
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from form4clean.config import load_settings
from form4clean.service import Form4Service

pytestmark = pytest.mark.live


@pytest.fixture
def live_service(tmp_path: Path) -> Form4Service:
    email = os.environ.get("FORM4CLEAN_SEC_EMAIL")
    if not email:
        pytest.skip("set FORM4CLEAN_SEC_EMAIL to run live tests")
    return Form4Service(load_settings(tmp_path, contact_email=email))


def test_recent_filings_parse_and_clean(live_service: Form4Service) -> None:
    summary = asyncio.run(live_service.fetch("MSFT", start=date.today() - timedelta(days=120)))
    assert summary.parse_errors == []
    result = live_service.clean(summary.company)
    assert result.report.classification_coverage > 0.99
    for record in result.transactions:
        assert record.filing_timestamp is not None
