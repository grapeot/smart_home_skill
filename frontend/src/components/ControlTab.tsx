import { useEffect, useState } from 'react';
import { useDeviceStore } from '../stores/deviceStore';
import { useCameras } from '../hooks/useCameras';
import type { RingSensorStatus } from '../types';

function isContactSensor(device: RingSensorStatus): boolean {
  const source = `${device.device_type ?? ''} ${device.derived_state ?? ''}`.toLowerCase();
  return source.includes('contact');
}

function sensorState(device: RingSensorStatus): string {
  if (device.derived_state) return device.derived_state;
  if (typeof device.faulted === 'boolean') return device.faulted ? 'Open' : 'Closed';
  return 'Unknown';
}

export function ControlTab() {
  const { status, loading, error, fetchStatus, toggleHue, setHueBrightness, toggleWemo, circulateRinnai, refreshRinnai, toggleGarage } = useDeviceStore();
  const { cameras, getSnapshotUrl } = useCameras();
  const [wemoLoading, setWemoLoading] = useState(false);
  const [garageImageKey, setGarageImageKey] = useState(0);
  const [garageImageError, setGarageImageError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchWemoStatus = async () => {
      setWemoLoading(true);
      await fetchStatus(['wemo']);
      if (!cancelled) {
        setWemoLoading(false);
      }
    };

    fetchStatus(['hue', 'rinnai', 'garage']);
    fetchStatus(['ring']);
    fetchWemoStatus();
    const fastInterval = setInterval(() => fetchStatus(['hue', 'rinnai', 'garage']), 10000);
    const ringInterval = setInterval(() => fetchStatus(['ring']), 30000);
    const wemoInterval = setInterval(fetchWemoStatus, 30000);
    return () => {
      cancelled = true;
      clearInterval(fastInterval);
      clearInterval(ringInterval);
      clearInterval(wemoInterval);
    };
  }, [fetchStatus]);

  if (loading && !status) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-600">
        Failed to load: {error}
      </div>
    );
  }

  const wemoDevices = status?.wemo ? Object.entries(status.wemo) : [];
  const wemoNames: Record<string, string> = {
    'coffee': 'Coffee maker',
    'veggie': 'Plant light',
    'tree': 'Tree light',
    'bedroom light': 'Bedroom light',
  };
  const garageCamera = cameras.find(camera =>
    camera.id.toLowerCase().includes('garage') || camera.name.toLowerCase().includes('garage')
  );
  const garageSnapshotUrl = garageCamera ? getSnapshotUrl(garageCamera.id) : null;
  const garageSnapshotSrc = garageSnapshotUrl ? `${garageSnapshotUrl}?t=${garageImageKey}` : null;
  const garageStatus = status?.garage;
  const garageDoors = garageStatus
    ? Array.from({ length: Math.min(garageStatus.door_count, 2) }, (_, i) => {
        const index = i + 1;
        return garageStatus.doors?.find(door => door.index === index) ?? { index, label: `Garage door ${index}` };
      })
    : [];
  const contactSensors = (status?.ring?.locations ?? [])
    .flatMap(location => location.devices ?? [])
    .filter(isContactSensor);

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 font-medium">
          ⚠️ Action failed: {error}
        </div>
      )}

      {/* Lights */}
      <section className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 bg-gradient-to-r from-yellow-50 to-orange-50 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-800 flex items-center">
            <span className="text-xl mr-2">💡</span>
            Lights
            {status?.hue?.error && (
              <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
                Offline
              </span>
            )}
          </h2>
        </div>
        <div className="p-4">
          {status?.hue?.error && (
            <div className="mb-3 p-2 bg-amber-50 border border-amber-200 rounded-lg text-amber-700 text-sm">
              {status.hue.error}
            </div>
          )}
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium text-gray-900">{status?.hue?.name || 'Light'}</div>
              <div className="text-sm text-gray-500 mt-0.5">
                {status?.hue?.error ? (
                  <span className="flex items-center text-amber-600">
                    <span className="w-2 h-2 bg-amber-400 rounded-full mr-1.5"></span>
                    {status.hue.error}
                  </span>
                ) : status?.hue?.is_on ? (
                  <span className="flex items-center">
                    <span className="w-2 h-2 bg-green-400 rounded-full mr-1.5"></span>
                    On · brightness {status.hue.brightness}
                    {status?.hue?.timer_active && <span className="ml-2 text-blue-500">⏱ Timer active</span>}
                  </span>
                ) : (
                  <span className="flex items-center">
                    <span className="w-2 h-2 bg-gray-300 rounded-full mr-1.5"></span>
                    Off
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={toggleHue}
              className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
                status?.hue?.is_on ? 'bg-blue-500' : 'bg-gray-200'
              }`}
            >
              <span
                className={`inline-block h-6 w-6 transform rounded-full bg-white shadow transition-transform ${
                  status?.hue?.is_on ? 'translate-x-7' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
          {status?.hue?.is_on && !status?.hue?.error && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Brightness
              </label>
              <input
                type="range"
                min="1"
                max="254"
                value={status.hue.brightness || 128}
                onChange={(e) => setHueBrightness(parseInt(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>Dim</span>
                <span className="font-medium text-gray-700">{status.hue.brightness || 128}</span>
                <span>Bright</span>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Switches */}
      <section className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 bg-gradient-to-r from-green-50 to-teal-50 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-800 flex items-center">
            <span className="text-xl mr-2">🔌</span>
            Switches
            {wemoLoading && (
              <span className="ml-auto flex items-center gap-1.5 text-xs font-medium text-teal-600">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-teal-200 border-t-teal-500"></span>
                Loading
              </span>
            )}
          </h2>
        </div>
        <div className="divide-y divide-gray-50">
          {wemoLoading && wemoDevices.length === 0 && (
            <div className="flex items-center justify-center px-4 py-6 text-sm text-gray-500">
              Loading switches...
            </div>
          )}
          {wemoDevices.map(([name, device]) => (
            <div key={name} className="flex items-center justify-between px-4 py-3">
              <div>
                <div className="font-medium text-gray-900">{wemoNames[name] || name}</div>
                <div className="text-sm text-gray-500">
                  {device.is_on === null ? 'Unknown' : device.is_on ? 'On' : 'Off'}
                </div>
              </div>
              <button
                onClick={() => toggleWemo(name)}
                className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 ${
                  device.is_on ? 'bg-green-500' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-6 w-6 transform rounded-full bg-white shadow transition-transform ${
                    device.is_on ? 'translate-x-7' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Garage doors */}
      {status?.garage?.available && (
        <section className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="px-4 py-3 bg-gradient-to-r from-gray-50 to-slate-50 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-800 flex items-center">
              <span className="text-xl mr-2">🚗</span>
              Garage doors
            </h2>
          </div>
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {garageDoors.map(door => (
                <button
                  key={door.index}
                  onClick={() => toggleGarage(door.index)}
                  className="px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-2"
                >
                  {door.label}
                </button>
              ))}
            </div>
            {garageCamera && garageSnapshotUrl && garageSnapshotSrc && (
              <div className="overflow-hidden rounded-lg border border-gray-100 bg-gray-100">
                <div className="flex items-center justify-between border-b border-gray-200 bg-white px-3 py-2">
                  <a
                    href={garageSnapshotUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium text-gray-700 hover:text-blue-600"
                  >
                    {garageCamera.name}
                  </a>
                  <button
                    onClick={() => {
                      setGarageImageError(null);
                      setGarageImageKey(key => key + 1);
                    }}
                    className="text-sm text-blue-500 hover:text-blue-600"
                  >
                    Refresh
                  </button>
                </div>
                {garageImageError ? (
                  <div className="flex aspect-video items-center justify-center px-4 text-center text-sm text-red-500">
                    {garageImageError}
                  </div>
                ) : (
                  <a href={garageSnapshotUrl} target="_blank" rel="noreferrer">
                    <img
                      src={garageSnapshotSrc}
                      alt={garageCamera.name}
                      className="aspect-video w-full object-cover"
                      onError={() => setGarageImageError('Failed to load garage snapshot')}
                    />
                  </a>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Contact sensors */}
      <section className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 bg-gradient-to-r from-purple-50 to-slate-50 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-800 flex items-center">
            <span className="text-xl mr-2">🛡️</span>
            Contact sensors
          </h2>
        </div>
        <div className="divide-y divide-gray-50">
          {status?.ring?.error && (
            <div className="px-4 py-3 text-sm text-amber-700 bg-amber-50">
              {status.ring.configured === false ? 'Ring is not configured on this host.' : status.ring.error}
            </div>
          )}
          {!status?.ring && (
            <div className="px-4 py-3 text-sm text-gray-500">Loading contact sensors...</div>
          )}
          {status?.ring && contactSensors.length === 0 && !status.ring.error && (
            <div className="px-4 py-3 text-sm text-gray-500">No contact sensors reported.</div>
          )}
          {contactSensors.map((sensor, index) => (
            <div key={`${sensor.name}-${index}`} className="flex items-center justify-between px-4 py-3">
              <div>
                <div className="font-medium text-gray-900">{sensor.name || 'Unnamed contact sensor'}</div>
                <div className="text-sm text-gray-500">
                  {typeof sensor.battery_level === 'number' ? `Battery ${sensor.battery_level}%` : sensor.battery_status ? `Battery ${sensor.battery_status}` : 'Battery unknown'}
                </div>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sensor.faulted ? 'bg-orange-100 text-orange-700' : 'bg-green-100 text-green-700'}`}>
                {sensorState(sensor)}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Water heater */}
      <section className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-800 flex items-center">
            <span className="text-xl mr-2">🚿</span>
            Water heater
            <span className={`ml-auto text-xs px-2 py-0.5 rounded-full ${
              status?.rinnai?.is_online ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}>
              {status?.rinnai?.is_online ? 'Online' : 'Offline'}
            </span>
          </h2>
        </div>
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-gray-500">Set temperature</div>
              <div className="font-semibold text-gray-900">{status?.rinnai?.set_temperature}°F</div>
            </div>
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-gray-500">Outlet temperature</div>
              <div className="font-semibold text-gray-900">{status?.rinnai?.outlet_temp}°F</div>
            </div>
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-gray-500">Inlet temperature</div>
              <div className="font-semibold text-gray-900">{status?.rinnai?.inlet_temp}°F</div>
            </div>
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-gray-500">Recirculation</div>
              <div className={`font-semibold ${status?.rinnai?.recirculation_enabled ? 'text-blue-600' : 'text-gray-900'}`}>
                {status?.rinnai?.recirculation_enabled ? 'Running' : 'Stopped'}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <button
              onClick={() => circulateRinnai(5)}
              className="px-4 py-2.5 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              Run 5 min circulation
            </button>
            <button
              onClick={refreshRinnai}
              className="px-4 py-2.5 bg-emerald-500 text-white rounded-lg font-medium hover:bg-emerald-600 transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
            >
              Maintenance refresh
            </button>
          </div>
        </div>
      </section>

    </div>
  );
}
