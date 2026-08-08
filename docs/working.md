# Working Log

## Current Direction

The project is being reframed from a Hue-oriented dashboard into `smart_home_skill`: a local, AI-facing control layer with a lightweight dashboard. The runtime API stays dedicated and explicit. Live OpenAPI becomes the source of truth for agents, and private overlays provide household-specific semantics.

## Changelog

### 2026-08-08

- Control tab: replaced global full-screen spinner with per-section loading spinners. Each device section (Lights, Switches, Samsung TV, Garage, Contact sensors, Water heater) now independently shows a local spinner while its data is loading, instead of blocking the entire tab behind one global spinner. The store's `loading: boolean` was replaced with `loadingKeys: Set<DeviceKey>` + `isLoading(key)` selector so concurrent fetch calls no longer overwrite each other's loading state.
- Added `ControlTab.test.tsx` (4 tests) and expanded `deviceStore.test.ts` (14 tests) covering per-key loading, concurrent fetch, and error cleanup.

### 2026-07-31

- 将 Ring nightly sensor check 调研从 `contexts/thought_review/` 迁入 `docs/ring_nightly_sensor_check_research.md`，使实现建议与现有 Ring spike、nightly visual check 架构放在同一项目内。

### 2026-07-30

- Replaced Samsung TV control from SmartThings cloud PAT to local Tizen WebSocket API (wss://TV_IP:8002). Eliminates the 24-hour PAT expiration problem entirely.
- One-time pairing: connect to 8002, approve on TV screen, store device-local token in `data/samsung_tv_ws_token.txt`. Token does not expire.
- `samsung_service.py` rewritten: each key event opens a fresh WS connection (Tizen resets connections that send multiple keys in quick succession). `power_on`/`power_off` check status first to avoid toggling. `get_status` returns `PowerState` from the REST device-info endpoint; volume/mute are not readable via the local protocol.
- Tested on Samsung QN900C 65" (QN65QN900CFXZA, Neo QLED 8K, 2022 Tizen). Power on/off, volume up/down, and mute all verified working.
- Upgraded project venv from Python 3.9 to 3.12.
- Added `websockets>=12.0` dependency.
- Added `test/test_samsung.py` (17 tests, all passing).
