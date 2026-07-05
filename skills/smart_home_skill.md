# Smart Home Skill

## Goal

Operate a local Smart Home Skill service safely through its live OpenAPI schema and private household overlay.

## Acceptance Criteria

A successful agent run:

1. Uses the running service's `GET /openapi.json` as the callable API source of truth.
2. Uses private overlay notes only for household-specific semantics: aliases, defaults, safety policy, and local deployment details.
3. Verifies the selected endpoint and HTTP method in OpenAPI before calling it.
4. Uses dedicated endpoints rather than inventing a generic action API.
5. Treats garage door and other physical actions as sensitive operations.
6. Reports the actual API response, including notification status when present.
7. Uses `visual_check` CLI or HTTP endpoints for configured camera-based state checks instead of free-form image guessing.

## Public/Private Split

This public repo provides implementation, tests, safe examples, and this root skill. It must not contain real local IPs, credentials, notification addresses, device UUIDs, or private household aliases.

Private overlays belong in the user's workspace. They should contain:

1. Base URL for the deployed local service.
2. Common natural-language mappings such as household names for devices.
3. Safety notes and default behavior for sensitive devices.
4. Local notification expectations.

Private overlays should not copy the full endpoint list. OpenAPI is the endpoint contract.

## Required Runtime Checks

Before executing any action:

1. Check service health with `GET {base_url}/health` when feasible.
2. Fetch `GET {base_url}/openapi.json`.
3. Resolve the user's request through private overlay notes.
4. Confirm the path and method exist in OpenAPI.
5. Execute the dedicated endpoint.
6. Inspect the response for `status`, `message`, `error`, and `notification`.

## Safety Rules

Garage doors are sensitive physical actions.

1. Use only `POST /api/garage/{door_index}/toggle` when it exists in OpenAPI.
2. Do not use or invent GET garage toggle endpoints.
3. Remember that the action is a trigger/toggle, not a guaranteed absolute open/close command unless the deployment provides reliable sensor state.
4. If notification is configured, check the response's `notification.sent` field and report it.
5. When a garage action needs verification and a visual check is configured, run a fresh visual check after the action rather than relying on cached or inferred door state.

## Visual Checks

`visual_check` is the generic camera + local vision model subsystem. It converts a configured camera snapshot into schema-validated JSON, saves artifacts, and evaluates deterministic assertions.

Use the live OpenAPI schema for HTTP routes:

```text
GET /api/visual-checks
POST /api/visual-checks/{check_id}/run
POST /api/visual-checks/groups/{group}/run
```

For local agent workflows, the CLI is often simpler:

```bash
python scripts/visual_check.py list
python scripts/visual_check.py --json run <check_id>
python scripts/visual_check.py --json run-all --group nightly
```

Read only the JSON result for automation decisions. Do not re-interpret the image unless the CLI or API fails. If `status` is `problem` or an assertion failed, report the failed assertion and artifact path. If `status` is `failed`, report `error` and do not treat the physical state as known.

## Known Pitfalls

1. README endpoint tables can become stale. Fetch `/openapi.json`.
2. Private aliases can drift from real config. Double-check ambiguous commands against the private overlay.
3. macOS Local Network permission can depend on how the service was launched. If local devices are unreachable after restart, verify the Process Launcher path rather than assuming device failure.
4. `.env` should not be shell-sourced because values can contain spaces.

## Output Style

For successful actions, report the device/action and the key result fields. For failures, include the HTTP status and response body when available. For sensitive actions, include whether notification was sent.
