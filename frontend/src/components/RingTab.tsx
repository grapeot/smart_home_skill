import { useEffect, useState } from 'react';
import { useDeviceStore } from '../stores/deviceStore';
import type { RingSensorStatus } from '../types';

function deviceKind(device: RingSensorStatus): string {
  const source = `${device.device_type ?? ''} ${device.derived_state ?? ''}`.toLowerCase();
  if (source.includes('motion')) return 'Motion';
  if (source.includes('contact')) return 'Contact';
  return device.device_type || 'Sensor';
}

function stateLabel(device: RingSensorStatus): string {
  if (device.derived_state) return device.derived_state;
  if (typeof device.faulted === 'boolean') return device.faulted ? 'Open' : 'Closed';
  return 'Unknown';
}

function stateClass(device: RingSensorStatus): string {
  if (device.comm_status && device.comm_status !== 'ok') return 'bg-amber-100 text-amber-700';
  if (device.tamper_status && device.tamper_status !== 'ok') return 'bg-red-100 text-red-700';
  if (device.faulted) return 'bg-orange-100 text-orange-700';
  return 'bg-green-100 text-green-700';
}

export function RingTab() {
  const { status, fetchStatus, refreshRing } = useDeviceStore();
  const [ringRefreshing, setRingRefreshing] = useState(false);
  const ring = status?.ring;

  useEffect(() => {
    fetchStatus(['ring']);
    const interval = setInterval(() => fetchStatus(['ring']), 30000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const locations = ring?.locations ?? [];
  const devices = locations.flatMap(location =>
    (location.devices ?? []).map(device => ({ ...device, locationName: location.name ?? 'Ring location' }))
  );

  const handleRefresh = async () => {
    setRingRefreshing(true);
    try {
      await refreshRing();
    } finally {
      setRingRefreshing(false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 bg-gradient-to-r from-purple-50 to-indigo-50 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-800 flex items-center">
            <span className="text-xl mr-2">🛡️</span>
            Ring sensors
            <button
              onClick={handleRefresh}
              disabled={ringRefreshing}
              className="ml-auto flex items-center gap-1.5 rounded-full bg-purple-100 px-3 py-1 text-xs font-medium text-purple-700 hover:bg-purple-200 focus:outline-none focus:ring-2 focus:ring-purple-400 focus:ring-offset-2 disabled:cursor-wait disabled:opacity-75"
            >
              {ringRefreshing && (
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-purple-200 border-t-purple-500"></span>
              )}
              {ringRefreshing ? 'Loading' : 'Refresh'}
            </button>
          </h2>
        </div>
        <div className="p-4 space-y-3">
          {ring?.error && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              {ring.configured === false ? 'Ring is not configured on this host.' : ring.error}
            </div>
          )}
          {ring?.observed_at && (
            <div className="text-xs text-gray-500">Observed at {new Date(ring.observed_at).toLocaleString()}</div>
          )}
          {!ring && <div className="text-sm text-gray-500">Loading Ring sensors...</div>}
          {ring && devices.length === 0 && !ring.error && (
            <div className="text-sm text-gray-500">No Ring sensors reported.</div>
          )}
          {devices.map((device, index) => (
            <div key={`${device.locationName}-${device.name}-${index}`} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-gray-900">{device.name || 'Unnamed sensor'}</div>
                  <div className="text-sm text-gray-500 mt-0.5">
                    {deviceKind(device)} · {device.locationName}
                  </div>
                </div>
                <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${stateClass(device)}`}>
                  {stateLabel(device)}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                {typeof device.battery_level === 'number' && <span>Battery {device.battery_level}%</span>}
                {device.battery_status && <span>Battery {device.battery_status}</span>}
                {device.comm_status && <span>Comm {device.comm_status}</span>}
                {device.tamper_status && <span>Tamper {device.tamper_status}</span>}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
