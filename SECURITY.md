# Security

Form4Clean runs locally. The dashboard binds to 127.0.0.1 and has no authentication, so do not
expose it to a network you do not trust (for example with `--host 0.0.0.0`).

Settings, including any price-provider API key, are stored in plain text in
`~/.form4clean/config.json` on your computer. Filings are parsed with `defusedxml`.

To report a vulnerability, please use GitHub's private vulnerability reporting on this
repository rather than opening a public issue.
