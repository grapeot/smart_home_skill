#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { pathToFileURL } from 'node:url'
import { RingApi, RingDeviceType } from 'ring-client-api'

export const ALARM_DEVICE_TYPES = new Set([
  RingDeviceType.BaseStation,
  RingDeviceType.BaseStationPro,
  RingDeviceType.SecurityPanel,
  RingDeviceType.Keypad,
  RingDeviceType.ContactSensor,
  RingDeviceType.MotionSensor,
  RingDeviceType.FloodFreezeSensor,
  RingDeviceType.FreezeSensor,
  RingDeviceType.TemperatureSensor,
  RingDeviceType.WaterSensor,
  RingDeviceType.TiltSensor,
  RingDeviceType.GlassbreakSensor,
  RingDeviceType.RangeExtender,
  RingDeviceType.SmokeAlarm,
  RingDeviceType.CoAlarm,
  RingDeviceType.SmokeCoListener,
  RingDeviceType.PanicButton,
])

const HELP_TEXT = `Usage: node scripts/ring_client_status.mjs [options]

Options:
  --config <path>          Config JSON path. Default: config/ring_client_status.json
  --include-raw            Include raw ring-client-api device data in JSON output
  --all-devices            Include non-alarm devices too
  --print-refresh-token    Print updated refresh token to stderr if Ring rotates it
  --save-refresh-token     Save updated refresh token back to --config path (default)
  --no-save-refresh-token  Do not save updated refresh token

Authentication:
  Set RING_REFRESH_TOKEN, or create config/ring_client_status.json from
  config/ring_client_status.example.json.
`

export function parseArgs(argv) {
  const options = {
    config: 'config/ring_client_status.json',
    includeRaw: false,
    allDevices: false,
    printRefreshToken: false,
    saveRefreshToken: true,
  }

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--config') options.config = argv[++i]
    else if (arg === '--include-raw') options.includeRaw = true
    else if (arg === '--all-devices') options.allDevices = true
    else if (arg === '--print-refresh-token') options.printRefreshToken = true
    else if (arg === '--save-refresh-token') options.saveRefreshToken = true
    else if (arg === '--no-save-refresh-token') options.saveRefreshToken = false
    else if (arg === '--help' || arg === '-h') {
      options.help = true
    } else {
      throw new Error(`Unknown argument: ${arg}`)
    }
  }

  return options
}

export function saveUpdatedRefreshToken(configPath, config, newRefreshToken) {
  const nextConfig = {
    ...config,
    refreshToken: newRefreshToken,
  }
  const tmpPath = `${configPath}.tmp`
  fs.mkdirSync(path.dirname(configPath), { recursive: true })
  fs.writeFileSync(tmpPath, `${JSON.stringify(nextConfig, null, 2)}\n`, { mode: 0o600 })
  fs.renameSync(tmpPath, configPath)
}

export function loadConfig(configPath) {
  if (!fs.existsSync(configPath)) return {}
  return JSON.parse(fs.readFileSync(configPath, 'utf8'))
}

export function withTimeout(promise, ms, label) {
  let timer
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms)
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer))
}

export function compactDevice(device, includeRaw) {
  const data = device.data || {}
  const deviceType = data.deviceType || data.kind || 'unknown'
  const faulted = data.faulted
  let derivedState = 'unknown'

  if (deviceType === RingDeviceType.ContactSensor) {
    derivedState = faulted === true ? 'open_or_faulted' : faulted === false ? 'closed_or_clear' : 'unknown'
  } else if (deviceType === RingDeviceType.MotionSensor) {
    derivedState = faulted === true ? 'motion_or_faulted' : faulted === false ? 'clear' : 'unknown'
  } else if (typeof faulted === 'boolean') {
    derivedState = faulted ? 'faulted' : 'clear'
  }

  const result = {
    id: data.zid || device.id || null,
    name: data.name || device.name || null,
    device_type: deviceType,
    category_id: data.categoryId ?? null,
    faulted: faulted ?? null,
    derived_state: derivedState,
    tamper_status: data.tamperStatus ?? null,
    comm_status: data.commStatus ?? null,
    battery_level: data.batteryLevel ?? null,
    battery_status: data.batteryStatus ?? null,
    last_update: data.lastUpdate ?? null,
    last_comm_time: data.lastCommTime ?? null,
    room_id: data.roomId ?? null,
    parent_zid: data.parentZid ?? null,
  }

  if (includeRaw) result.raw = data
  return result
}

