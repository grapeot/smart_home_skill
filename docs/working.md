# Working Log

## Current Direction

The project is being reframed from a Hue-oriented dashboard into `smart_home_skill`: a local, AI-facing control layer with a lightweight dashboard. The runtime API stays dedicated and explicit. Live OpenAPI becomes the source of truth for agents, and private overlays provide household-specific semantics.

## Changelog

### 2026-07-30

- Added Roon integration via `roonapi==0.1.6`: pair flow, zone list, play queue/playlist, pause/stop/playpause, and local sleep timer (Roon has no native sleep-timer API).
- Added kids-music ticket API for M5Paper: daily plays (default 2 × 15 min), playlist `k-pop`, zone `bedroom`, Pacific day boundary at 04:00.
- Agent setup: `POST /api/roon/pair/start` → user Enables extension → poll `/api/roon/pair/status` → `/api/roon/zones`.
- Scheduled actions gained `roon.play`, `roon.pause`, `roon.stop`.

### 2026-07-18

- Added configurable LM Studio chat-template arguments so visual checks can disable Qwen reasoning and preserve the token budget for schema-constrained JSON.
- Updated the private nightly check to return a non-zero exit status when a visual check fails or reports an open door or gate.

### 2026-06-25

- Switched garage control to POST-only semantics.
- Added optional Resend notifications after successful garage toggles.
- Moved garage control to Meross local HTTP `/config` for the physical trigger path.
- Updated `start_server.sh` to resolve a Resend `op://` secret reference at startup rather than on each action.

### 2026-02-20

- Added post-action state collection after device control.
- Hue and Wemo state collection runs after a short delay; Rinnai uses a longer delay.
- The collector complements recurring scheduled status collection.

### 2026-02-19

- Added a dynamic delayed-action scheduler with `POST/GET/DELETE /api/schedule/actions`.
- Added camera preview support through local Amcrest snapshot proxying.
- Added mobile-friendly tab labels and responsive camera layout.
- Added private config ignores for camera and Wemo configuration.

### 2026-02-18

- Consolidated Hue, Wemo, Rinnai, Meross, history storage, scheduling, and frontend UI into one FastAPI/React service.
- Added device-specific services under `services/` and API routers under `api/`.
- Added SQLite history storage.
- Added FastAPI static serving for the built frontend.
- Added Process Launcher deployment guidance for macOS Local Network permission compatibility.
- Added robust status aggregation so one failing integration does not fail the full `/api/status` response.
- Added Wemo config migration to `config/wemo_config.yaml` and private git ignores.
- Added tests for services, APIs, dynamic scheduling, frontend store logic, and integration paths.

## Lessons Learned

### Meross Garage Door State Is Not Always Authoritative

MSG200 garage openers may require a magnetic sensor for reliable door state. Without a reliable sensor, the API should describe garage actions as triggers/toggles rather than absolute open/close state.

### Garage Door Actions Need POST Semantics

Garage door triggers are sensitive physical actions. They should not be exposed as GET toggles. The current contract is `POST /api/garage/{door}/toggle`.

### macOS Local Network Permission Depends on Launch Chain

Hue, Wemo, Meross, and camera integrations depend on local network access. PM2 or other background supervisors may not inherit the right macOS Local Network permission context. Use Process Launcher or another foreground-capable launch chain for production on macOS.

### Do Not Source `.env` in Shell

Values such as `HUE_LIGHT_NAME=Baby room` can break shell parsing when sourced directly. Let Python `load_dotenv()` load `.env`; `start_server.sh` only handles the narrow startup secret-resolution case for `RESEND_API_KEY`.

### Aggregate Status Should Degrade Gracefully

Any single device integration can fail because of cloud auth, local network reachability, or vendor API changes. `/api/status` should return partial results with error fields rather than fail the entire aggregate request.
