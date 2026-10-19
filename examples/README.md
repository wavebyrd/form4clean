# Examples

Set your SEC contact email once (`form4clean config --email you@example.com`, or the
`FORM4CLEAN_SEC_EMAIL` environment variable), then:

| Script | What it shows |
|---|---|
| [`python_api.py`](python_api.py) | Load a company, filter by type, role, value and quality, export Parquet with a manifest |
| [`point_in_time.py`](point_in_time.py) | What was public on a past date versus today; disclosure timing |

```bash
python examples/python_api.py NVDA
python examples/point_in_time.py NVDA 2025-06-01
```

The first run downloads five years of filings for the ticker (a minute or two for a large
company); later runs read the local copy.
