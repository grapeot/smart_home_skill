import { useState } from 'react';
import { useCameras } from '../hooks/useCameras';
import { CameraCard } from './CameraCard';
import { CameraModal } from './CameraModal';

export function CamerasTab() {
  const { cameras, states, loading, error, refreshAll, getSnapshotUrl, getStreamUrl } = useCameras();
  const [selectedCamera, setSelectedCamera] = useState<{ name: string; id: string } | null>(null);

  const handleRefreshAll = () => {
    refreshAll();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading cameras...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-500">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">📷 Live Cameras</h2>
        <button
          onClick={handleRefreshAll}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Refresh all
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {cameras.map(camera => (
          <CameraCard
            key={camera.id}
            name={camera.name}
            id={camera.id}
            streamUrl={getStreamUrl(camera.id)}
            loading={states[camera.id]?.loading ?? false}
            error={states[camera.id]?.error ?? null}
            onClick={() => setSelectedCamera(camera)}
            onRefresh={() => {}}
          />
        ))}
      </div>

      {selectedCamera && (
        <CameraModal
          cameraName={selectedCamera.name}
          snapshotUrl={getSnapshotUrl(selectedCamera.id)}
          onClose={() => setSelectedCamera(null)}
        />
      )}
    </div>
  );
}
