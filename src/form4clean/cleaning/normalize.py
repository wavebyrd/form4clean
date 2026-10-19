"""Deterministic normalization rules for individual values.

Each function returns the normalized value and, when it cannot produce one, an error string.
None of them guess: a value that cannot be read confidently becomes None with an error, and the
pipeline flags the record. Rules are documented in docs/cleaning-rules.md.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ..calendar import EASTERN

CENT = Decimal("0.01")
MAX_SCALE = 10  # decimal places kept for quantities and prices (schema type DECIMAL(38, 10))

# ---------------------------------------------------------------- numbers


def parse_decimal(raw: str | None) -> tuple[Decimal | None, str | None]:
    """Parse a numeric source value. Thousands separators and a leading '$' are tolerated."""
    if raw is None:
        return None, None
    text = raw.strip().replace(",", "").replace("$", "").replace(" ", "")
    if text == "":
        return None, None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, f"{raw!r} is not a number"
    if not value.is_finite():
        return None, f"{raw!r} is not a finite number"
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -MAX_SCALE:
        return None, f"{raw!r} has more than {MAX_SCALE} decimal places"
    return value, None


def money(shares: Decimal, price: Decimal) -> Decimal:
    return (shares * price).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- dates

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:Z|[+-]\d{2}:\d{2})?$")
_COMPACT_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_US_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def parse_date(raw: str | None) -> tuple[date | None, str | None]:
    """Parse ISO dates (optionally with an XML timezone suffix), YYYYMMDD, or MM/DD/YYYY."""
    if raw is None or raw.strip() == "":
        return None, None
    text = raw.strip()
    for pattern, order in ((_DATE_RE, (1, 2, 3)), (_COMPACT_RE, (1, 2, 3)), (_US_RE, (3, 1, 2))):
        m = pattern.match(text)
        if m:
            y, mo, d = (int(m.group(i)) for i in order)
            try:
                return date(y, mo, d), None
            except ValueError:
                return None, f"{raw!r} is not a valid calendar date"
    return None, f"{raw!r} is not a recognized date format"


def parse_acceptance(raw: str | None) -> tuple[datetime | None, str | None]:
    """Parse the header ACCEPTANCE-DATETIME (YYYYMMDDHHMMSS, US Eastern)."""
    if raw is None or raw.strip() == "":
        return None, None
    try:
        naive = datetime.strptime(raw.strip(), "%Y%m%d%H%M%S")
    except ValueError:
        return None, f"{raw!r} is not a valid acceptance timestamp"
    return naive.replace(tzinfo=EASTERN), None


def parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in ("1", "true", "y", "yes"):
        return True
    if value in ("0", "false", "n", "no"):
        return False
    return None


# ---------------------------------------------------------------- CIKs


def normalize_cik(raw: str | None) -> tuple[str | None, str | None]:
    if raw is None or raw.strip() == "":
        return None, None
    text = raw.strip()
    if not text.isdigit() or len(text) > 10:
        return None, f"{raw!r} is not a valid CIK"
    return text.zfill(10), None


# ---------------------------------------------------------------- names

ENTITY_WORDS = frozenset(
    [
        "INC",
        "INC.",
        "INCORPORATED",
        "CORP",
        "CORP.",
        "CORPORATION",
        "CO",
        "CO.",
        "COMPANY",
        "LLC",
        "L.L.C.",
        "LP",
        "L.P.",
        "LLP",
        "L.L.P.",
        "LTD",
        "LTD.",
        "LIMITED",
        "PLC",
        "N.V.",
        "NV",
        "S.A.",
        "SA",
        "AG",
        "GMBH",
        "TRUST",
        "TR",
        "FUND",
        "FUNDS",
        "FOUNDATION",
        "PARTNERS",
        "PARTNERSHIP",
        "CAPITAL",
        "HOLDINGS",
        "HOLDING",
        "GROUP",
        "MANAGEMENT",
        "ADVISORS",
        "ADVISERS",
        "INVESTMENTS",
        "INVESTMENT",
        "VENTURES",
        "VENTURE",
        "ASSOCIATES",
        "BANK",
        "ESTATE",
        "ENTERPRISES",
        "SECURITIES",
        "MASTER",
        "OFFSHORE",
        "ONSHORE",
        "II-A",
        "SPV",
        "PORTFOLIO",
    ]
)
SUFFIXES = frozenset(
    {"JR", "JR.", "SR", "SR.", "II", "III", "IV", "MD", "M.D.", "PHD", "PH.D.", "ESQ", "ESQ."}
)
PARTICLES = frozenset(
    {
        "VAN",
        "VON",
        "DE",
        "DER",
        "DEN",
        "DI",
        "DA",
        "DEL",
        "DELLA",
        "DOS",
        "DU",
        "LA",
        "LE",
        "ST",
        "ST.",
        "TER",
        "TEN",
        "BIN",
        "AL",
        "EL",
    }
)
_KEEP_UPPER = frozenset(
    {
        "LLC",
        "LP",
        "LLP",
        "PLC",
        "II",
        "III",
        "IV",
        "USA",
        "US",
        "UK",
        "NV",
        "SA",
        "AG",
        "SPV",
        "MD",
        "PHD",
        "L.P.",
        "L.L.C.",
        "N.V.",
        "S.A.",
        "M.D.",
        "GP",
    }
)


def _cap_word(word: str) -> str:
    core = word.rstrip(",;:")
    if core != word:
        return _cap_word(core) + word[len(core) :]
    if word.upper() in _KEEP_UPPER:
        return word.upper()
    if re.fullmatch(r"(?:[A-Za-z]\.)+", word):
        return word.upper()
    parts = re.split(r"([-'\N{RIGHT SINGLE QUOTATION MARK}])", word.lower())
    out = []
    for part in parts:
        if part and part[0].isalpha():
            part = part[0].upper() + part[1:]
            if part.startswith("Mc") and len(part) > 2:
                part = "Mc" + part[2].upper() + part[3:]
        out.append(part)
    return "".join(out)


def _smart_case(tokens: list[str]) -> list[str]:
    joined = " ".join(tokens)
    if joined.isupper() or joined.islower():
        return [_cap_word(t) for t in tokens]
    return tokens


def is_entity_name(name: str) -> bool:
    tokens = [t.strip(",") for t in name.upper().split()]
    return (
        any(t in ENTITY_WORDS for t in tokens)
        or "&" in name
        or any(ch.isdigit() for ch in name)
        or len(tokens) > 5
    )


def normalize_person_or_entity(raw: str | None) -> tuple[str | None, str | None]:
    """Return (display name, rule applied). Individuals filed as 'LAST FIRST M' become
    'First M Last'; entities keep their word order and only get their casing fixed."""
    if raw is None or raw.strip() == "":
        return None, None
    text = " ".join(raw.split())
    if is_entity_name(text):
        cased = " ".join(_smart_case(text.split()))
        return cased, ("entity name: casing normalized" if cased != text else None)
    if "," in text:
        last, _, rest = text.partition(",")
        tokens = rest.split()
        suffix = [t for t in tokens if t.upper().strip(",") in SUFFIXES]
        given = [t for t in tokens if t not in suffix]
        ordered = [*given, *last.split(), *suffix]
        rule = "individual 'Last, First' reordered to 'First Last'"
    else:
        tokens = text.split()
        if len(tokens) < 2:
            cased = " ".join(_smart_case(tokens))
            return cased, ("casing normalized" if cased != text else None)
        suffix = [t for t in tokens[1:] if t.upper() in SUFFIXES]
        core = [t for t in tokens if t not in suffix]
        n_last = 1
        while n_last < len(core) - 1 and core[n_last - 1].upper() in PARTICLES:
            n_last += 1
        ordered = [*core[n_last:], *core[:n_last], *suffix]
        rule = "individual 'LAST FIRST' (EDGAR convention) reordered to 'First Last'"
    display = " ".join(_smart_case(ordered))
    return display, (rule if display != text else None)


# ---------------------------------------------------------------- security titles

_PAR_VALUE = re.compile(
    r"[,;]?\s*\(?\s*(?:\$\s*[\d.]+\s+)?par\s+value(?:\s+\$?\s*[\d.]+)?(?:\s+per\s+share)?\s*\)?",
    re.IGNORECASE,
)
_SMALL = frozenset(
    {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "per", "the", "to", "with"}
)
_ACRONYMS = {
    "rsu": "RSU",
    "rsus": "RSUs",
    "psu": "PSU",
    "psus": "PSUs",
    "ads": "ADS",
    "adss": "ADSs",
    "adr": "ADR",
    "adrs": "ADRs",
    "espp": "ESPP",
    "llc": "LLC",
    "lp": "LP",
    "sar": "SAR",
    "sars": "SARs",
    "ltip": "LTIP",
    "ipo": "IPO",
    "dsu": "DSU",
    "dsus": "DSUs",
    "us": "US",
    "i": "I",
    "ii": "II",
    "iii": "III",
}
_CANONICAL = [
    (re.compile(r"^(?:shares of )?common(?: stock| shares)?$", re.I), "Common Stock"),
    (re.compile(r"^class ([a-z])(?: common)?(?: stock| shares)?$", re.I), "Class {0} Common Stock"),
    (re.compile(r"^(?:rsus?|restricted stock units?)$", re.I), "Restricted Stock Units"),
    (
        re.compile(r"^(?:psus?|performance (?:stock|share) units?)$", re.I),
        "Performance Stock Units",
    ),
    (re.compile(r"^stock options? \(right to buy\)$", re.I), "Stock Option (Right to Buy)"),
    (
        re.compile(r"^employee stock options? \(right to buy\)$", re.I),
        "Employee Stock Option (Right to Buy)",
    ),
]


def _title_case(text: str) -> str:
    words = re.split(r"(\s+|[()/,-])", text)
    out: list[str] = []
    first = True
    for word in words:
        lower = word.lower()
        if not word.strip() or not word[0].isalnum():
            out.append(word)
            continue
        if lower in _ACRONYMS:
            out.append(_ACRONYMS[lower])
        elif lower in _SMALL and not first:
            out.append(lower)
        else:
            out.append(lower[:1].upper() + lower[1:])
        first = False
    return "".join(out)


def normalize_security_title(raw: str | None) -> tuple[str | None, list[str]]:
    """Return (normalized title, rules applied)."""
    if raw is None or raw.strip() == "":
        return None, []
    rules: list[str] = []
    text = " ".join(raw.split())
    stripped = _PAR_VALUE.sub("", text).strip(" ,;")
    if stripped and stripped != text:
        rules.append("par value clause removed")
        text = stripped
    letters = [c for c in text if c.isalpha()]
    if letters and (all(c.isupper() for c in letters) or all(c.islower() for c in letters)):
        cased = _title_case(text)
        if cased != text:
            rules.append("casing normalized")
            text = cased
    for pattern, canonical in _CANONICAL:
        m = pattern.match(text)
        if m:
            value = canonical.format(*(g.upper() for g in m.groups()))
            if value != text:
                rules.append(f"synonym mapped to {value!r}")
                text = value
            break
    return text, rules


# ---------------------------------------------------------------- roles

_ROLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("CEO", re.compile(r"\bCEO\b|CHIEF\s+EXECUTIVE|PRINCIPAL\s+EXECUTIVE")),
    ("CFO", re.compile(r"\bCFO\b|CHIEF\s+FINANCIAL|PRINCIPAL\s+FINANCIAL")),
    ("COO", re.compile(r"\bCOO\b|CHIEF\s+OPERATING")),
    ("President", re.compile(r"\bPRESIDENT\b")),
    ("Chair", re.compile(r"\bCHAIR(?:MAN|WOMAN|PERSON)?\b")),
    ("General Counsel", re.compile(r"GENERAL\s+COUNSEL|CHIEF\s+LEGAL|\bCLO\b")),
    ("CTO", re.compile(r"\bCTO\b|CHIEF\s+TECHNOLOGY")),
    ("CAO", re.compile(r"\bCAO\b|CHIEF\s+ACCOUNTING|PRINCIPAL\s+ACCOUNTING")),
]
ROLES = (
    "CEO",
    "CFO",
    "COO",
    "President",
    "Chair",
    "General Counsel",
    "CTO",
    "CAO",
    "Officer",
    "Director",
    "10% Owner",
    "Other",
    "Unknown",
)


def _match_role(text: str) -> str | None:
    upper = re.sub(r"VICE[\s-]+PRESIDENT|\bEVP\b|\bSVP\b|\bVP\b", " ", text.upper())
    upper = re.sub(r"VICE[\s-]+CHAIR\w*", " ", upper)
    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(upper):
            return role
    return None


def standard_role(
    *,
    is_officer: bool | None,
    is_director: bool | None,
    is_ten_percent: bool | None,
    is_other: bool | None,
    officer_title: str | None,
    other_text: str | None,
) -> str:
    if officer_title:
        role = _match_role(officer_title)
        if role:
            return role
    if is_officer or officer_title:
        return "Officer"
    if is_director:
        if other_text and _match_role(other_text) == "Chair":
            return "Chair"
        return "Director"
    if is_ten_percent:
        return "10% Owner"
    if is_other:
        return "Other"
    return "Unknown"
