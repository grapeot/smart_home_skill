# Smart Home Skill

Chinese version: [README_zh.md](README_zh.md)

Smart Home Skill is a local, AI-facing control layer for real smart home devices. It exposes dedicated HTTP APIs, live OpenAPI documentation, and a lightweight dashboard so agents can operate household systems through the same deployed configuration that humans use.

The core contract is simple: **OpenAPI defines what can be called; private overlays define what should be called in this home.**

## What It Controls

| Integration | Role |
|---|---|
| Hue | Local light status and control through `phue` |
| Wemo | Local switch status/control through `pywemo` and private device config |
| Rinnai | Water heater status and recirculation through `aiorinnai` |
| Meross | Garage door trigger through local HTTP `/config`; cloud credentials are used only to discover the local device and signing key |
| Amcrest | Local camera snapshot proxy through Digest Auth |
| Visual Check | Camera snapshot + local LM Studio vision model for schema-validated visual state checks |

## Design Principles

1. **OpenAPI is the public source of truth.** Agents should fetch `GET /openapi.json` from the running service before selecting an endpoint. README snippets are examples, not the authority.
2. **Runtime APIs stay dedicated and debuggable.** Actions remain visible endpoints such as `POST /api/garage/{door}/toggle`, not a generic `/execute` RPC with hidden intent in the payload.
3. **Private overlays carry household semantics.** Device aliases, local IPs, credentials, notification recipients, safety preferences, and common natural-language mappings stay outside the public repo.
4. **Physical actions are treated differently from software state.** Garage toggles use POST only and can send notifications after successful triggers.
5. **The dashboard is secondary.** The UI is a human observability/debug surface. The primary product is the agent-readable local control layer.

## Public/Private Layout

The public repo contains reusable code, schemas, docs, tests, and safe examples.

Local deployments add private state:

| Local file or overlay | Purpose | Git status |
|---|---|---|
| `.env` | Credentials, ports, Resend notification config | ignored |
| `config/wemo_config.yaml` | Real Wemo device names and local IPs | ignored |
| `config/cameras.yaml` | Real camera names and local IPs | ignored |
| Workspace private skill overlay | Natural-language aliases, default devices, safety notes, household policy | outside this public repo |

The private overlay should not duplicate the full API. It should point agents to live OpenAPI and add only the local semantics OpenAPI cannot know.

## Agent Workflow

Before calling a device API, an agent should:

1. Confirm the service is healthy: `GET /health`.
2. Fetch the live schema: `GET /openapi.json`.
3. Use private overlay notes only for name mapping, safety policy, and local defaults.
4. Double-check that the selected endpoint and method exist in OpenAPI.
5. Call the dedicated endpoint.
6. Inspect the response, especially `status`, `error`, and `notification` fields for sensitive actions.

Example garage flow:

```bash
curl -sS http://localhost:7999/openapi.json >/tmp/smart_home_openapi.json
curl -sS -X POST http://localhost:7999/api/garage/2/toggle
```

## Quick Start

```bash
cd smart_home
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp config/wemo_config.example.yaml config/wemo_config.yaml
cp config/cameras.example.yaml config/cameras.yaml
```

Edit the private files for your home. Do not commit them.

Build the frontend and start the backend:

```bash
./scripts/build-frontend.sh
./scripts/start-backend.sh
```

For production on macOS, prefer a foreground process launcher that inherits Local Network permission. This workspace uses Process Launcher to run `./start_server.sh`. Avoid PM2 for this service on macOS; Local Network permission can depend on the launch chain.

## API Discovery

FastAPI serves the live schema and interactive docs:

| URL | Purpose |
|---|---|
| `/openapi.json` | Machine-readable API contract for agents |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc UI |
| `/health` | Service health check |

Common dedicated endpoints include:

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | Aggregate device status; supports `?devices=hue,wemo,rinnai,garage` |
| `GET /api/hue/status` | Hue status |
| `GET /api/wemo/status` | Wemo status |
| `GET /api/rinnai/status` | Rinnai status |
| `POST /api/garage/{door}/toggle` | Sensitive garage trigger through Meross local HTTP |
| `GET /api/history?hours=24` | Recent device history |
| `GET /api/cameras` | Configured camera list |
| `GET /api/visual-checks` | Configured visual checks |
| `POST /api/visual-checks/{check_id}/run` | Run one visual check |

Treat this table as orientation only. Use `/openapi.json` for the live contract.

## Visual Checks

`visual_check` turns camera observations into structured JSON. It is useful for states where sensors are unavailable or unreliable, such as a garage door or side gate. The implementation is generic: local deployments configure the snapshot source, prompt, output JSON Schema, retry policy, and assertions.

CLI examples:

```bash
python scripts/visual_check.py list
python scripts/visual_check.py --json run example_garage
python scripts/visual_check.py --json run-all --group nightly
```

Copy `config/vision_checks.example.yaml` to ignored `config/vision_checks.yaml` and replace example camera ids, prompts, schemas, and model settings. Public fixtures under `test/fixtures/visual_check/` demonstrate the measurement-set pattern with synthetic images and ground truth JSON. Real camera measurement sets should stay under ignored `data/visual_checks/measurement_sets/`.

## Optional Garage Notifications

Garage door triggers can send email through Resend after a successful toggle. The feature is disabled unless all required settings are present and `GARAGE_NOTIFY_ENABLED=true`.

```dotenv
GARAGE_NOTIFY_ENABLED=true
GARAGE_NOTIFY_RECIPIENTS=you@example.com;alerts@example.com
RESEND_API_KEY=op://your-vault/your-item/resend_api_key
RESEND_FROM_EMAIL="Smart Home <notifications@example.com>"
```

`GARAGE_NOTIFY_RECIPIENTS` supports comma or semicolon separated addresses. `RESEND_API_KEY` may be a resolved key or a 1Password `op://...` secret reference; `start_server.sh` resolves that reference at startup.

## Tests

```bash
source .venv/bin/activate
python -m pytest test/ -q --ignore=test/test_integration_real.py

cd frontend
npm test -- --run
npm run build
```

See [docs/test.md](docs/test.md) for the full test strategy.

## Documentation

| File | Purpose |
|---|---|
| [docs/prd.md](docs/prd.md) | Product framing and requirements |
| [docs/rfc.md](docs/rfc.md) | Architecture and design decisions |
| [docs/test.md](docs/test.md) | Test strategy and commands |
| [docs/working.md](docs/working.md) | Development log and lessons learned |
| [skills/smart_home_skill.md](skills/smart_home_skill.md) | Public AI skill instructions |
