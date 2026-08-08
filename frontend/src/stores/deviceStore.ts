import { create } from 'zustand';
import type { DeviceStatus, RingStatusResponse } from '../types';

type DeviceKey = 'hue' | 'wemo' | 'rinnai' | 'garage' | 'ring' | 'samsung';

const RING_CACHE_KEY = 'smart_home:ring_status:v1';
const RING_CACHE_TTL_MS = 60_000;

interface DeviceStore {
  status: DeviceStatus | null;
  loadingCounts: Record<DeviceKey, number>;
  errorsByKey: Partial<Record<DeviceKey, string>>;
  error: string | null;
  fetchStatus: (devices?: DeviceKey[]) => Promise<void>;
  refreshRing: () => Promise<void>;
  toggleHue: () => Promise<void>;
  setHueBrightness: (brightness: number) => Promise<void>;
  toggleWemo: (name: string) => Promise<void>;
  circulateRinnai: (duration?: number) => Promise<void>;
  refreshRinnai: () => Promise<void>;
  toggleGarage: (doorIndex: number) => Promise<void>;
  toggleSamsungTV: () => Promise<void>;
  isLoading: (key: DeviceKey) => boolean;
  getError: (key: DeviceKey) => string | undefined;
}

const API_BASE = '/api';

const ALL_KEYS: DeviceKey[] = ['hue', 'wemo', 'rinnai', 'garage', 'ring', 'samsung'];

function incrementCounts(counts: Record<DeviceKey, number>, keys: DeviceKey[]): Record<DeviceKey, number> {
  const next = { ...counts };
  for (const k of keys) next[k] = (next[k] ?? 0) + 1;
  return next;
}

function decrementCounts(counts: Record<DeviceKey, number>, keys: DeviceKey[]): Record<DeviceKey, number> {
  const next = { ...counts };
  for (const k of keys) next[k] = Math.max(0, (next[k] ?? 0) - 1);
  return next;
}

function clearErrors(errors: Partial<Record<DeviceKey, string>>, keys: DeviceKey[]): Partial<Record<DeviceKey, string>> {
  const next = { ...errors };
  for (const k of keys) delete next[k];
  return next;
}

function readRingCache(): RingStatusResponse | null {
  try {
    const raw = globalThis.localStorage?.getItem(RING_CACHE_KEY);
    if (!raw) return null;
    const cached = JSON.parse(raw) as { savedAt: number; ring: RingStatusResponse };
    if (!cached.savedAt || Date.now() - cached.savedAt > RING_CACHE_TTL_MS) return null;
    return cached.ring;
  } catch {
    return null;
  }
}

function writeRingCache(ring: RingStatusResponse) {
  try {
    globalThis.localStorage?.setItem(RING_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), ring }));
  } catch {
    // Cache failures should not affect live controls.
  }
}

function emptyCounts(): Record<DeviceKey, number> {
  return { hue: 0, wemo: 0, rinnai: 0, garage: 0, ring: 0, samsung: 0 };
}

