# Privacy

The MVP is local-first and runs offline with synthetic demo data.

- `.env`, credentials, private CSV files, local databases, caches, logs, and generated reports are ignored by git.
- API keys are optional and are not needed for demo mode.
- AI is disabled by default. If AI explanations are added later, they must be opt-in and must not calculate authoritative values.
- Brokerage tokens and personal transaction files should never be committed.
- Brokerage position exports are processed locally. Broker-specific importers use an allowlist of portfolio fields and discard account names, account numbers, brokerage identifiers, gain/loss columns, and other unneeded metadata by default.
- Fixtures in this repository are synthetic and do not contain personal financial data.
- Diagnostics must redact credentials and avoid logging full private transaction files.
