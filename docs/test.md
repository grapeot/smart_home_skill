# Test Strategy

## Goals

The test suite protects four contracts:

1. Device adapters return stable results under mocked conditions.
2. FastAPI routes expose callable, OpenAPI-documented endpoints for agents.
3. The frontend store and production build keep working against the backend API.
4. The dashboard UX preserves safety-critical layout and loading behavior without relying on real devices.

## Commands

Backend unit tests:

```bash
source .venv/bin/activate
python -m pytest test/ -q --ignore=test/test_integration_real.py
```

Frontend tests and build:

```bash
cd frontend
npm test -- --run
npm run build
```

Frontend UX tests:

```bash
cd frontend
npx playwright install chromium
npm run test:ux
```

Startup script syntax:

```bash
bash -n start_server.sh
```

Privacy scan for public files:

```bash
git grep -n -E '<real-lan-subnet>|<real-email>|<secret-reference>|<device-id>' -- . ':!*.lock' || true
```

The final command should print nothing for tracked public files.

## Coverage Map

| Area | Tests |
|---|---|
| API routes | `test/test_api.py` |
| Hue service | `test/test_hue_service.py` |
| Wemo service | `test/test_wemo_service.py` |
| Meross local HTTP | `test/test_meross_service.py` |
| Garage notifications | `test/test_notification_service.py` |
| Database/history | `test/test_database.py` |
| Dynamic scheduler | `test/test_dynamic_scheduler.py`, `test/test_action_executor.py` |
| Aggregate status API | `test/test_status_api.py` |
| Visual check service/API | `test/test_visual_check_service.py`, `test/test_visual_check_api.py`, `test/test_visual_check_integration.py` |
| Frontend store | `frontend/src/stores/deviceStore.test.ts` |
| Frontend UX | `frontend/tests/ux/control-dashboard.spec.ts` |

## OpenAPI Assertions

`test/test_api.py` should keep explicit checks for `/openapi.json`:

1. The schema returns 200.
2. Core endpoints are present.
3. Garage toggle is POST-only.
4. The SPA catch-all route is not included in OpenAPI.

These tests make OpenAPI-first agent usage safer because they catch accidental schema regressions.

## Live Integration Tests

`test/test_integration_real.py` is intentionally excluded from default test runs. It may touch real devices and should only run with explicit local intent.

`test/test_visual_check_e2e_real.py` is a safer real-data E2E path for visual checks. It does not trigger garage actions; it calls the configured visual-check endpoint and asserts that the response is valid JSON with the expected result envelope. It is skipped unless explicitly enabled:

```bash
source .venv/bin/activate
SMART_HOME_RUN_REAL_E2E=1 SMART_HOME_REAL_VISUAL_CHECK_ID=garage python -m pytest test/test_visual_check_e2e_real.py -v
```

This test targets the running service at `SMART_HOME_REAL_BASE_URL`, defaulting to `http://localhost:7999`, so start or restart the local service before running it.

## CI

GitHub Actions runs backend pytest, frontend Vitest/build, and Playwright UX tests on PRs. Real-device and real-data E2E tests stay out of CI by default and require explicit local opt-in.