export const useDeviceStore = create<DeviceStore>((set, get) => ({
  status: null,
  loadingCounts: emptyCounts(),
  errorsByKey: {},
  error: null,

  isLoading: (key: DeviceKey) => (get().loadingCounts[key] ?? 0) > 0,

  getError: (key: DeviceKey) => get().errorsByKey[key],

  fetchStatus: async (devices?: DeviceKey[]) => {
    const keys = devices?.length ? devices : ALL_KEYS;
    set((state) => ({ loadingCounts: incrementCounts(state.loadingCounts, keys) }));
    try {
      if (devices?.length === 1 && devices[0] === 'ring') {
        const cachedRing = readRingCache();
        if (cachedRing) {
          const prev = get().status;
          set((state) => ({
            status: prev ? { ...prev, ring: cachedRing } : { ring: cachedRing },
            loadingCounts: decrementCounts(state.loadingCounts, keys),
            errorsByKey: clearErrors(state.errorsByKey, keys),
            error: null,
          }));
          return;
        }
      }

      const qs = devices?.length ? `?devices=${devices.join(',')}` : '';
      const res = await fetch(`${API_BASE}/status${qs}`);
      if (!res.ok) throw new Error('Failed to fetch status');
      const data = await res.json();
      if (data.ring) writeRingCache(data.ring);
      const prev = get().status;
      const merged = prev ? { ...prev, ...data } : data;
      set((state) => ({
        status: merged,
        loadingCounts: decrementCounts(state.loadingCounts, keys),
        errorsByKey: clearErrors(state.errorsByKey, keys),
        error: null,
      }));
    } catch (error) {
      set((state) => ({
        error: String(error),
        loadingCounts: decrementCounts(state.loadingCounts, keys),
        errorsByKey: { ...state.errorsByKey, ...Object.fromEntries(keys.map((k) => [k, String(error)])) },
      }));
    }
  },

  refreshRing: async () => {
    const keys: DeviceKey[] = ['ring'];
    set((state) => ({ loadingCounts: incrementCounts(state.loadingCounts, keys) }));
    try {
      const res = await fetch(`${API_BASE}/status?devices=ring`);
      if (!res.ok) throw new Error('Failed to refresh Ring status');
      const data = await res.json();
      if (data.ring) writeRingCache(data.ring);
      const prev = get().status;
      set((state) => ({
        status: prev ? { ...prev, ...data } : data,
        loadingCounts: decrementCounts(state.loadingCounts, keys),
        errorsByKey: clearErrors(state.errorsByKey, keys),
        error: null,
      }));
    } catch (error) {
      set((state) => ({
        error: String(error),
        loadingCounts: decrementCounts(state.loadingCounts, keys),
        errorsByKey: { ...state.errorsByKey, ring: String(error) },
      }));
    }
  },

  toggleHue: async () => {
    try {
      const res = await fetch(`${API_BASE}/hue/toggle`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.status === 'error') {
        throw new Error(data.message || 'Failed to toggle Hue');
      }
      await get().fetchStatus(['hue']);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  setHueBrightness: async (brightness: number) => {
    try {
      const res = await fetch(`${API_BASE}/hue/on/${brightness}`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.status === 'error') {
        throw new Error(data.message || 'Failed to set Hue brightness');
      }
      await get().fetchStatus(['hue']);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  toggleWemo: async (name: string) => {
    try {
      const res = await fetch(`${API_BASE}/wemo/${name}/toggle`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.status === 'error') {
        throw new Error(data.message || 'Failed to toggle Wemo');
      }
      await get().fetchStatus(['wemo']);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  circulateRinnai: async (duration = 5) => {
    try {
      const res = await fetch(`${API_BASE}/rinnai/circulate?duration=${duration}`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to start circulation');
      await get().refreshRinnai();
      setTimeout(() => get().fetchStatus(), 10000);
    } catch (error) {
      set({ error: String(error) });
    }
  },

  refreshRinnai: async () => {
    set({ error: null });
    try {
      const res = await fetch(`${API_BASE}/status?devices=rinnai&rinnai_refresh=true`);
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Maintenance refresh failed (${res.status})`);
      }
      const data = await res.json();
      const prev = get().status;
      set({ status: prev ? { ...prev, ...data } : data });
      setTimeout(() => get().fetchStatus(), 10000);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : String(error) });
    }
  },

  toggleGarage: async (doorIndex: number) => {
    try {
      const res = await fetch(`${API_BASE}/garage/${doorIndex}/toggle`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to toggle garage door');
    } catch (error) {
      set({ error: String(error) });
    }
  },

  toggleSamsungTV: async () => {
    try {
      const prev = get().status;
      if (prev?.samsung) {
        set({ status: { ...prev, samsung: { ...prev.samsung, is_on: !prev.samsung.is_on } } });
      }

      const res = await fetch(`${API_BASE}/samsung/power/toggle`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.status === 'error') {
        if (prev?.samsung) set({ status: prev });
        throw new Error(data.message || 'Failed to toggle Samsung TV');
      }
      await new Promise(resolve => setTimeout(resolve, 2000));
      await get().fetchStatus(['samsung']);
    } catch (error) {
      set({ error: String(error) });
    }
  },
}));