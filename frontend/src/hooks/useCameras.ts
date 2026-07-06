import { useState, useEffect } from 'react';

interface Camera {
  name: string;
  id: string;
}

interface CameraState {
  loading: boolean;
  error: string | null;
}

export function useCameras() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [states, setStates] = useState<Record<string, CameraState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCameras = async () => {
    try {
      const response = await fetch('/api/cameras');
      if (!response.ok) throw new Error('Failed to fetch cameras');
      const data = await response.json();
      setCameras(data.cameras);
      
      const initialStates: Record<string, CameraState> = {};
      data.cameras.forEach((cam: Camera) => {
        initialStates[cam.id] = { loading: false, error: null };
      });
      setStates(initialStates);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCameras();
  }, []);

  const refreshAll = () => {
    const newStates: Record<string, CameraState> = {};
    cameras.forEach(cam => {
      newStates[cam.id] = { loading: true, error: null };
    });
    setStates(newStates);
  };

  const setCameraState = (id: string, state: Partial<CameraState>) => {
    setStates(prev => ({
      ...prev,
      [id]: { ...prev[id], ...state }
    }));
  };

  const getSnapshotUrl = (id: string) => `/api/cameras/snapshot/${encodeURIComponent(id)}`;

  return {
    cameras,
    states,
    loading,
    error,
    refreshAll,
    setCameraState,
    getSnapshotUrl,
    refetch: fetchCameras
  };
}
