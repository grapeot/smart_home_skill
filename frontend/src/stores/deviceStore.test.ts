import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useDeviceStore } from './deviceStore'
import type { DeviceStatus } from '../types'

describe('deviceStore', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn()
    globalThis.localStorage.clear()
    useDeviceStore.setState({ status: null, error: null, loadingCounts: { hue: 0, wemo: 0, rinnai: 0, garage: 0, ring: 0, samsung: 0 }, errorsByKey: {} })
    vi.useRealTimers()
  })

  it('has initial state', () => {
    const state = useDeviceStore.getState()
    expect(state.status).toBeNull()
    expect(state.loadingCounts.hue).toBe(0)
    expect(state.error).toBeNull()
  })

  it('isLoading returns false for all keys initially', () => {
    expect(useDeviceStore.getState().isLoading('hue')).toBe(false)
    expect(useDeviceStore.getState().isLoading('ring')).toBe(false)
    expect(useDeviceStore.getState().isLoading('wemo')).toBe(false)
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

  it('fetchStatus tracks loadingCounts per device', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    let resolveFetch: ((value: Response) => void) | undefined
    const fetchPromise = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    mockFetch.mockReturnValueOnce(fetchPromise)

    const fetchCall = useDeviceStore.getState().fetchStatus(['ring'])

    expect(useDeviceStore.getState().isLoading('ring')).toBe(true)
    expect(useDeviceStore.getState().isLoading('hue')).toBe(false)

    resolveFetch!({
      ok: true,
      json: () => Promise.resolve({ ring: { configured: true, locations: [] } }),
    } as Response)

    await fetchCall

    expect(useDeviceStore.getState().isLoading('ring')).toBe(false)
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

  it('refreshRing clears ring loading and sets error on failure', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({}),
    } as Response)

    await useDeviceStore.getState().refreshRing()

    expect(useDeviceStore.getState().isLoading('ring')).toBe(false)
    expect(useDeviceStore.getState().getError('ring')).toBeTruthy()
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

  it('concurrent fetchStatus calls do not interfere loadingCounts', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    let resolveHue: ((value: Response) => void) | undefined
    let resolveRing: ((value: Response) => void) | undefined

    mockFetch.mockReturnValueOnce(new Promise<Response>((r) => { resolveHue = r }))
    mockFetch.mockReturnValueOnce(new Promise<Response>((r) => { resolveRing = r }))

    const hueCall = useDeviceStore.getState().fetchStatus(['hue'])
    const ringCall = useDeviceStore.getState().fetchStatus(['ring'])

    expect(useDeviceStore.getState().isLoading('hue')).toBe(true)
    expect(useDeviceStore.getState().isLoading('ring')).toBe(true)

    resolveHue!({
      ok: true,
      json: () => Promise.resolve({ hue: { name: 'Baby room', is_on: false, brightness: 0 } }),
    } as Response)

    await hueCall

    expect(useDeviceStore.getState().isLoading('hue')).toBe(false)
    expect(useDeviceStore.getState().isLoading('ring')).toBe(true)

    resolveRing!({
      ok: true,
      json: () => Promise.resolve({ ring: { configured: true, locations: [] } }),
    } as Response)

    await ringCall

    expect(useDeviceStore.getState().isLoading('ring')).toBe(false)
  })

  it('overlapping same-key requests keep loading true until both resolve', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    let resolveFirst: ((value: Response) => void) | undefined
    let resolveSecond: ((value: Response) => void) | undefined

    mockFetch.mockReturnValueOnce(new Promise<Response>((r) => { resolveFirst = r }))
    mockFetch.mockReturnValueOnce(new Promise<Response>((r) => { resolveSecond = r }))

    const firstCall = useDeviceStore.getState().fetchStatus(['hue'])
    const secondCall = useDeviceStore.getState().fetchStatus(['hue'])

    expect(useDeviceStore.getState().isLoading('hue')).toBe(true)

    resolveFirst!({
      ok: true,
      json: () => Promise.resolve({ hue: { name: 'Baby room', is_on: false, brightness: 0 } }),
    } as Response)

    await firstCall

    expect(useDeviceStore.getState().isLoading('hue')).toBe(true)

    resolveSecond!({
      ok: true,
      json: () => Promise.resolve({ hue: { name: 'Baby room', is_on: true, brightness: 128 } }),
    } as Response)

    await secondCall

    expect(useDeviceStore.getState().isLoading('hue')).toBe(false)
  })

  it('fetchStatus stores per-key error on failure', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({}),
    } as Response)

    await useDeviceStore.getState().fetchStatus(['hue'])

    expect(useDeviceStore.getState().getError('hue')).toBeTruthy()
    expect(useDeviceStore.getState().getError('ring')).toBeUndefined()
  })

  it('successful fetchStatus clears per-key error', async () => {
    const mockFetch = vi.mocked(globalThis.fetch)
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({}),
    } as Response)

    await useDeviceStore.getState().fetchStatus(['hue'])
    expect(useDeviceStore.getState().getError('hue')).toBeTruthy()

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ hue: { name: 'Baby room', is_on: true, brightness: 128 } }),
    } as Response)

    await useDeviceStore.getState().fetchStatus(['hue'])
    expect(useDeviceStore.getState().getError('hue')).toBeUndefined()
  })
})