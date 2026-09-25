# Foundation Multitenant Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair PR #1 so the FastAPI/Vue foundation installs, migrates, authenticates users, enforces active-company tenancy, seeds staging explicitly, and passes local and remote CI without touching Coolify.

**Architecture:** Keep the existing flat `backend` layout and explicitly package only `app*`; Alembic owns schema creation and reads `DATABASE_URL` from settings. FastAPI exposes health, auth, company selection, and a small protected company-context endpoint; tenant access is derived from the access token plus database membership, never from an arbitrary frontend value. The Vue shell remains minimal but uses a same-origin/API-base client seam for future `/api/v1` calls.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PyMySQL, JWT, pytest/TestClient, Vue 3, Vite, npm.

**Spec:** User request pasted in `C:\Users\Ventas\.codex\attachments\408578cb-fc35-4d82-96e6-1d91d06ca462\Texto pegado.txt`.

## Global Constraints

- Work only on `feat/foundation-multitenant`; do not create another PR.
- Do not merge while any CI check fails.
- Do not touch Coolify, production, DNS, or real PortalVogel/WhatsApp credentials.
- Do not use `create_all` in application startup; use Alembic for runtime schema changes.
- Do not hardcode staging passwords or JWT secrets.
- Keep seed explicit, idempotent, and never run it automatically at startup.

## Review Focus

- A refresh token must not authenticate as an access token: `test_refresh_token_cannot_access_tenant_endpoint`.
- A forged `company_id` must fail for a non-member even when the company exists: `test_forged_company_id_does_not_cross_tenant`.
- SuperAdmin access is bounded by active/existing companies: `test_superadmin_cannot_select_missing_or_inactive_company`.
- A stale/inactive company must fail after a token was issued: `test_inactive_company_is_rejected_by_tenant_context`.
- Re-running the staging seed must not duplicate users, companies, or memberships: `test_seed_is_idempotent`.

### Task 1: Red tests and packaging contract

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/tests/test_health.py`
- Replace: `backend/tests/test_tenant_isolation.py`
- Create: `backend/tests/test_auth.py`
- Create: `backend/tests/test_migrations.py`
- Create: `backend/tests/test_seed_staging.py`

- [ ] Write failing tests for health, login, refresh, company selection, tenant context, migration head, and idempotent seed.
- [ ] Run `pytest -q` and confirm the current missing `app.main`/auth implementation fails before production code changes.

### Task 2: Application and auth foundation

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/v1/auth.py`
- Create: `backend/app/api/v1/companies.py`
- Modify: `backend/app/api/dependencies.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/security.py`

- [ ] Implement `/health`, login, refresh, select-company, active-company listing, and protected current-company endpoint.
- [ ] Make token type, active user, active company, and membership checks explicit and consistent.
- [ ] Run focused auth/tenant tests and then the complete backend suite.

### Task 3: Alembic and explicit staging seed

**Files:**
- Create: `backend/alembic/env.py`
- Modify: `backend/alembic.ini`
- Modify: `backend/alembic/versions/20260925_0001_foundation.py`
- Create: `backend/scripts/seed_staging.py`

- [ ] Make Alembic read `DATABASE_URL` and upgrade an empty database to the single foundation head.
- [ ] Implement an explicit, idempotent seed using environment-provided passwords or secure generated values.
- [ ] Verify migration and seed behavior against an isolated temporary database.

### Task 4: Frontend/API seam and CI/build files

**Files:**
- Create: `frontend/src/api.ts`
- Modify: `frontend/src/App.vue`
- Create: `frontend/package-lock.json`
- Review: `frontend/Dockerfile`, `backend/Dockerfile`, `.github/workflows/ci.yml`

- [ ] Keep the initial Vue screen loadable and expose a configurable `/api/v1` base URL without secrets.
- [ ] Run `npm install` and `npm run build`; keep CI aligned with the committed lockfile.

### Task 5: Full validation and PR update

- [ ] Run `python -m compileall app`, `pytest -q`, `alembic heads`, `git diff --check`, `npm install`, and `npm run build`.
- [ ] Inspect the diff for secrets and verify no Coolify/production files or actions were touched.
- [ ] Commit descriptive changes, push `feat/foundation-multitenant`, and inspect PR #1 checks.
- [ ] If CI fails, read logs, correct the branch, push again, and repeat until green; never merge.
