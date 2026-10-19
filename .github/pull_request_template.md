## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## How it was tested

<!-- New or updated tests, and anything checked by hand (commands, tickers, accession numbers). -->

## Checklist

- [ ] Tests cover the change, and `pytest`, `ruff check .`, `ruff format --check .` and `mypy` pass
- [ ] If a cleaning, classification, reconciliation or quality rule changed: `CLEANING_VERSION`
      is bumped and the docs describe the new rule
- [ ] If a column changed: `SCHEMA_VERSION` is bumped and `python scripts/generate_docs.py` was run
- [ ] If the dashboard changed: `npm test` and `npm run build` pass, and the built files are committed
- [ ] No source record can be dropped and no value is estimated
