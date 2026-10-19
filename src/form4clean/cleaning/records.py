"""Turn one parsed source row into one standardized record.

The record is built field by field from the source strings. Every change to a value is logged
as a CleaningDecision, and every problem is attached as a quality flag. Nothing is dropped and
nothing is filled in.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from ..calendar import EASTERN, business_days_between, disclosure
from ..classification.classify import classify
from ..models.enums import AmendmentStatus, QualityStatus
from ..models.raw import ParsedFiling, ParsedTransaction
from ..models.transaction import FootnoteRef, InsiderTransaction, OwnerRef
from ..validation.flags import FLAGS
from ..versions import CLEANING_VERSION, SCHEMA_VERSION
from . import normalize as n

# Latest acceptance time that still receives the same filing date (EDGAR rule). Used as the
# conservative "public by" time when a filing has no acceptance timestamp.
FILING_DATE_CUTOFF = time(17, 30)
_WEIGHTED = re.compile(r"weighted[-\s]average", re.IGNORECASE)


@dataclass(frozen=True)
class CompanyInfo:
    cik: str
    ticker: str | None
    name: str | None = None


@dataclass
class CleaningDecision:
    accession_number: str
    transaction_id: str | None
    step: str
    field: str | None
    rule: str
    before: str | None = None
    after: str | None = None


@dataclass
class Draft:
    record: InsiderTransaction
    flags: list[tuple[str, str | None]] = field(default_factory=list)
    economic_key: tuple[Any, ...] = ()

    def flag(self, code: str, detail: str | None = None) -> None:
        if code not in FLAGS:
            raise KeyError(f"unknown quality flag {code}")
        if all(existing != code for existing, _ in self.flags):
            self.flags.append((code, detail))

    def finalize(self) -> InsiderTransaction:
        status = QualityStatus.VALID
        codes: list[str] = []
        explanations: list[str] = []
        for code, detail in self.flags:
            definition = FLAGS[code]
            codes.append(code)
            explanations.append(f"{definition.title}. {detail}" if detail else definition.title)
            candidate = definition.severity.to_status()
            if candidate.rank > status.rank:
                status = candidate
        rec = self.record
        rec.quality_flags = codes
        rec.quality_explanations = explanations
        rec.quality_status = status
        return rec


def transaction_id(source_transaction_id: str) -> str:
    return "f4c_" + hashlib.sha256(source_transaction_id.encode("utf-8")).hexdigest()[:20]


def source_id(accession: str, tx: ParsedTransaction) -> str:
    return f"{accession}:{'ND' if tx.table == 'non_derivative' else 'D'}:{tx.sequence}"


def public_time(filing: ParsedFiling) -> datetime | None:
    """When the filing became public: its acceptance time, or end of the filing date's window."""
    accepted, _ = n.parse_acceptance(filing.acceptance_datetime)
    if accepted is not None:
        return accepted
    filed, _ = n.parse_date(filing.filing_date)
    if filed is None:
        return None
    return datetime.combine(filed, FILING_DATE_CUTOFF, tzinfo=EASTERN)


