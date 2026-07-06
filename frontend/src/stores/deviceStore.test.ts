import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useDeviceStore } from './deviceStore'
import type { DeviceStatus } from '../types'

describe('deviceStore', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn()
    globalThis.localStorage.clear()
    useDeviceStore.setState({ status: null, error: null, loading: false })
    vi.useRealTimers()
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

  it('fetchStatus can request Ring only', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ring: { configured: true, locations: [{ name: 'Home', devices: [] }] } }),
    } as Response)

    await useDeviceStore.getState().fetchStatus(['ring'])

    expect(mockFetch).toHaveBeenCalledWith('/api/status?devices=ring')
    expect(useDeviceStore.getState().status?.ring?.locations[0]?.name).toBe('Home')
  })

  it('fetchStatus uses cached Ring status inside TTL', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-06T10:00:00Z'))
    globalThis.localStorage.setItem(
      'smart_home:ring_status:v1',
      JSON.stringify({
        savedAt: Date.now(),
        ring: { configured: true, locations: [{ name: 'Cached home', devices: [] }] },
      }),
    )

    await useDeviceStore.getState().fetchStatus(['ring'])

    expect(globalThis.fetch).not.toHaveBeenCalled()
    expect(useDeviceStore.getState().status?.ring?.locations[0]?.name).toBe('Cached home')
  })

  it('refreshRing bypasses cache and updates cached status', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    globalThis.localStorage.setItem(
      'smart_home:ring_status:v1',
      JSON.stringify({ savedAt: Date.now(), ring: { configured: true, locations: [{ name: 'Cached home', devices: [] }] } }),
    )
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ring: { configured: true, locations: [{ name: 'Fresh home', devices: [] }] } }),
    } as Response)

    await useDeviceStore.getState().refreshRing()

    expect(mockFetch).toHaveBeenCalledWith('/api/status?devices=ring')
    expect(useDeviceStore.getState().status?.ring?.locations[0]?.name).toBe('Fresh home')
    const cached = JSON.parse(globalThis.localStorage.getItem('smart_home:ring_status:v1') || '{}')
    expect(cached.ring.locations[0].name).toBe('Fresh home')
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
