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
- Added `websockets>=12.0` dependency.
- Added `test/test_samsung.py` (17 tests, all passing).

### Lessons Learned (Samsung Local WS)

- **QN900C shallow standby keeps port 8002 alive.** After `KEY_POWER` powers off the TV, the REST endpoint briefly returns empty `PowerState` (~3s), then returns `standby`. The port stays reachable. `KEY_POWER` from standby turns it back on. Wake-on-LAN is not needed for this model.
- **KEY_POWER is a toggle, not absolute on/off.** `power_on`/`power_off` must query `PowerState` first and only send the key if the current state differs from the target.
- **Volume is not readable.** The Tizen WS protocol sends key events (`KEY_VOLUP`, `KEY_VOLDOWN`, `KEY_MUTE`) but does not return current volume or mute state. `get_status` reports `volume: null, muted: null` — this is a protocol limitation, not a bug.
- **One key per connection.** Sending multiple keys on a single WS connection triggers `ConnectionResetError`. Each `_send_key` call opens a new connection, sends one key, and closes.
- **Power commands have multi-second latency.** The TV takes 2-5 seconds to actually change state after `KEY_POWER`. `power_on`/`power_off` wait `POWER_SETTLE_SECONDS` before returning.
- **Transient empty PowerState.** Right after a power command, the REST endpoint returns an empty string instead of `on`/`standby`. `get_status` treats this as `is_on: null` (unknown).
