# RFC: Architecture and API Contract

## Summary

The architecture keeps runtime execution concrete and OpenAPI-discoverable. FastAPI routes are the execution contract. Private overlays add household semantics. The UI is a debug surface on top of the same APIs.

```text
Human / AI command
        |
        v
Private overlay: aliases, defaults, safety notes
        |
        v
Live OpenAPI: endpoint and method verification
        |
        v
Dedicated FastAPI endpoint
        |
        v
Device adapter: Hue / Wemo / Rinnai / Meross / Camera
```

Read-only telemetry spikes may also expose CLI surfaces before becoming FastAPI endpoints. The Ring status spike follows that path: it validates that Ring Alarm sensor state can be read safely before adding backend/API/dashboard integration.

## Why This Skill Is an Always-On Web Service

Most public AI skills in this workspace use a CLI contract. That is the right shape for research, file processing, email workflows, and other tasks where an agent is already in the loop. Smart home control needs a different runtime shape.

The system has to serve two classes of callers:

1. AI agents that benefit from natural language, private household overlays, and OpenAPI verification.
2. Direct triggers such as Flic buttons, iOS Shortcuts, Apple Watch actions, Siri shortcuts, and simple curl calls.

A CLI-only skill would force every action through an AI conversation or a local agent process. That adds latency and makes physical integrations awkward. A garage button, watch shortcut, or Siri phrase needs a stable local URL that can be called immediately. The FastAPI server provides that always-on surface, while `/openapi.json` gives agents the same runtime contract.

This is why the architecture is not "CLI instead of server". It is "server as the physical integration surface, OpenAPI as the AI contract, private overlay as the household grounding layer".

## OpenAPI as Source of Truth

The running service publishes `GET /openapi.json`. Agents should fetch it before calling APIs. This avoids stale README endpoint lists and keeps the actual running server authoritative.

The public docs may show example endpoints, but examples are not the contract. OpenAPI defines paths, methods, parameters, and response schemas. Private overlays may not invent endpoints.

## Why Dedicated Endpoints Stay

The project intentionally keeps device actions as dedicated routes such as `POST /api/garage/{door}/toggle` and `POST /api/wemo/{device}/on`.

This is less abstract than a generic `/api/actions/execute`, but it is better for this domain:

1. Logs reveal the physical action without parsing a payload.
2. curl, Shortcuts, Flic, and dashboard calls are easy to debug.
3. OpenAPI displays concrete path/method combinations.
4. Sensitive actions can have route-specific method rules and documentation.

A future generic facade can be added if audit policy or cross-device permissions require it. It should wrap dedicated endpoints rather than replace them.

## Public/Private Overlay Split

Public repo responsibilities:

1. Runtime code and tests.
2. OpenAPI metadata and Pydantic schemas.
3. Safe example configuration.
4. Public AI skill workflow.

Private overlay responsibilities:

1. Natural-language aliases for this household.
2. Preferred defaults such as which door or switch a phrase means.
3. Safety constraints and confirmation expectations.
4. Credentials, notification recipients, and local device addresses.

Rule: **OpenAPI defines what can be called. Private overlay defines what should be called here.**

## Backend Structure

| Area | Files | Responsibility |
|---|---|---|
| App entrypoint | `main.py` | FastAPI app, lifespan startup, static frontend serving |
| Routes | `api/*.py` | Dedicated API endpoints and OpenAPI metadata |
| Schemas | `models/schemas.py` | API-facing Pydantic models for OpenAPI |
| Persistence | `models/database.py` | SQLite history storage |
| Device adapters | `services/*_service.py` | Integration-specific control and status logic |
| Scheduling | `services/dynamic_scheduler.py`, `services/scheduler.py` | Delayed actions and recurring state collection |
| Visual checks | `services/visual_check_service.py`, `api/visual_check.py`, `scripts/visual_check.py` | Camera snapshot inspection through a local vision model with schema validation |
| Ring status spike | `scripts/ring_client_status.mjs`, `config/ring_client_status.example.json` | Read-only Ring Alarm sensor status pull through `ring-client-api` |

