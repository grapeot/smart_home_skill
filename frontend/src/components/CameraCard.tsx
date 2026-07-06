import { useState } from 'react';

interface CameraCardProps {
  name: string;
  id: string;
  snapshotUrl: string;
  loading: boolean;
  error: string | null;
  onClick: () => void;
  onRefresh: () => void;
}

export function CameraCard({ 
  name, 
  snapshotUrl, 
  loading, 
  error, 
  onClick,
  onRefresh 
}: CameraCardProps) {
  const [imgKey, setImgKey] = useState(0);

  const handleRefresh = (e: React.MouseEvent) => {
    e.stopPropagation();
    setImgKey(key => key + 1);
    onRefresh();
  };

  return (
    <div 
      className="bg-white rounded-lg shadow overflow-hidden cursor-pointer hover:shadow-lg transition-shadow"
      onClick={onClick}
    >
      <div className="p-3 border-b flex justify-between items-center">
        <h3 className="font-medium text-gray-800">{name}</h3>
        <button
          onClick={handleRefresh}
          className="text-sm px-2 py-1 text-blue-500 hover:bg-blue-50 rounded"
        >
          Refresh
        </button>
      </div>
      <div className="relative aspect-video bg-gray-100">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
            <div className="text-gray-400">Loading...</div>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
            <div className="text-center text-red-400">
              <p className="text-sm">{error}</p>
              <button 
                onClick={handleRefresh}
                className="mt-2 text-sm text-blue-500"
              >
                Retry
              </button>
            </div>
          </div>
        )}
        <img
          key={imgKey}
          src={`${snapshotUrl}?t=${imgKey}`}
          alt={name}
          className={`w-full h-full object-cover ${loading || error ? 'opacity-0' : 'opacity-100'}`}
          onLoad={() => {}}
          onError={() => {}}
        />
      </div>
      <div className="p-2 text-center text-sm text-gray-500 border-t">
        Click for full resolution
      </div>
    </div>
  );
}
