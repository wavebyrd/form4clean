# Cleaning and classification rules

Every rule here is deterministic and covered by tests. Changing any of them increments
`CLEANING_VERSION`. Every change a rule makes to a value is written to the cleaning log with
the before and after values.

## Why raw Form 4 data needs cleaning

* The same security is written dozens of ways: `Common`, `COMMON STOCK, PAR VALUE $0.001 PER
  SHARE`, `Class A Common`, `RSU`.
* Names are filed `LAST FIRST MIDDLE`, usually in capitals.
* Numbers come with thousands separators, dates with XML timezone suffixes.
* Codes P and S mean "open market **or private**" purchase and sale, so a P is not always an
  exchange trade.
* A footnote, not a field, often says whether a sale was under a 10b5-1 plan, or that a price
  is a weighted average.
* Joint filings report one trade for several owners. Counting it once per owner double-counts
  the shares.
* Form 4/A amendments do not say which filing they amend, and may restate all, part or none of
  it.
* The SEC's own submissions index lists acceptance times in the wrong time zone (see
  [sec-data.md](sec-data.md#acceptance-timestamps)).

## Values

| Field | Rule |
|---|---|
| Numbers | Trim; remove `,` and `$`; parse as an exact `Decimal`. Non-numbers, `NaN`, infinities and values with more than 10 decimal places become null with a flag. |
| Dates | Accept `YYYY-MM-DD` with an optional XML timezone suffix (`2022-08-16-04:00`), `YYYYMMDD`, and `M/D/YYYY`. Invalid calendar dates become null with a flag. |
| Filing timestamp | Header `ACCEPTANCE-DATETIME`, interpreted as US Eastern. |
| CIKs | Digits only, zero-padded to 10. Anything else becomes null with a flag. |
| Booleans | `1`/`true`/`yes` and `0`/`false`/`no`, case-insensitive; anything else is null (unknown). |
| Transaction value | `shares × price_per_share`, rounded half-up to cents, only when both exist and the price is above zero. A zero price (awards, gifts) gives a null value, not $0. |
| Ownership | `D` becomes `Direct`, `I` becomes `Indirect`. Other values are flagged. The nature of ownership text is kept as filed. |

### Names

* Entities (names containing words like Inc, LLC, LP, Trust, Fund, Capital, Partners, or `&`,
  digits, or more than five words) keep their word order; only all-caps casing is fixed, with
  acronyms (LLC, LP, II, III) preserved.
* Individuals follow EDGAR's `LAST FIRST MIDDLE` convention and are reordered to
  `First Middle Last`. Suffixes (Jr, Sr, II, III, MD) stay at the end, and surname particles
  (van, de, der, la, st) stay with the surname. `Last, First` is also understood.
* **Limitation:** two-word surnames without a particle cannot be detected (`NORA JOHNSON
  SUZANNE M` becomes `Johnson Suzanne M Nora`). `insider_name_raw` always has the filed name,
  and `insider_cik` is the reliable identifier.

### Security titles

1. Collapse whitespace.
2. Remove par value clauses (`, par value $0.001 per share`, `$.01 par value`).
3. Fix all-caps or all-lowercase titles to title case, keeping acronyms (RSU, ADS, ESPP).
4. Map synonyms: `Common`/`Common Shares` to `Common Stock`; `Class A Common` to
   `Class A Common Stock`; `RSU(s)`/`Restricted Stock Unit` to `Restricted Stock Units`;
   `PSU(s)` to `Performance Stock Units`; option titles to `Stock Option (Right to Buy)`.

### Roles

`insider_role` is the first match, in this order, in the officer title: CEO, CFO, COO,
President, Chair, General Counsel, CTO, CAO. "Vice President" and "Vice Chair" never match
President or Chair. An officer with no recognized title is `Officer`; otherwise `Director`
(or `Chair` if the "other" text says so), `10% Owner`, `Other`, `Unknown`. The four relationship
boxes are also kept as booleans.

## Classification

The full Form 4 code list (General Instruction 8) is in `classification/codes.py` and in
[quality-flags.md](quality-flags.md#transaction-codes). Each code maps to a category:

| Category | Codes |
|---|---|
| Market Purchase | P |
| Market Sale | S |
| Equity Compensation | A |
| Derivative Exercise | M, X, O |
| Conversion | C |
| Tax-Related | F |
| Gift or Transfer | G, W |
| Other | D, I, E, H, L, Z, J, K, U, V |
| Unknown | anything else, or missing |

Unknown codes are never guessed; they are classified Unknown with LOW confidence and flagged
for review.

### Three-state fields

`true`, `false`, or `null` meaning the filing does not say.

**`is_10b5_1`**, in order:

1. A footnote on the transaction saying it was **not** under a 10b5-1 plan: `false`.
2. A footnote on the transaction citing a 10b5-1 plan: `true`.
3. The filing's 10b5-1 checkbox (forms since April 2023) unchecked: `false`.
4. Checkbox checked: `true` for P and S; unknown for other codes, because the box covers the
   whole filing and may refer to a different row.
5. Otherwise unknown.

**`is_market_transaction`**: for P and S, `true` if a footnote says open market, `false` if it
says private, privately negotiated, underwritten, secondary offering or block trade, otherwise
unknown. Every other code is `false`.

**`is_discretionary_trade`**: `false` for any 10b5-1 plan trade, awards, tax withholding,
dispositions to the issuer, gifts and expirations. For P and S: `true` only when the filing
states no plan was used, otherwise unknown. Exercises and conversions are unknown: the insider
picks the timing, but the exercise is not a market trade.

### Direction checks

The acquired/disposed code must agree with the transaction code where the instructions fix
it (for example P must be an acquisition, F a disposition, and an M row in the derivative
table a disposition of the option). A contradiction is flagged for review and lowers the
classification confidence to LOW; both values are kept as filed.

## Cross-record checks

* **Exercise legs.** In one filing, a derivative row and a common-stock row with the same
  exercise code, date and share count are linked in `related_transaction_ids`.
* **Duplicates in a filing.** Rows with identical values are both kept and flagged.
* **Duplicates across filings.** Current records in different filings with the same date, code,
  shares, price, direction, security, holdings after the trade and ownership type are flagged
  and linked. This catches related owners (a fund and its general partner) who each file the
  same trade, without flagging the common case of equal award sizes given to many insiders.
* **Holdings continuity.** Within a filing, for the same security and ownership, each row's
  holdings after the trade should equal the previous row's plus or minus this trade.
* **Price outliers.** A P or S common-stock price more than 50% away from the median of at
  least two other P/S prices in other filings within seven days. Stock splits trigger this; the
  explanation says so.
* **Late filing (INFO).** Filed more than two business days after the trade (approximated with
  the NYSE calendar). Not applied to amendments.

## Disclosure timing

`filing_timestamp` is compared with regular NYSE hours (9:30 a.m. to 4:00 p.m. Eastern, 1:00
p.m. on early-close days; holidays computed from NYSE rules):

| Accepted | `disclosure_timing` | `disclosure_session_date` |
|---|---|---|
| Before 9:30 on a trading day | PRE_MARKET | same day |
| During the session | MARKET_HOURS | same day |
| At or after the close | AFTER_CLOSE | next trading day |
| Weekend or holiday | NON_TRADING_DAY | next trading day |

The dashboard plots markers on `disclosure_session_date` by default, so a trade never appears
on the chart before investors could have known about it.

## Quality status

Each flag has a severity (see [quality-flags.md](quality-flags.md)). A record's status is the
most severe of its flags; INFO flags leave it VALID. INVALID is reserved for values that cannot
be used at all (an unparseable share quantity or price). A missing optional field is never
INVALID.
