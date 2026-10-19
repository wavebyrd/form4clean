"""Split an EDGAR complete submission (.txt) into its SGML header and documents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADER_KEYS = {
    "ACCESSION NUMBER": "accession_number",
    "CONFORMED SUBMISSION TYPE": "form_type",
    "CONFORMED PERIOD OF REPORT": "period_of_report",
    "FILED AS OF DATE": "filed_as_of_date",
}
_ACCEPTANCE_RE = re.compile(r"<ACCEPTANCE-DATETIME>\s*(\d{14})")
_DOCUMENT_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.DOTALL | re.IGNORECASE)
_TAG_RE = {
    "type": re.compile(r"<TYPE>([^\r\n<]*)", re.IGNORECASE),
    "filename": re.compile(r"<FILENAME>([^\r\n<]*)", re.IGNORECASE),
}
_XML_RE = re.compile(r"<XML>\s*(.*?)\s*</XML>", re.DOTALL | re.IGNORECASE)


@dataclass
class SubmissionDocument:
    type: str
    filename: str | None
    xml: str | None


@dataclass
class Submission:
    header: dict[str, str] = field(default_factory=dict)
    documents: list[SubmissionDocument] = field(default_factory=list)

    @property
    def acceptance_datetime(self) -> str | None:
        return self.header.get("acceptance_datetime")

    def ownership_document(self) -> SubmissionDocument | None:
        """The XML document whose type matches the submission type, or any ownership XML."""
        form = self.header.get("form_type", "")
        candidates = [d for d in self.documents if d.xml and "<ownershipDocument" in d.xml]
        for doc in candidates:
            if doc.type.strip().upper() == form.strip().upper():
                return doc
        return candidates[0] if candidates else None


def decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def parse_submission(data: bytes | str) -> Submission:
    text = decode(data) if isinstance(data, bytes) else data
    sub = Submission()
    header_end = text.find("</SEC-HEADER>")
    header = text[: header_end if header_end != -1 else min(len(text), 20000)]
    match = _ACCEPTANCE_RE.search(header)
    if match:
        sub.header["acceptance_datetime"] = match.group(1)
    for line in header.splitlines():
        if ":" not in line or line.startswith(("\t", " ")):
            continue
        key, _, value = line.partition(":")
        name = _HEADER_KEYS.get(key.strip())
        if name and name not in sub.header:
            sub.header[name] = value.strip()
    for block in _DOCUMENT_RE.findall(text):
        doc_type = _TAG_RE["type"].search(block)
        filename = _TAG_RE["filename"].search(block)
        xml = _XML_RE.search(block)
        sub.documents.append(
            SubmissionDocument(
                type=doc_type.group(1).strip() if doc_type else "",
                filename=filename.group(1).strip() if filename else None,
                xml=xml.group(1) if xml else None,
            )
        )
    return sub
