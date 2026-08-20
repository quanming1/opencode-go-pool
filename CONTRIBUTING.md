# Contributing

Thanks for your interest in OpenCode Go Pool. This project follows the **Rondo method** — PRD-driven, TODO-driven development with a full pull-request flow.

## Development flow (agreed with the repository owner)

1. **Follow `docs/TODO.yaml`** — it is the single source of truth. Work stage by stage, no skipping.
2. **PRD first** — before coding a stage, create/update its PRD in `docs/prd/` (copy from the template) and reach `approved`.
3. **Branch per task** — `develop` only accepts Pull Requests; create a branch named `feature/<stage>-<name>` (or `fix/<stage>-<name>`, `docs/...`, `todos`, `prd`, `chore/...`).
4. **Conventional commits** — `<type>(<scope>): <subject>` with a *Chinese* subject, English type/scope. `feat`/`fix`/`prd`/`todos` scopes must be a real stage id from `docs/TODO.yaml` (enforced by githooks).
5. **Open a PR** to `develop`, wait for CI (backend `pytest` + `ruff`, web `eslint` + `vitest` + `build`), get a review, then merge.
6. **No local merges into `develop`** — `develop` and `main` only receive PRs. Never push to `main` directly.

## Local checks before opening a PR

```bash
# backend
cd apps/backend && .venv\Scripts\python -m pytest && .venv\Scripts\python -m ruff check .

# frontend
cd apps/web && pnpm lint && pnpm test --run && pnpm build
```

## Testing

- Backend: `pytest` under `apps/backend/tests/` — every new feature needs tests; every bug fix needs a regression test. Tests must not depend on real external credentials (use mock/fake upstream).
- Frontend: `vitest` for key logic components.

## Security

Never commit secrets. Account keys live only in local `.env` / environment variables (git-ignored); templates (`*.example.*`) must contain placeholders only. See [SECURITY.md](SECURITY.md).
