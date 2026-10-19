# Amendments and point-in-time data

## The problem

A Form 4/A corrects an earlier Form 4, but it does not contain the accession number of the
filing it corrects. It may restate every row with one value changed, restate only the rows it
fixes, add rows that were left out, or remove rows reported in error. Counting both the
original and the amendment double-counts the trade; replacing the original wholesale can drop
rows the amendment never touched.

## How Form4Clean reconciles

### 1. Link the amendment to its original

Candidates are earlier original Forms 4 that share a reporting owner (by CIK) with the
amendment and that were filed, or accepted, on the amendment's `dateOfOriginalSubmission`. If
the amendment has no such date, candidates must share its `periodOfReport`.

| Candidates | Result | Effect |
|---|---|---|
| Exactly one | `LINKED` (HIGH confidence with a submission date, MEDIUM without) | Record-level matching below |
| None | `ORIGINAL_NOT_FOUND` | Amendment records stay current, with a warning. Usually the original is outside the downloaded date range. |
| Several | `AMBIGUOUS` | Amendment records leave the current view and are flagged for review. The originals stay current. |

### 2. Match records

Amendments of the same original are applied in acceptance order, each against the records that
are current at that point. Matching is done table by table (non-derivative, derivative):

1. Rows with the same transaction date, code, security title and ownership type pair up in
   order of appearance.
2. If rows are left on both sides in equal numbers, they pair by position. This is an
   amendment that changes a date, code or security; it is flagged `AMENDMENT_MATCHED_BY_POSITION`.
3. Amended rows with nothing left to pair are additions (`AMENDED_ADDED`).
4. If rows are left on both sides in unequal numbers, the amended rows are ambiguous: they
   leave the current view and are flagged for review, and the earlier rows stay current.
5. Earlier rows the amendment does not restate stay current (`ORIGINAL_NOT_RESTATED`). If the
   amendment's table is empty, they are flagged `AMENDMENT_MAY_REMOVE` for review, because the
   amendment may have been filed to remove them.

A paired earlier record becomes `SUPERSEDED` (out of the current view, `superseded_by` set).
The amended record becomes `AMENDED_RESTATED` if its values are identical, or
`AMENDED_CORRECTED` if anything changed.

### Statuses

| `amendment_status` | Current view | Meaning |
|---|---|---|
| `ORIGINAL` | yes | No amendment touched it |
| `ORIGINAL_NOT_RESTATED` | yes | Its filing was amended but this row was not restated |
| `AMENDED_RESTATED` | yes | Amendment row repeating an earlier row |
| `AMENDED_CORRECTED` | yes | Amendment row replacing an earlier row with new values |
| `AMENDED_ADDED` | yes | Amendment row with no earlier counterpart |
| `AMENDMENT_ORIGINAL_NOT_FOUND` | yes | Original filing not in the dataset |
| `SUPERSEDED` | no | Replaced by a later amendment row |
| `AMENDMENT_AMBIGUOUS` | no | Could not be matched confidently |
| `NOT_RECONCILED` | yes | Reconciliation turned off |

Nothing is ever deleted. Superseded and ambiguous records are available with
`include_superseded=True` (Python), `--all` (CLI) or the "Include superseded" filter
(dashboard). Every linking and matching decision is in the cleaning log and the
`amendment_links` table.

## Views

**Current view** (default): the latest confidently reconciled history, so each trade is counted
once.

**All records**: current view plus superseded and ambiguous records, with `is_current` telling
them apart.

**Not reconciled**: every row from every filing as filed. Restated rows show up twice and are
flagged as possible duplicates.

**Point in time**: what was public at a moment in the past.

```bash
form4clean export NVDA --as-of 2025-06-01
```

```python
InsiderData("NVDA").transactions(as_of="2025-06-01")
```

The pipeline runs on only the filings whose acceptance time is at or before the cutoff, and
reconciles them with only the amendments public by then. An amendment filed after the cutoff
therefore has no effect, and the original record is current, exactly as it was at the time. A
bare date means the end of that day, US Eastern; pass a full timestamp
(`2025-06-01T09:30:00-04:00`) for intraday cutoffs.

A filing with no acceptance timestamp is treated as public at 5:30 p.m. Eastern on its filing
date, the latest time a filing can be accepted and still receive that date. It can appear late
in a point-in-time view, but never early.
