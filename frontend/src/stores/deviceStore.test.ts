import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useDeviceStore } from './deviceStore'
import type { DeviceStatus } from '../types'

describe('deviceStore', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn()
    useDeviceStore.setState({ status: null, error: null })
  })

  it('has initial state', () => {
    const state = useDeviceStore.getState()
    expect(state.status).toBeNull()
    expect(state.loading).toBe(false)
    expect(state.error).toBeNull()
  })

  it('fetchStatus merges partial data with existing status', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ wemo: { coffee: { is_on: true } } }),
    } as Response)

    const initialStatus: DeviceStatus = {
      hue: { name: 'Baby room', is_on: true, brightness: 128 },
      wemo: {},
      rinnai: { is_online: true },
      garage: { door_count: 2, available: true, doors: [{ index: 1, label: 'Garage Door Black' }] },
    }
    useDeviceStore.setState({ status: initialStatus })

    await useDeviceStore.getState().fetchStatus(['wemo'])

    const status = useDeviceStore.getState().status
    expect(status?.hue?.name).toBe('Baby room')
    expect(status?.wemo?.coffee?.is_on).toBe(true)
  })

  it('setHueBrightness calls API and fetches updated status', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'ok' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ hue: { name: 'Baby room', is_on: true, brightness: 200 } }),
      } as Response)

    await useDeviceStore.getState().setHueBrightness(200)

    expect(mockFetch).toHaveBeenCalledTimes(2)
    expect(mockFetch).toHaveBeenNthCalledWith(1, '/api/hue/on/200', { method: 'POST' })
    expect(mockFetch).toHaveBeenNthCalledWith(2, '/api/status?devices=hue')
    
    const status = useDeviceStore.getState().status
    expect(status?.hue?.brightness).toBe(200)
  })

  it('setHueBrightness handles API error', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ status: 'error', message: 'Failed to set brightness' }),
    } as Response)

    await useDeviceStore.getState().setHueBrightness(150)

    const state = useDeviceStore.getState()
    expect(state.error).toBeTruthy()
  })
})
