import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { useDeviceStore } from '../stores/deviceStore'
import { ControlTab } from './ControlTab'

vi.mock('../hooks/useCameras', () => ({
  useCameras: () => ({
    cameras: [],
    getSnapshotUrl: () => '',
    getStreamUrl: () => '',
    loading: false,
    error: null,
    states: {},
    refreshAll: vi.fn(),
    setCameraState: vi.fn(),
    refetch: vi.fn(),
  }),
}))

describe('ControlTab', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn()
    globalThis.localStorage.clear()
    useDeviceStore.setState({ status: null, error: null, loadingKeys: new Set() })
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders all section headers immediately without waiting for data', () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise(() => {}))

    render(<ControlTab />)

    expect(screen.getByText('Lights')).toBeTruthy()
    expect(screen.getByText('Switches')).toBeTruthy()
    expect(screen.getByText('Contact sensors')).toBeTruthy()
    expect(screen.getByText('Water heater')).toBeTruthy()
  })

  it('shows per-section spinners while data is loading', () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise(() => {}))

    render(<ControlTab />)

    const sections = document.querySelectorAll('section')
    const spinners = document.querySelectorAll('.animate-spin')
    expect(spinners.length).toBeGreaterThan(0)
    expect(sections.length).toBeGreaterThanOrEqual(4)
  })

  it('renders light data after fetch resolves', async () => {
    vi.useRealTimers()
    vi.mocked(globalThis.fetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        hue: { name: 'Baby room', is_on: true, brightness: 200 },
        wemo: { coffee: { is_on: true } },
        rinnai: { is_online: true, set_temperature: 120, outlet_temp: 110, inlet_temp: 60, recirculation_enabled: false },
        garage: { door_count: 2, available: true, doors: [{ index: 1, label: 'Main' }] },
        ring: { configured: true, locations: [{ name: 'Home', devices: [] }] },
        samsung: { configured: false },
      }),
    } as Response)

    render(<ControlTab />)

    await waitFor(() => {
      expect(screen.getAllByText('Baby room').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Coffee maker').length).toBeGreaterThan(0)
      expect(screen.getAllByText('120°F').length).toBeGreaterThan(0)
    }, { timeout: 3000 })
  })

  it('does not render a global full-screen spinner', () => {
    vi.mocked(globalThis.fetch).mockImplementation(() => new Promise(() => {}))

    const { container } = render(<ControlTab />)

    const fullScreenSpinner = container.querySelector('.flex.items-center.justify-center.p-8')
    expect(fullScreenSpinner).toBeNull()
  })
})