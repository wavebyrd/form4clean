# Contributing to Form4Clean

Thanks for helping. Bug reports, data issues, documentation fixes and code are all welcome.

## The rules that matter most

1. **Never drop a source record and never invent a value.** If something cannot be read or
   classified confidently, keep the record, leave the value null, and add a quality flag.
2. **Money is exact.** Use `Decimal`, never `float`, for shares, prices and values.
3. **Every rule is deterministic and tested.** The same filings and cleaning version must give
   byte-for-byte identical output.
4. **Rule changes are versioned.** Changing any cleaning, classification, reconciliation or
   quality rule bumps `CLEANING_VERSION` in `src/form4clean/versions.py`. Changing columns bumps
   `SCHEMA_VERSION` and needs `python scripts/generate_docs.py`.
5. **Be polite to the SEC.** All network access goes through `SecClient`. Tests never make real
   requests; use the fake EDGAR in `tests/conftest.py`.

## Set up

```bash
git clone https://github.com/wavebyrd/form4clean
cd form4clean
uv venv && uv pip install -e ".[dev]"     # or: python -m venv .venv && pip install -e ".[dev]"
```

Run the checks (on Windows, use `.venv\Scripts\` instead of `.venv/bin/`):

```bash
.venv/bin/pytest                       # unit and integration tests, no network
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy                         # strict
.venv/bin/python scripts/generate_docs.py --check
```

Optional live test against SEC EDGAR:

```bash
FORM4CLEAN_SEC_EMAIL=you@example.com .venv/bin/pytest -m live
```

Dashboard:

```bash
cd frontend
npm install
npm test && npm run typecheck && npm run lint
npm run build    # commit the files it writes to src/form4clean/api/static
```

## Adding a test fixture

Fixtures in `tests/fixtures/filings/` are realistic ownership XML for a fictional issuer,
Example Robotics Inc. (CIK 0000999001). To reproduce a real-world problem, copy the structure of
the real filing into a new fixture with fictional names, add it to `index.json` with an
accession number and acceptance time, and write a test that fails before your fix.

## Where things live

See [docs/architecture.md](docs/architecture.md). In short: `sec/` downloads, `parsing/` reads
XML, `cleaning/` + `classification/` + `amendments/` + `validation/` are the engine,
`storage/` is DuckDB, and `service.py` holds the workflows that the Python API, CLI and HTTP
API share.

## Pull requests

Keep them focused, describe how you tested, and fill in the checklist in the PR template. User-
facing text uses plain language and sentence case; error messages say what happened and what to
do next.