## Device Integration Notes

Hue uses the local bridge through `phue`. The bridge pairing token is managed by the library and should not be committed.

Wemo uses private `config/wemo_config.yaml` for stable local addresses. Auto-discovery is still available through scripts and stale-device rediscovery logic.

Rinnai uses cloud credentials and may fail independently of local devices. Aggregate status endpoints isolate device failures instead of failing the whole status request.

Meross garage control uses cloud login to discover the device, signing key, and LAN address, then atomically caches those local connection fields in a gitignored `0600` file. On an internet-offline cold start, the service restores that cache and continues using local HTTP `/config` with Meross signatures. Door state is not treated as authoritative when the physical sensor is absent or unreliable.

Camera snapshots are proxied on demand. Images are not stored by the backend.

Ring Alarm sensor status is currently a read-only spike. The data path is Ring sensor → Ring Alarm Base Station → Ring cloud / Ring app API → `ring-client-api` → local JSON output. The script does not read the Base Station over LAN, does not join the Z-Wave network, and does not perform Ring control actions. `ring-mqtt` uses the same underlying API family, so MQTT is treated as an optional bridge/runtime layer rather than a more authoritative data source.

Samsung TV uses the local Tizen WebSocket API on `wss://TV_IP:8002`. This replaces the previous SmartThings cloud PAT implementation, which suffered from a 24-hour token expiration policy. The local token is a one-time device credential stored in `data/samsung_tv_ws_token.txt` (gitignored); it does not expire. First-run pairing requires the user to press "Allow" on the TV screen. Each key event opens a fresh WebSocket connection because Tizen resets connections that send multiple keys in quick succession. `power_on` and `power_off` query `PowerState` via the REST device-info endpoint before sending `KEY_POWER` (which is a toggle). Volume and mute state are not readable via the local protocol; `get_status` returns `null` for those fields.

The Ring spike rotates refresh tokens back into the ignored private config file by default when the token came from that file. Public examples must not contain real refresh tokens, location IDs, device IDs, room IDs, sensor names, or raw Ring output.

Visual checks consume camera snapshots or configured HTTP snapshot URLs, call an OpenAI-compatible local LM Studio endpoint, validate the model response against a configured JSON Schema, and save per-run artifacts under an ignored data directory. The HTTP endpoint and CLI are thin wrappers over `VisualCheckService`; they do not duplicate prompt, validation, retry, or artifact logic.

Prompt files and JSON Schema files are intentionally separate. Prompts describe visual interpretation rules, including local camera perspective conventions. Schemas define the machine contract consumed by automations and tests. Assertions are deterministic post-processing rules over the validated JSON, such as `$.overall.any_door_open == false`.

The system does not maintain authoritative derived state for camera-observed objects. A visual check result is a timestamped observation. Nightly jobs or post-action verification should run a fresh check instead of reading a cached door state.

Measurement sets are part of the design. Public fixtures use synthetic images plus ground truth JSON so CI can demonstrate evaluation mechanics without exposing a real home. Private deployments should keep real camera images and local ground truth under ignored paths such as `data/visual_checks/measurement_sets/`.

## Startup and macOS Local Network Permissions

On macOS, Local Network permission may depend on the launch chain. This service should run through a foreground-capable process launcher rather than PM2. `start_server.sh` activates the virtual environment, resolves a Resend `op://` reference at startup when present, and starts `python main.py`.

## Garage Notifications

Garage notifications are optional. When enabled, `services/notification_service.py` sends a Resend email after a successful garage trigger. Notification failure does not roll back or block the physical action; the API response reports the notification result.

## API Compatibility

This cleanup improves OpenAPI metadata without changing the core runtime API. Some query/path parameters now use FastAPI validation bounds so invalid inputs return 422 instead of being clamped silently.
