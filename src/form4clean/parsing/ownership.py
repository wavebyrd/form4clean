"""Parse SEC ownership XML (the ``ownershipDocument`` schema used by Forms 3, 4 and 5).

The parser extracts values exactly as written. It does not convert numbers or dates, fix
casing, or infer anything; that is the cleaning engine's job. Problems that stop a value from
being read are recorded in ``parse_warnings`` instead of raising, so one odd filing never
blocks a whole company.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from ..models.raw import ParsedFiling, ParsedHolding, ParsedTransaction, ReportingOwner
from ..sec.edgar import filing_index_url, pad_cik
from .submission import Submission, parse_submission


class OwnershipParseError(ValueError):
    pass


def _text(el: Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    value = " ".join(el.text.split())
    return value or None


def _value(parent: Element, path: str) -> str | None:
    """Text of ``path/value``, falling back to ``path`` itself for elements without <value>."""
    el = parent.find(path)
    if el is None:
        return None
    inner = el.find("value")
    return _text(inner) if inner is not None else _text(el)


def _footnote_ids(parent: Element, path: str) -> list[str]:
    el = parent.find(path)
    if el is None:
        return []
    return [fid.get("id", "").strip() for fid in el.iter("footnoteId") if fid.get("id")]


# field name -> path relative to the transaction element
_COMMON_FIELDS = {
    "security_title": "securityTitle",
    "transaction_date": "transactionDate",
    "deemed_execution_date": "deemedExecutionDate",
    "transaction_form_type": "transactionCoding/transactionFormType",
    "transaction_code": "transactionCoding/transactionCode",
    "equity_swap_involved": "transactionCoding/equitySwapInvolved",
    "transaction_timeliness": "transactionTimeliness",
    "shares": "transactionAmounts/transactionShares",
    "price_per_share": "transactionAmounts/transactionPricePerShare",
    "acquired_disposed_code": "transactionAmounts/transactionAcquiredDisposedCode",
    "shares_owned_after": "postTransactionAmounts/sharesOwnedFollowingTransaction",
    "value_owned_after": "postTransactionAmounts/valueOwnedFollowingTransaction",
    "direct_or_indirect": "ownershipNature/directOrIndirectOwnership",
    "nature_of_ownership": "ownershipNature/natureOfOwnership",
}
_DERIVATIVE_FIELDS = {
    "total_value": "transactionAmounts/transactionTotalValue",
    "conversion_or_exercise_price": "conversionOrExercisePrice",
    "exercise_date": "exerciseDate",
    "expiration_date": "expirationDate",
    "underlying_security_title": "underlyingSecurity/underlyingSecurityTitle",
    "underlying_shares": "underlyingSecurity/underlyingSecurityShares",
    "underlying_value": "underlyingSecurity/underlyingSecurityValue",
}
# transactionCoding carries footnotes on the element itself, not on transactionCode.
_FOOTNOTE_PATHS = {"transaction_code": "transactionCoding"}
_HOLDING_FIELDS = (
    "security_title",
    "shares_owned_after",
    "value_owned_after",
    "direct_or_indirect",
    "nature_of_ownership",
)


def _extract(
    el: Element, fields: dict[str, str]
) -> tuple[dict[str, str | None], dict[str, list[str]]]:
    values: dict[str, str | None] = {}
    notes: dict[str, list[str]] = {}
    for name, path in fields.items():
        values[name] = _value(el, path)
        if name in ("transaction_form_type", "equity_swap_involved"):
            continue
        ids = _footnote_ids(el, _FOOTNOTE_PATHS.get(name, path))
        if ids:
            notes[name] = ids
    return values, notes


def _parse_table(root: Element, table: str) -> tuple[list[ParsedTransaction], list[ParsedHolding]]:
    prefix = "nonDerivative" if table == "non_derivative" else "derivative"
    fields = dict(_COMMON_FIELDS)
    if table == "derivative":
        fields.update(_DERIVATIVE_FIELDS)
    transactions: list[ParsedTransaction] = []
    holdings: list[ParsedHolding] = []
    table_el = root.find(f"{prefix}Table")
    if table_el is None:
        return transactions, holdings
    for el in table_el.findall(f"{prefix}Transaction"):
        values, notes = _extract(el, fields)
        transactions.append(
            ParsedTransaction(table=table, sequence=len(transactions), footnote_ids=notes, **values)
        )
    holding_fields = {k: v for k, v in fields.items() if k in _HOLDING_FIELDS}
    if table == "derivative":
        holding_fields.update({k: v for k, v in _DERIVATIVE_FIELDS.items() if k != "total_value"})
    for el in table_el.findall(f"{prefix}Holding"):
        values, notes = _extract(el, holding_fields)
        holdings.append(
            ParsedHolding(
                table=table,
                sequence=len(holdings),
                footnote_ids=notes,
                **{k: values.get(k) for k in _HOLDING_FIELDS},
            )
        )
    return transactions, holdings


def _parse_owner(el: Element) -> ReportingOwner:
    rel = el.find("reportingOwnerRelationship")

    def get(path: str) -> str | None:
        return _value(rel, path) if rel is not None else None

    return ReportingOwner(
        cik=_value(el, "reportingOwnerId/rptOwnerCik"),
        name=_value(el, "reportingOwnerId/rptOwnerName"),
        is_director=get("isDirector"),
        is_officer=get("isOfficer"),
        is_ten_percent_owner=get("isTenPercentOwner"),
        is_other=get("isOther"),
        officer_title=get("officerTitle"),
        other_text=get("otherText"),
    )


def parse_ownership_xml(
    xml: str | bytes,
    *,
    accession_number: str,
    form_type: str | None = None,
    header: dict[str, str] | None = None,
    source_document: str | None = None,
) -> ParsedFiling:
    try:
        root = ElementTree.fromstring(xml.strip() if isinstance(xml, (str, bytes)) else xml)
    except ElementTree.ParseError as exc:
        raise OwnershipParseError(f"{accession_number}: ownership XML is malformed: {exc}") from exc
    if root.tag != "ownershipDocument":
        raise OwnershipParseError(
            f"{accession_number}: expected an ownershipDocument, found <{root.tag}>"
        )
    header = header or {}
    warnings: list[str] = []
    nd_tx, nd_hold = _parse_table(root, "non_derivative")
    d_tx, d_hold = _parse_table(root, "derivative")
    footnotes: dict[str, str] = {}
    for note in root.findall("footnotes/footnote"):
        fid = note.get("id")
        if not fid:
            warnings.append("A footnote has no id and cannot be linked to any field.")
            continue
        footnotes[fid.strip()] = " ".join("".join(note.itertext()).split())
    referenced = {fid for tx in (*nd_tx, *d_tx) for ids in tx.footnote_ids.values() for fid in ids}
    for fid in sorted(referenced - footnotes.keys()):
        warnings.append(f"Footnote {fid} is referenced but not present in the filing.")
    issuer_cik = _value(root, "issuer/issuerCik")
    doc_type = _value(root, "documentType")
    resolved_form = form_type or header.get("form_type") or doc_type or ""
    if doc_type and resolved_form and doc_type.upper() != resolved_form.upper():
        warnings.append(
            f"XML documentType {doc_type!r} differs from the filing header form {resolved_form!r}."
        )
    url = None
    if issuer_cik and issuer_cik.isdigit():
        url = filing_index_url(pad_cik(issuer_cik), accession_number)
    return ParsedFiling(
        accession_number=accession_number,
        form_type=resolved_form,
        filing_date=header.get("filed_as_of_date"),
        acceptance_datetime=header.get("acceptance_datetime"),
        period_of_report=_value(root, "periodOfReport"),
        document_type=doc_type,
        schema_version=_value(root, "schemaVersion"),
        date_of_original_submission=_value(root, "dateOfOriginalSubmission"),
        not_subject_to_section16=_value(root, "notSubjectToSection16"),
        issuer_cik=issuer_cik,
        issuer_name=_value(root, "issuer/issuerName"),
        issuer_trading_symbol=_value(root, "issuer/issuerTradingSymbol"),
        aff_10b5_one=_value(root, "aff10b5One"),
        reporting_owners=[_parse_owner(o) for o in root.findall("reportingOwner")],
        transactions=[*nd_tx, *d_tx],
        holdings=[*nd_hold, *d_hold],
        footnotes=footnotes,
        remarks=_value(root, "remarks"),
        signature_date=_value(root, "ownerSignature/signatureDate"),
        source_document=source_document,
        sec_filing_url=url,
        parse_warnings=warnings,
    )


def parse_filing(data: bytes | str, accession_number: str | None = None) -> ParsedFiling:
    """Parse a complete submission (.txt) into a ParsedFiling."""
    sub: Submission = parse_submission(data)
    accession = accession_number or sub.header.get("accession_number")
    if not accession:
        raise OwnershipParseError("The submission header has no accession number.")
    doc = sub.ownership_document()
    if doc is None or doc.xml is None:
        raise OwnershipParseError(
            f"{accession}: no ownership XML found. Filings before mid-2003 were not filed as "
            "XML and are not supported."
        )
    return parse_ownership_xml(
        doc.xml,
        accession_number=accession,
        form_type=sub.header.get("form_type"),
        header=sub.header,
        source_document=doc.filename,
    )
