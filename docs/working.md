# Working Log

## Current Direction

The project is being reframed from a Hue-oriented dashboard into `smart_home_skill`: a local, AI-facing control layer with a lightweight dashboard. The runtime API stays dedicated and explicit. Live OpenAPI becomes the source of truth for agents, and private overlays provide household-specific semantics.

## Changelog

### 2026-07-30

- Replaced Samsung TV control from SmartThings cloud PAT to local Tizen WebSocket API (wss://TV_IP:8002). Eliminates the 24-hour PAT expiration problem entirely.
- One-time pairing: connect to 8002, approve on TV screen, store device-local token in `data/samsung_tv_ws_token.txt`. Token does not expire.
- `samsung_service.py` rewritten: each key event opens a fresh WS connection (Tizen resets connections that send multiple keys in quick succession). `power_on`/`power_off` check status first to avoid toggling. `get_status` returns `PowerState` from the REST device-info endpoint; volume/mute are not readable via the local protocol.
- Tested on Samsung QN900C 65" (QN65QN900CFXZA, Neo QLED 8K, 2022 Tizen). Power on/off, volume up/down, and mute all verified working.
- Upgraded project venv from Python 3.9 to 3.12.
- Added `websockets>=12.0` dependency; relaxed `websocket-client` to `>=1.4.0` (roonapi requires it).
- Added `test/test_samsung.py` (17 tests, all passing).

### Lessons Learned (Samsung Local WS)

- **QN900C shallow standby keeps port 8002 alive.** After `KEY_POWER` powers off the TV, the REST endpoint briefly returns empty `PowerState` (~3s), then returns `standby`. The port stays reachable. `KEY_POWER` from standby turns it back on. Wake-on-LAN is not needed for this model.
- **KEY_POWER is a toggle, not absolute on/off.** `power_on`/`power_off` must query `PowerState` first and only send the key if the current state differs from the target.
- **Volume is not readable.** The Tizen WS protocol sends key events (`KEY_VOLUP`, `KEY_VOLDOWN`, `KEY_MUTE`) but does not return current volume or mute state. `get_status` reports `volume: null, muted: null` — this is a protocol limitation, not a bug.
- **One key per connection.** Sending multiple keys on a single WS connection triggers `ConnectionResetError`. Each `_send_key` call opens a new connection, sends one key, and closes.
- **Power commands have multi-second latency.** The TV takes 2-5 seconds to actually change state after `KEY_POWER`. `power_on`/`power_off` wait `POWER_SETTLE_SECONDS` before returning.
- **Transient empty PowerState.** Right after a power command, the REST endpoint returns an empty string instead of `on`/`standby`. `get_status` treats this as `is_on: null` (unknown).

- Added Roon integration via `roonapi==0.1.6`: pair flow, zone list, play queue/playlist, pause/stop/playpause, and local sleep timer (Roon has no native sleep-timer API).
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