export async function main() {
  const args = parseArgs(process.argv.slice(2))
  if (args.help) {
    console.log(HELP_TEXT)
    return
  }
  const config = loadConfig(args.config)
  const refreshToken = process.env.RING_REFRESH_TOKEN || config.refreshToken

  if (!refreshToken) {
    throw new Error('Missing refresh token. Run `npm run ring:auth`, then set RING_REFRESH_TOKEN or config/ring_client_status.json.')
  }

  const timeoutMs = Number(process.env.RING_STATUS_TIMEOUT_MS || config.timeoutMs || 30000)
  const locationIds = process.env.RING_LOCATION_IDS
    ? process.env.RING_LOCATION_IDS.split(',').map((x) => x.trim()).filter(Boolean)
    : Array.isArray(config.locationIds) && config.locationIds.length
      ? config.locationIds
      : undefined
  const includeRaw = args.includeRaw || config.includeRaw === true
  const allDevices = args.allDevices || config.allDevices === true
  let updatedRefreshToken = null

  const ringApi = new RingApi({
    refreshToken,
    locationIds,
    controlCenterDisplayName: 'smart-home-ring-status-spike',
  })
  ringApi.onRefreshTokenUpdated.subscribe(({ newRefreshToken }) => {
    updatedRefreshToken = newRefreshToken
  })

  try {
    const locations = await withTimeout(ringApi.getLocations(), timeoutMs, 'getLocations')
    const locationResults = []

    for (const location of locations) {
      const devices = await withTimeout(location.getDevices(), timeoutMs, `getDevices(${location.name})`)
      const filteredDevices = devices.filter((device) => {
        return allDevices || ALARM_DEVICE_TYPES.has((device.data || {}).deviceType)
      })
      locationResults.push({
        id: location.id,
        name: location.name,
        has_hubs: location.hasHubs,
        has_alarm_base_station: location.hasAlarmBaseStation,
        devices: filteredDevices.map((device) => compactDevice(device, includeRaw)),
      })
    }

    const output = {
      schema_version: 'smart_home.ring_client_status.v0',
      source: 'ring-client-api',
      observed_at: new Date().toISOString(),
      locations: locationResults,
      updated_refresh_token_available: Boolean(updatedRefreshToken && updatedRefreshToken !== refreshToken),
    }

    console.log(JSON.stringify(output, null, 2))
    if (args.printRefreshToken && updatedRefreshToken && updatedRefreshToken !== refreshToken) {
      console.error(`UPDATED_REFRESH_TOKEN=${updatedRefreshToken}`)
    }
    if (args.saveRefreshToken && updatedRefreshToken && updatedRefreshToken !== refreshToken) {
      if (process.env.RING_REFRESH_TOKEN) {
        console.error('Updated refresh token was not saved because RING_REFRESH_TOKEN was used. Use --print-refresh-token and update your secret store manually.')
      } else {
        saveUpdatedRefreshToken(args.config, config, updatedRefreshToken)
        console.error(`Saved updated refresh token to ${args.config}`)
      }
    }
  } finally {
    ringApi.disconnect()
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main()
    .then(() => {
      // ring-client-api opens sockets/push listeners while discovering alarm devices.
      // This spike is pull-only, so exit explicitly after cleanup instead of monitoring.
      process.exit(0)
    })
    .catch((error) => {
      console.error(JSON.stringify({ error: error.message }, null, 2))
      process.exit(1)
    })
}
