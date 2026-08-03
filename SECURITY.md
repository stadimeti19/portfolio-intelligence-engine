# Security Policy

Until `1.0.0`, only the latest released `0.x` version receives security fixes.

Do not open a public vulnerability issue. Use GitHub private vulnerability reporting. If unavailable, contact the owner through the private method on their GitHub profile. Include affected versions, impact, reproduction steps, and mitigation.

Demo mode is offline and AI is disabled by default. Credentials come from environment variables or an ignored `.env`. YAML uses `safe_load`, templates escape untrusted text, and application state uses best-effort owner-only POSIX permissions. Local portfolios, caches, databases, logs, and reports are excluded from packages. Optional AI explanations cannot invoke tools and default to no response storage and no dollar values.
