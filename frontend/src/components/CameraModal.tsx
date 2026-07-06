import { useState, useEffect } from 'react';

interface CameraModalProps {
  cameraName: string;
  snapshotUrl: string;
  onClose: () => void;
}

export function CameraModal({ cameraName, snapshotUrl, onClose }: CameraModalProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [key, setKey] = useState(0);

  const handleRefresh = () => {
    setLoading(true);
    setError(null);
    setKey(key => key + 1);
  };

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  return (
    <div 
      className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div 
        className="bg-white rounded-lg max-w-5xl max-h-[90vh] w-full mx-4 overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-xl font-semibold">{cameraName} - Full resolution</h2>
          <div className="flex gap-2">
            <button
              onClick={handleRefresh}
              className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              Refresh
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1 bg-gray-300 rounded hover:bg-gray-400"
            >
              Close
            </button>
          </div>
        </div>
        <div className="p-4 flex items-center justify-center min-h-[300px]">
          {loading && (
            <div className="text-gray-500">Loading...</div>
          )}
          {error && (
            <div className="text-red-500 text-center">
              <p>{error}</p>
              <button 
                onClick={handleRefresh}
                className="mt-2 px-3 py-1 bg-blue-500 text-white rounded"
              >
                Retry
              </button>
            </div>
          )}
          <img
            key={key}
            src={`${snapshotUrl}?t=${key}`}
            alt={cameraName}
            className={`max-w-full max-h-[70vh] object-contain ${loading || error ? 'hidden' : ''}`}
            onLoad={() => setLoading(false)}
            onError={() => {
              setLoading(false);
              setError('Failed to load image');
            }}
          />
        </div>
      </div>
    </div>
  );
}
