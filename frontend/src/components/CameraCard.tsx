import { useState } from 'react';

interface CameraCardProps {
  name: string;
  id: string;
  streamUrl: string;
  loading: boolean;
  error: string | null;
  onClick: () => void;
  onRefresh: () => void;
}

export function CameraCard({ 
  name, 
  streamUrl, 
  onClick,
}: CameraCardProps) {
  const [streamKey, setStreamKey] = useState(0);
  const [streamError, setStreamError] = useState(false);

  const handleRetry = (e: React.MouseEvent) => {
    e.stopPropagation();
    setStreamError(false);
    setStreamKey(key => key + 1);
  };

  return (
    <div 
      className="bg-white rounded-lg shadow overflow-hidden cursor-pointer hover:shadow-lg transition-shadow"
      onClick={onClick}
    >
      <div className="p-3 border-b flex justify-between items-center">
        <h3 className="font-medium text-gray-800">{name}</h3>
      </div>
      <div className="relative aspect-video bg-gray-100">
        {streamError && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
            <div className="text-center text-red-400">
              <p className="text-sm">Stream failed</p>
              <button 
                onClick={handleRetry}
                className="mt-2 text-sm text-blue-500"
              >
                Retry
              </button>
            </div>
          </div>
        )}
        <img
          key={streamKey}
          src={`${streamUrl}?t=${streamKey}`}
          alt={name}
          className={`w-full h-full object-fill ${streamError ? 'hidden' : ''}`}
          onError={() => setStreamError(true)}
        />
      </div>
      <div className="p-2 text-center text-sm text-gray-500 border-t">
        Click for full resolution
      </div>
    </div>
  );
}
