import { create } from 'zustand';
import type { DeviceStatus, RingStatusResponse } from '../types';

type DeviceKey = 'hue' | 'wemo' | 'rinnai' | 'garage' | 'ring' | 'samsung';

const RING_CACHE_KEY = 'smart_home:ring_status:v1';
const RING_CACHE_TTL_MS = 60_000;

interface DeviceStore {
  status: DeviceStatus | null;
  loadingKeys: Set<DeviceKey>;
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
}

const API_BASE = '/api';

function removeKeys(set: Set<DeviceKey>, keys: DeviceKey[]): Set<DeviceKey> {
  const next = new Set(set);
  for (const k of keys) next.delete(k);
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

export const useDeviceStore = create<DeviceStore>((set, get) => ({
  status: null,
  loadingKeys: new Set<DeviceKey>(),
  error: null,

  isLoading: (key: DeviceKey) => get().loadingKeys.has(key),

  fetchStatus: async (devices?: DeviceKey[]) => {
    const keys = devices ?? (['hue', 'wemo', 'rinnai', 'garage', 'ring', 'samsung'] as DeviceKey[]);
    set((state) => ({ loadingKeys: new Set([...state.loadingKeys, ...keys]) }));
    try {
      if (devices?.length === 1 && devices[0] === 'ring') {
        const cachedRing = readRingCache();
        if (cachedRing) {
          const prev = get().status;
          set((state) => ({
            status: prev ? { ...prev, ring: cachedRing } : { ring: cachedRing },
            loadingKeys: removeKeys(state.loadingKeys, keys),
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
      set((state) => ({ status: merged, loadingKeys: removeKeys(state.loadingKeys, keys), error: null }));
    } catch (error) {
      set((state) => ({ error: String(error), loadingKeys: removeKeys(state.loadingKeys, keys) }));
    }
  },

  refreshRing: async () => {
    const keys: DeviceKey[] = ['ring'];
    set((state) => ({ loadingKeys: new Set([...state.loadingKeys, ...keys]) }));
    try {
      const res = await fetch(`${API_BASE}/status?devices=ring`);
      if (!res.ok) throw new Error('Failed to refresh Ring status');
      const data = await res.json();
      if (data.ring) writeRingCache(data.ring);
      const prev = get().status;
      set((state) => ({
        status: prev ? { ...prev, ...data } : data,
        loadingKeys: removeKeys(state.loadingKeys, keys),
        error: null,
      }));
    } catch (error) {
      set((state) => ({ error: String(error), loadingKeys: removeKeys(state.loadingKeys, keys) }));
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
      // 乐观更新：立刻翻转前端状态
      const prev = get().status;
      if (prev?.samsung) {
        set({ status: { ...prev, samsung: { ...prev.samsung, is_on: !prev.samsung.is_on } } });
      }

      const res = await fetch(`${API_BASE}/samsung/power/toggle`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.status === 'error') {
        // 回滚乐观更新
        if (prev?.samsung) set({ status: prev });
        throw new Error(data.message || 'Failed to toggle Samsung TV');
      }
      // SmartThings 云端有延迟，等 2 秒再刷新真实状态
      await new Promise(resolve => setTimeout(resolve, 2000));
      await get().fetchStatus(['samsung']);
    } catch (error) {
      set({ error: String(error) });
    }
  },
}));
