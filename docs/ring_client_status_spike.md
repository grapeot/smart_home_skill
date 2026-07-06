# Ring Client API Status Spike

This is a minimal read-only spike for pulling Ring Alarm device status without MQTT.

The data path is:

```text
Ring Contact/Motion Sensor
  -> Ring Alarm Base Station
  -> Ring cloud / Ring app API
  -> ring-client-api
  -> scripts/ring_client_status.mjs JSON output
```

It does not read the Base Station over LAN, and it does not directly read Z-Wave radio traffic. The Base Station remains the hub for Ring sensors; this script reads the state synchronized to Ring's cloud API.

## Install

```bash
npm install
```

## Login

Generate a Ring refresh token:

```bash
npm run ring:auth
```

The CLI prompts for Ring email, password, and 2FA code, then prints:

```json
"refreshToken": "..."
```

Store that token locally. Do not commit it.

Option 1: one-off environment variable:

```bash
RING_REFRESH_TOKEN='paste-token-here' npm run ring:status
```

Option 2: private config file:

```bash
cp config/ring_client_status.example.json config/ring_client_status.json
```

Then paste the token into `config/ring_client_status.json`. This file is ignored by git.

## Pull Status

```bash
npm run ring:status
```

The script outputs JSON with alarm-related devices only: Base Station, Security Panel, Keypad, Contact Sensor, Motion Sensor, range extenders, and other alarm sensors.

This command is pull-only. It should exit after printing JSON; it is not intended to keep monitoring. `ring-client-api` opens sockets/push listeners during discovery, so the script exits explicitly after cleanup.

Useful debug options:

```bash
node scripts/ring_client_status.mjs --include-raw
node scripts/ring_client_status.mjs --all-devices
node scripts/ring_client_status.mjs --print-refresh-token
node scripts/ring_client_status.mjs --save-refresh-token
node scripts/ring_client_status.mjs --no-save-refresh-token
```

`--print-refresh-token` prints an updated refresh token to stderr if Ring rotates it during the request. If that happens, update the private config or 1Password item. The normal JSON output only says whether an updated token is available; it does not print the token.

By default, the script writes the updated token back to `--config` when the token came from the config file. It refuses to write when `RING_REFRESH_TOKEN` was used, because the real secret source is then outside the config file. Use `--no-save-refresh-token` to disable config writeback for a run.

## Interpreting Output

For contact sensors, `faulted=true` is treated as `derived_state=open_or_faulted`; `faulted=false` is treated as `derived_state=closed_or_clear`. Keep the raw `faulted`, `tamper_status`, `comm_status`, `battery_level`, and timestamps in the nightly decision. Do not collapse the result into a single authoritative open/closed boolean.

For the first run, use `--include-raw` and manually inspect the real fields returned by Ring. Different Ring devices may expose slightly different field names.

## MVP Acceptance Criteria

1. The script logs in with a refresh token and returns at least one location.
2. The location has `has_alarm_base_station=true`.
3. Contact sensors appear with names matching Ring app device names.
4. Opening/closing one sensor changes `faulted` or another raw state field.
5. The output includes enough freshness fields to detect stale state, such as `last_update`, `last_comm_time`, or raw equivalents.

## Known Risk

This still depends on an unofficial Ring cloud API. `ring-mqtt` uses the same underlying API family and currently depends on a forked/custom `@tsightler/ring-client-api`. MQTT mainly adds a bridge/runtime layer, not a fundamentally different data source.
