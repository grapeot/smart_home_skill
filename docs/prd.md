# Product Requirements: Smart Home Skill

## Product Positioning

Smart Home Skill is a local, AI-facing control layer for real household devices. It is not primarily a dashboard. The dashboard exists so humans can observe and debug the same system that agents use.

The product succeeds when an agent can hear a household command such as "turn on the coffee maker" or "toggle garage door 2", resolve it through private household semantics, verify the live API contract through OpenAPI, and call the correct dedicated endpoint without guessing.

Unlike many AI skills in this workspace, this project is intentionally not CLI-only. Smart home control has two interaction modes. Natural language is useful for intent-heavy requests such as "turn this off in 30 minutes" or "start the water heater circulation". But physical buttons, iOS Shortcuts, Apple Watch actions, and Siri shortcuts need a low-latency always-on HTTP surface. A Flic button or phone shortcut should not have to open an AI chat, wait for model latency, and route through a CLI process just to trigger a household action. The web server exists to make those direct integrations reliable while still giving AI agents an OpenAPI-readable control layer.

## Users

| User | Need |
|---|---|
| AI agent | Discover current capabilities, map natural language to real devices, and safely call explicit endpoints |
| Home operator | Keep local device configuration private while exposing enough semantics for agents to act reliably |
| Physical/shortcut trigger | Call low-latency HTTP endpoints directly from Flic, iOS Shortcuts, Apple Watch, Siri, or similar surfaces |
| Developer/maintainer | Debug device integrations through stable routes, tests, logs, and OpenAPI |
| Human dashboard user | Quickly check status and trigger common actions when needed |

## Core Requirements

1. The running service must expose `GET /openapi.json` as the machine-readable source of truth for callable APIs.
2. The public repo must not contain real household IPs, credentials, notification addresses, routines, or private aliases.
3. Private overlays must provide local semantics: aliases, default devices, safety notes, and household-specific policy.
4. Device actions must remain dedicated endpoints so logs, curl commands, browser docs, and tests stay easy to debug.
5. Physical actions must be explicit. Garage door toggles use `POST` only and report notification results when notifications are enabled.
6. The dashboard must remain lightweight and same-origin with the FastAPI backend.
7. The service must stay available as an always-on local HTTP server so non-AI triggers can call it directly.

## Supported Device Classes

| Device class | Current implementation | Required behavior |
|---|---|---|
| Lights | Hue via local bridge | Status, on, off, brightness, toggle |
| Switches | Wemo via local config/discovery | Status, on, off, toggle |
| Water heater | Rinnai cloud API | Status, recirculation, schedule readout |
| Garage doors | Meross local HTTP `/config` | Trigger/toggle, no false promise of authoritative door position |
| Cameras | Amcrest local snapshot proxy | List cameras and fetch snapshots without storing images |
| Visual checks | Camera snapshot + local LM Studio vision model | Convert visual household state into schema-validated JSON with artifacts and assertions |
| Ring Alarm status spike | `ring-client-api` read-only pull | Fetch Ring Alarm sensor telemetry without MQTT or physical actions |

## Visual Check Requirements

Some household states are easier to observe with a camera than with a brittle physical sensor. Garage doors, side gates, and backyard doors are examples: the automation needs a reliable structured answer, not a raw image.

`visual_check` is the generic subsystem for this. It must:

1. Run from both HTTP and CLI surfaces, with both wrappers sharing the same service implementation.
2. Treat prompt and output JSON Schema as separate configuration files.
3. Validate model output against JSON Schema and retry with validation feedback when the first response is malformed.
4. Save artifacts for audit: input image, raw model response, and normalized result JSON.
5. Support measurement sets. Public fixtures demonstrate the method with synthetic images and ground truth; private real-camera measurement sets stay under ignored paths.
6. Avoid maintaining long-lived derived state. A visual result is a point-in-time observation and becomes stale unless a new check runs.
7. Keep physical corrective actions outside `visual_check`. Garage toggle workflows may call visual checks for post-action verification, but visual checks do not trigger devices by themselves.

## Non-Goals

1. This project is not a Home Assistant replacement.
2. This project should not become a generic `/execute` RPC where all intent is hidden in a payload.
3. Public docs should not describe one real home's topology or routines.
4. Private overlays should not copy the full OpenAPI schema.
5. The Ring spike is not a Ring control surface. It must not arm, disarm, sound sirens, bypass sensors, or mutate Ring devices.

## Privacy Requirements for Ring Status

Ring status contains household presence data. Public files may include only synthetic sensor names, example config keys, and shape-level JSON. Real Ring refresh tokens, location IDs, device IDs, room IDs, sensor names, and raw output belong in ignored local files or operator logs.

The public example config is `config/ring_client_status.example.json`. The private runtime config is `config/ring_client_status.json`, which is ignored by git. Token writeback is allowed only to the ignored private config file or to an explicitly managed local secret store.

## Success Criteria

1. A fresh agent can use public docs to learn the workflow without seeing private household details.
2. A local agent can combine live OpenAPI and private overlay notes to select the correct endpoint.
3. Public examples use RFC 5737 example IPs and fake credentials only.
4. Visual check examples use synthetic or mock images only; real camera fixtures remain ignored.
5. Ring examples and tests use synthetic device names and IDs only.
6. Backend tests, frontend tests, frontend build, Node tests, and privacy scans pass before release.
