# Auth Guard Session Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent every protected frontend route from rendering until a real backend-validated session exists, with one-attempt refresh, explicit context routing, logout clearing, tests, and a staging smoke.

**Architecture:** The Pinia session store owns an explicit `initializing`, `authenticated`, or `anonymous` state and performs bootstrap before router navigation resolves. Route metadata drives a global guard; the API interceptor coordinates a single refresh attempt and delegates failed authentication to the store. Protected shell components remain presentation-only and never bootstrap authentication themselves.

**Tech Stack:** Vue 3, Pinia, Vue Router 4, Axios, Vitest/jsdom, FastAPI pytest.

**Spec:** User request: “BUG CRÍTICO DE AUTENTICACIÓN EN STAGING” in the task conversation.

## Global Constraints

- No protected route may render without a backend-validated session.
- Do not hardcode or autocomplete seed credentials.
- Preserve backend 401/403 guarantees and do not add a migration.
- Do not touch production or create new Coolify resources.
- Deploy only the merged main commit to the existing staging frontend.

## Review Focus

- Empty storage, missing token, invalid token, expired token, and invalid refresh all end at `/login`.
- Refresh is attempted at most once for a request and cannot loop on repeated 401 responses.
- SuperAdmin without company context sees platform dashboard, never an undefined company.
- Zero, one, and multiple company memberships route to the required controlled state.
- Logout clears every session/context key and browser back/refresh cannot restore protected UI.

### Task 1: Failing authentication and router tests

**Files:**
- Create: `frontend/src/__tests__/auth-guard.test.ts`
- Modify: `frontend/src/__tests__/session.test.ts`

- [ ] Add tests for store bootstrap, invalid/expired access with failed refresh, authenticated guest redirect, protected route redirect, logout cleanup, and company-context routing.
- [ ] Run the focused Vitest file and confirm failures are caused by missing bootstrap/guard behavior.

### Task 2: Session store and API boundary

**Files:**
- Modify: `frontend/src/stores/session.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] Add explicit auth status and a single bootstrap promise; validate `/auth/me`, refresh once when needed, and clear all session state on failure.
- [ ] Add a single-flight response interceptor that retries the original request once after refresh, while leaving 403 untouched.
- [ ] Run the focused tests and confirm the new state machine passes.

### Task 3: Router/bootstrap and safe shell rendering

**Files:**
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/router.ts`
- Modify: `frontend/src/components/AppShell.vue`
- Modify: `frontend/src/views/PostLoginView.vue`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/LoginView.vue`
- Modify: `frontend/src/components/Topbar.vue`

- [ ] Add route metadata and global guards, await session bootstrap before initial navigation, and show a Vogel loading splash during initialization.
- [ ] Remove duplicate late auth loading from AppShell; make post-login routing distinguish SuperAdmin, zero, one, and multiple memberships.
- [ ] Ensure identity/context copy has explicit fallbacks and logout is awaited before navigation.
- [ ] Run frontend tests and build.

### Task 4: Backend regression coverage and full verification

**Files:**
- Modify: `backend/tests/test_auth.py` only if a missing protected-endpoint assertion is needed.

- [ ] Confirm unauthenticated and invalid-token protected requests return 401 and existing cross-tenant assertions remain 403.
- [ ] Run complete frontend and backend suites.
- [ ] Create the branch commit, push, open PR, wait for CI, merge, redeploy existing staging frontend without cache, and perform clean-browser anonymous/private-route and real SuperAdmin/logout smoke checks.
