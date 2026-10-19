from __future__ import annotations

from form4clean.cleaning.pipeline import clean
from tests.conftest import COMPANY, INDEX, parsed


def test_duplicate_ingestion_is_ignored_and_logged() -> None:
    filing = parsed("f01_sale_10b5_1.xml")
    res = clean([filing, filing, filing], COMPANY)
    assert len(res.transactions) == 2
    assert res.report.duplicate_filings_ignored == 2
    assert sum(1 for d in res.decisions if d.step == "deduplicate") == 2


def test_identical_rows_in_one_filing_are_kept_and_flagged() -> None:
    res = clean([parsed("f03_edge_cases.xml")], COMPANY)
    gifts = [r for r in res.transactions if r.transaction_code == "G"]
    assert len(gifts) == 2
    for g in gifts:
        assert "POSSIBLE_DUPLICATE_IN_FILING" in g.quality_flags
    assert gifts[0].related_transaction_ids == [gifts[1].transaction_id]


def test_same_trade_reported_in_separate_filings() -> None:
    res = clean([parsed("f04_joint_filing.xml"), parsed("f04b_joint_separate.xml")], COMPANY)
    a, b = res.transactions
    for r in (a, b):
        assert "POSSIBLE_DUPLICATE_ACROSS_FILINGS" in r.quality_flags
        assert r.is_current  # kept; the user decides
    assert a.related_transaction_ids == [b.transaction_id]
    assert res.report.duplicates_detected == 2


def test_equal_awards_to_different_insiders_are_not_duplicates() -> None:
    first = parsed("f08a_cfo_first.xml")
    other = first.model_copy(
        update={
            "accession_number": "0000999107-25-000001",
            "reporting_owners": [
                o.model_copy(update={"cik": "0000999107", "name": "LEE SAM"})
                for o in first.reporting_owners
            ],
            "transactions": [
                t.model_copy(update={"shares_owned_after": "91000"}) for t in first.transactions
            ],
        }
    )
    res = clean([first, other], COMPANY)
    assert all("POSSIBLE_DUPLICATE_ACROSS_FILINGS" not in r.quality_flags for r in res.transactions)


def test_identical_direct_holdings_of_different_insiders_are_not_duplicates() -> None:
    # Co-founders with identical grant schedules file identical rows, holdings included.
    first = parsed("f08a_cfo_first.xml")
    other = first.model_copy(
        update={
            "accession_number": "0000999107-25-000001",
            "reporting_owners": [
                o.model_copy(update={"cik": "0000999107", "name": "LEE SAM"})
                for o in first.reporting_owners
            ],
        }
    )
    res = clean([first, other], COMPANY)
    assert {r.ownership_type for r in res.transactions} == {"Direct"}
    assert all("POSSIBLE_DUPLICATE_ACROSS_FILINGS" not in r.quality_flags for r in res.transactions)


def test_same_insider_filing_a_trade_twice_is_flagged() -> None:
    first = parsed("f08a_cfo_first.xml")
    again = first.model_copy(update={"accession_number": "0000999107-25-000002"})
    res = clean([first, again], COMPANY)
    flagged = [
        r for r in res.transactions if "POSSIBLE_DUPLICATE_ACROSS_FILINGS" in r.quality_flags
    ]
    assert len(flagged) == 2 * len(first.transactions)


def test_all_fixture_accessions_are_unique() -> None:
    accessions = [m["accession"] for m in INDEX.values()]
    assert len(accessions) == len(set(accessions))
