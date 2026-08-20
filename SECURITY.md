# Security

## Reporting a Vulnerability

If you discover a security vulnerability in OpenCode Go Pool, please do **not** open a public issue. Instead, report it privately to the repository owner via GitHub's **Security Advisories** (Repository → Security → New advisory) so it can be fixed before public disclosure.

## What this project does NOT do

- It never stores or transmits account API keys in plaintext within the repository.
- Account keys live only in local `.env` / environment variables (git-ignored), referenced from `accounts.yaml` via `${ENV_VAR}`.
- Gateway API keys are stored as SHA-256 hashes; the plaintext is shown only once at creation.
- It does not implement cookie scraping, session reuse, credential forging, or reselling of quota.

## Local secret layout (git-ignored)

| File | Content |
|---|---|
| `apps/backend/.env` | Application settings |
| `apps/backend/.env.keys` | Account keys + `GATEWAY_MASTER_KEY` / `GATEWAY_AUTH` |
| `apps/backend/config/accounts.yaml` | Account definitions (keys referenced via env vars) |
| `apps/backend/data/*.db` | Local SQLite data |

These are excluded by `.gitignore` and must never be committed. If you believe a key has leaked, rotate it immediately and update the local files.
