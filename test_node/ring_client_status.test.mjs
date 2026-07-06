import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import {
  compactDevice,
  loadConfig,
  parseArgs,
  saveUpdatedRefreshToken,
  withTimeout,
} from '../scripts/ring_client_status.mjs'

test('parseArgs defaults to private config and token writeback', () => {
  assert.deepEqual(parseArgs([]), {
    config: 'config/ring_client_status.json',
    includeRaw: false,
    allDevices: false,
    printRefreshToken: false,
    saveRefreshToken: true,
  })
})

test('parseArgs supports debug and no-writeback options', () => {
  assert.deepEqual(parseArgs([
    '--config', '/tmp/ring.json',
    '--include-raw',
    '--all-devices',
    '--print-refresh-token',
    '--no-save-refresh-token',
  ]), {
    config: '/tmp/ring.json',
    includeRaw: true,
    allDevices: true,
    printRefreshToken: true,
    saveRefreshToken: false,
  })
})

test('compactDevice maps contact sensor states without raw data by default', () => {
  const result = compactDevice({
    data: {
      zid: 'sensor-1',
      name: 'Example Contact Sensor',
      deviceType: 'sensor.contact',
      categoryId: 5,
      faulted: true,
      tamperStatus: 'ok',
      commStatus: 'ok',
      batteryLevel: 90,
      batteryStatus: 'full',
      lastUpdate: 123,
      lastCommTime: 120,
      roomId: 2,
      parentZid: null,
      serialNumber: 'should-not-leak-without-raw',
    },
  }, false)

  assert.equal(result.derived_state, 'open_or_faulted')
  assert.equal(result.faulted, true)
  assert.equal(result.name, 'Example Contact Sensor')
  assert.equal(result.serialNumber, undefined)
  assert.equal(result.raw, undefined)
})

test('compactDevice maps motion and clear generic states', () => {
  assert.equal(compactDevice({ data: { deviceType: 'sensor.motion', faulted: false } }, false).derived_state, 'clear')
  assert.equal(compactDevice({ data: { deviceType: 'sensor.motion', faulted: true } }, false).derived_state, 'motion_or_faulted')
  assert.equal(compactDevice({ data: { deviceType: 'custom.sensor', faulted: false } }, false).derived_state, 'clear')
})

test('compactDevice includes raw data only when requested', () => {
  const result = compactDevice({ data: { zid: 'sensor-1', deviceType: 'sensor.contact', faulted: false } }, true)
  assert.equal(result.derived_state, 'closed_or_clear')
  assert.deepEqual(result.raw, { zid: 'sensor-1', deviceType: 'sensor.contact', faulted: false })
})

test('loadConfig returns empty object for missing private config', () => {
  assert.deepEqual(loadConfig('/tmp/does-not-exist-ring-config.json'), {})
})

test('saveUpdatedRefreshToken writes token with private file mode', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ring-status-test-'))
  const configPath = path.join(dir, 'ring_client_status.json')

  saveUpdatedRefreshToken(configPath, { refreshToken: 'old-token', timeoutMs: 123 }, 'new-token')

  const saved = JSON.parse(fs.readFileSync(configPath, 'utf8'))
  assert.equal(saved.refreshToken, 'new-token')
  assert.equal(saved.timeoutMs, 123)
  assert.equal(fs.statSync(configPath).mode & 0o777, 0o600)
})

test('withTimeout rejects slow promises', async () => {
  await assert.rejects(
    withTimeout(new Promise(() => {}), 1, 'slow op'),
    /slow op timed out after 1ms/,
  )
})