class RecordBuilder:
    def __init__(self, company: CompanyInfo, log: list[CleaningDecision]) -> None:
        self.company = company
        self.log = log

    def _note(
        self, acc: str, tid: str, step: str, fld: str, rule: str, before: object, after: object
    ) -> None:
        b = None if before is None else str(before)
        a = None if after is None else str(after)
        if b != a:
            self.log.append(CleaningDecision(acc, tid, step, fld, rule, b, a))

    def _number(
        self, d: Draft, acc: str, tid: str, fld: str, raw: str | None, invalid_flag: str
    ) -> Decimal | None:
        value, error = n.parse_decimal(raw)
        if error:
            d.flag(invalid_flag, f"{fld}: {error}")
        elif value is not None:
            if value < 0:
                d.flag("NEGATIVE_AMOUNT", f"{fld} is {raw}")
            self._note(
                acc,
                tid,
                "normalize",
                fld,
                "parsed as exact decimal",
                raw.strip() if raw else raw,
                format(value, "f"),
            )
        return value

    def _date(
        self,
        d: Draft,
        acc: str,
        tid: str,
        fld: str,
        raw: str | None,
        invalid_flag: str | None = None,
    ) -> date | None:
        value, error = n.parse_date(raw)
        if error:
            if invalid_flag:
                d.flag(invalid_flag, error)
            else:
                d.flag("INVALID_NUMBER", f"{fld}: {error}")
        elif value is not None:
            self._note(acc, tid, "normalize", fld, "parsed as ISO date", raw, value.isoformat())
        return value

    def build(self, filing: ParsedFiling, tx: ParsedTransaction) -> Draft:
        acc = filing.accession_number
        sid = source_id(acc, tx)
        tid = transaction_id(sid)
        notes = [
            filing.footnotes[fid]
            for ids in tx.footnote_ids.values()
            for fid in ids
            if fid in filing.footnotes
        ]
        cls = classify(
            tx.transaction_code,
            table=tx.table,
            acquired_disposed=tx.acquired_disposed_code,
            footnotes=notes,
            aff_10b5_one=filing.aff_10b5_one,
        )
        owner = filing.reporting_owners[0] if filing.reporting_owners else None
        owners = [
            OwnerRef(cik=n.normalize_cik(o.cik)[0] or o.cik, name=o.name)
            for o in filing.reporting_owners
        ]
        filed, _ = n.parse_date(filing.filing_date)
        accepted, _ = n.parse_acceptance(filing.acceptance_datetime)
        timing, session = disclosure(accepted)

        placeholder = InsiderTransaction(
            transaction_id=tid,
            source_transaction_id=sid,
            accession_number=acc,
            form_type=filing.form_type,
            transaction_table=tx.table,
            sequence=tx.sequence,
            company_cik=self.company.cik,
            ticker=self.company.ticker,
            company_name=filing.issuer_name or self.company.name,
            issuer_trading_symbol=filing.issuer_trading_symbol,
            insider_cik=None,
            insider_name=None,
            insider_name_raw=owner.name if owner else None,
            insider_role="Unknown",
            is_director=None,
            is_officer=None,
            is_ten_percent_owner=None,
            is_other_reporting_owner=None,
            officer_title=None,
            other_relationship_text=None,
            reporting_owners=owners,
            reporting_owner_count=len(owners),
            transaction_date=None,
            deemed_execution_date=None,
            filing_date=filed,
            filing_timestamp=accepted,
            disclosure_timing=timing,
            disclosure_session_date=session,
            days_to_file=None,
            transaction_code=tx.transaction_code,
            transaction_type=cls.transaction_type,
            transaction_category=cls.category,
            transaction_direction=cls.direction,
            acquired_disposed_code=tx.acquired_disposed_code,
            equity_swap_involved=n.parse_bool(tx.equity_swap_involved),
            shares=None,
            price_per_share=None,
            transaction_value=None,
            shares_owned_after=None,
            security_title=None,
            security_title_raw=tx.security_title,
            is_derivative=tx.table == "derivative",
            underlying_security_title=None,
            underlying_shares=None,
            exercise_price=None,
            exercise_date=None,
            expiration_date=None,
            ownership_type=None,
            ownership_nature=tx.nature_of_ownership,
            is_market_transaction=cls.is_market_transaction,
            is_discretionary_trade=cls.is_discretionary_trade,
            is_10b5_1=cls.is_10b5_1,
            is_10b5_1_source=cls.is_10b5_1_source,
            classification_confidence=cls.confidence,
            classification_reason=cls.reason,
            is_amended=filing.is_amendment,
            amendment_status=AmendmentStatus.ORIGINAL,
            amends_accession_number=None,
            superseded_by=None,
            is_current=True,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            quality_explanations=[],
            footnotes=[],
            related_transaction_ids=[],
            sec_filing_url=filing.sec_filing_url,
            source_document=filing.source_document,
            source_values=_source_values(filing, tx),
            cleaning_version=CLEANING_VERSION,
            schema_version=SCHEMA_VERSION,
        )
        d = Draft(placeholder)
        r = d.record

        # Insider
        if owner is not None:
            cik, err = n.normalize_cik(owner.cik)
            if err:
                d.flag("INVALID_INSIDER_CIK", err)
            elif cik is None:
                d.flag("MISSING_INSIDER_CIK")
            r.insider_cik = cik
            name, rule = n.normalize_person_or_entity(owner.name)
            r.insider_name = name
            if rule:
                self._note(acc, tid, "normalize", "insider_name", rule, owner.name, name)
            r.is_director = n.parse_bool(owner.is_director)
            r.is_officer = n.parse_bool(owner.is_officer)
            r.is_ten_percent_owner = n.parse_bool(owner.is_ten_percent_owner)
            r.is_other_reporting_owner = n.parse_bool(owner.is_other)
            r.officer_title = owner.officer_title
            r.other_relationship_text = owner.other_text
            r.insider_role = n.standard_role(
                is_officer=r.is_officer,
                is_director=r.is_director,
                is_ten_percent=r.is_ten_percent_owner,
                is_other=r.is_other_reporting_owner,
                officer_title=owner.officer_title,
                other_text=owner.other_text,
            )
            self._note(
                acc,
                tid,
                "classify",
                "insider_role",
                "standardized from relationship boxes and officer title",
                owner.officer_title,
                r.insider_role,
            )
        else:
            d.flag("MISSING_INSIDER_CIK", "The filing lists no reporting owner.")
        if len(owners) > 1:
            d.flag("MULTIPLE_REPORTING_OWNERS", f"{len(owners)} owners on this filing.")

        # Classification
        if tx.transaction_code is None:
            d.flag("MISSING_TRANSACTION_CODE")
        elif cls.unknown_code:
            d.flag("UNRECOGNIZED_TRANSACTION_CODE", f"Code {tx.transaction_code!r}.")
        if cls.direction_mismatch:
            d.flag("DIRECTION_CODE_MISMATCH", cls.direction_mismatch)
        if tx.acquired_disposed_code is None:
            d.flag("MISSING_ACQUIRED_DISPOSED")

        # Dates
        r.transaction_date = self._date(
            d, acc, tid, "transaction_date", tx.transaction_date, "INVALID_TRANSACTION_DATE"
        )
        if tx.transaction_date is None:
            d.flag("MISSING_TRANSACTION_DATE")
        r.deemed_execution_date = self._date(
            d, acc, tid, "deemed_execution_date", tx.deemed_execution_date
        )
        r.exercise_date = self._date(d, acc, tid, "exercise_date", tx.exercise_date)
        r.expiration_date = self._date(d, acc, tid, "expiration_date", tx.expiration_date)
        if accepted is None:
            d.flag("MISSING_FILING_TIMESTAMP")
        if r.transaction_date and filed:
            r.days_to_file = (filed - r.transaction_date).days
            if r.transaction_date > filed:
                d.flag("TRANSACTION_AFTER_FILING", f"Traded {r.transaction_date}, filed {filed}.")
            elif not filing.is_amendment and business_days_between(r.transaction_date, filed) > 2:
                d.flag("LATE_FILING", f"{r.days_to_file} calendar days after the transaction.")

        # Amounts
        r.shares = self._number(d, acc, tid, "shares", tx.shares, "INVALID_SHARES")
        if tx.shares is None:
            if tx.total_value is not None:
                d.flag("VALUE_REPORTED_INSTEAD_OF_SHARES", f"Total value {tx.total_value}.")
            else:
                d.flag("MISSING_SHARES")
        r.price_per_share = self._number(
            d, acc, tid, "price_per_share", tx.price_per_share, "INVALID_PRICE"
        )
        r.shares_owned_after = self._number(
            d, acc, tid, "shares_owned_after", tx.shares_owned_after, "INVALID_NUMBER"
        )
        r.underlying_shares = self._number(
            d, acc, tid, "underlying_shares", tx.underlying_shares, "INVALID_NUMBER"
        )
        r.exercise_price = self._number(
            d, acc, tid, "exercise_price", tx.conversion_or_exercise_price, "INVALID_NUMBER"
        )
        code = (tx.transaction_code or "").strip().upper()
        trade = code in ("P", "S")
        if r.price_per_share is None and tx.price_per_share is None:
            d.flag("MISSING_PRICE" if trade else "MISSING_PRICE_NON_TRADE")
        elif r.price_per_share is not None and r.price_per_share == 0:
            d.flag("ZERO_PRICE_TRADE" if trade else "ZERO_PRICE")
        if r.shares is not None and r.price_per_share is not None and r.price_per_share > 0:
            r.transaction_value = n.money(r.shares, r.price_per_share)
            self._note(
                acc,
                tid,
                "derive",
                "transaction_value",
                "shares x price, rounded half-up to cents",
                None,
                format(r.transaction_value, "f"),
            )
        price_notes = [
            filing.footnotes.get(f, "") for f in tx.footnote_ids.get("price_per_share", [])
        ]
        if any(_WEIGHTED.search(t) for t in price_notes):
            d.flag("WEIGHTED_AVERAGE_PRICE")

        # Security
        title, rules = n.normalize_security_title(tx.security_title)
        r.security_title = title
        for rule in rules:
            self._note(acc, tid, "normalize", "security_title", rule, tx.security_title, title)
        underlying, urules = n.normalize_security_title(tx.underlying_security_title)
        r.underlying_security_title = underlying
        for rule in urules:
            self._note(
                acc,
                tid,
                "normalize",
                "underlying_security_title",
                rule,
                tx.underlying_security_title,
                underlying,
            )

        # Ownership
        di = (tx.direct_or_indirect or "").strip().upper()
        if not di:
            d.flag("MISSING_OWNERSHIP_TYPE")
        elif di not in ("D", "I"):
            d.flag("INVALID_OWNERSHIP_TYPE", f"Value {tx.direct_or_indirect!r}.")
        else:
            r.ownership_type = "Direct" if di == "D" else "Indirect"
            self._note(
                acc,
                tid,
                "normalize",
                "ownership_type",
                "D/I code expanded",
                tx.direct_or_indirect,
                r.ownership_type,
            )
            if di == "I" and not tx.nature_of_ownership:
                d.flag("INDIRECT_WITHOUT_NATURE")
            if di == "D" and tx.nature_of_ownership:
                d.flag("DIRECT_WITH_NATURE", f"Nature given: {tx.nature_of_ownership!r}.")

        # Footnotes
        by_id: dict[str, list[str]] = {}
        for fld, ids in tx.footnote_ids.items():
            for fid in ids:
                by_id.setdefault(fid, []).append(fld)
        r.footnotes = [
            FootnoteRef(id=fid, fields=sorted(fields), text=filing.footnotes.get(fid))
            for fid, fields in sorted(by_id.items(), key=lambda kv: _footnote_order(kv[0]))
        ]
        missing = [fid for fid in by_id if fid not in filing.footnotes]
        if missing:
            d.flag("FOOTNOTE_NOT_FOUND", f"Missing: {', '.join(sorted(missing))}.")
        if n.parse_bool(filing.not_subject_to_section16):
            d.flag("NOT_SUBJECT_TO_SECTION_16")

        d.economic_key = (
            r.transaction_table,
            r.transaction_date,
            code,
            r.shares,
            r.price_per_share,
            (tx.acquired_disposed_code or "").upper(),
            (r.security_title or "").lower(),
        )
        return d


def _footnote_order(fid: str) -> tuple[int, str]:
    digits = "".join(ch for ch in fid if ch.isdigit())
    return (int(digits) if digits else 0, fid)


def _source_values(filing: ParsedFiling, tx: ParsedTransaction) -> str:
    data: dict[str, Any] = {
        "transaction": tx.model_dump(exclude_none=True),
        "filing": {
            "accession_number": filing.accession_number,
            "form_type": filing.form_type,
            "filing_date": filing.filing_date,
            "acceptance_datetime": filing.acceptance_datetime,
            "period_of_report": filing.period_of_report,
            "date_of_original_submission": filing.date_of_original_submission,
            "aff_10b5_one": filing.aff_10b5_one,
            "issuer_cik": filing.issuer_cik,
        },
        "reporting_owners": [o.model_dump(exclude_none=True) for o in filing.reporting_owners],
    }
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
