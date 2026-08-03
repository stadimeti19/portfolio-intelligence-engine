# Privacy

The MVP is local-first and runs offline with synthetic demo data.

- `.env`, credentials, private CSV files, local databases, caches, logs, and generated reports are ignored by git.
- API keys are optional and are not needed for demo mode.
- AI explanations are disabled by default. The deterministic application remains authoritative for
  every calculated value and continues to work without an OpenAI API key.
- When enabled, only a minimal explanation-specific payload is sent to OpenAI. It includes relevant
  computed percentages, methodology version, data dates, freshness labels, and limitations. It does
  not include brokerage credentials, account names or identifiers, transaction IDs, raw transaction
  history, or unnecessary news or filing text.
- Exact dollar values are omitted by default. Set `OPENAI_SEND_DOLLAR_VALUES=true` only when you
  explicitly want the selected report slice to contain those values.
- `OPENAI_STORE_RESPONSES=false` is the default and is passed to the Responses API. To avoid repeat
  paid requests, the application separately caches the already privacy-filtered structured request
  and response in the local application cache. Use `portfolio explain --force` to bypass it.
- Explanation logs record only model, explanation type, token usage when available, and success or
  failure. They do not contain API keys, full payloads, exact holdings in privacy mode, or full model
  responses.
- Brokerage tokens and personal transaction files should never be committed.
- Brokerage position exports are processed locally. Broker-specific importers use an allowlist of portfolio fields and discard account names, account numbers, brokerage identifiers, gain/loss columns, and other unneeded metadata by default.
- Fixtures in this repository are synthetic and do not contain personal financial data.
- Diagnostics must redact credentials and avoid logging full private transaction files.
