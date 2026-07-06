import { useState, useEffect } from 'react';
import { ControlTab } from './components/ControlTab';
import { CamerasTab } from './components/CamerasTab';
import { RingTab } from './components/RingTab';
import { ScheduleTab } from './components/ScheduleTab';
import { HistoryTab } from './components/HistoryTab';

type Tab = 'control' | 'cameras' | 'ring' | 'schedule' | 'history';

const TAB_PATH: Record<Tab, string> = {
  control: '/control',
  cameras: '/cameras',
  ring: '/ring',
  schedule: '/schedule',
  history: '/history',
};

function getTabFromPath(pathname: string): Tab {
  const normalizedPath = pathname.endsWith('/') && pathname !== '/'
    ? pathname.slice(0, -1)
    : pathname;

  if (normalizedPath === '/cameras') {
    return 'cameras';
  }

  if (normalizedPath === '/ring') {
    return 'ring';
  }

  if (normalizedPath === '/schedule') {
    return 'schedule';
  }

  if (normalizedPath === '/history') {
    return 'history';
  }

  return 'control';
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>(() => getTabFromPath(window.location.pathname));

  useEffect(() => {
    const onPopState = () => {
      setActiveTab(getTabFromPath(window.location.pathname));
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const switchTab = (tab: Tab) => {
    if (tab === activeTab) {
      return;
    }

    window.history.pushState({ tab }, '', TAB_PATH[tab]);
    setActiveTab(tab);
  };

  useEffect(() => {
    const path = window.location.pathname;
    if (path === '/' || path === '') {
      window.history.replaceState({ tab: 'control' }, '', TAB_PATH.control);
    }
  }, []);

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'control', label: 'Control', icon: '🎛️' },
    { key: 'cameras', label: 'Cameras', icon: '📷' },
    { key: 'ring', label: 'Ring', icon: '🛡️' },
    { key: 'schedule', label: 'Tasks', icon: '⏰' },
    { key: 'history', label: 'History', icon: '📊' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-sm shadow-sm sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-4">
          <h1 className="text-lg font-bold text-gray-800 flex items-center">
            <span className="text-2xl mr-2">🏠</span>
            Smart Home Skill
          </h1>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="bg-white/60 backdrop-blur-sm border-b border-gray-100 sticky top-[57px] z-10">
        <div className="max-w-2xl mx-auto px-4">
          <div className="grid grid-cols-3 sm:flex">
            {tabs.map(tab => (
              <button
                key={tab.key}
                onClick={() => switchTab(tab.key)}
                className={`px-2 sm:px-4 py-3 font-medium text-xs sm:text-sm border-b-2 transition-all duration-200 flex items-center justify-center gap-1 sm:gap-1.5 sm:flex-1 ${
                  activeTab === tab.key
                    ? 'border-blue-500 text-blue-600 bg-blue-50/50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50/50'
                }`}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-2xl mx-auto px-4 py-4">
        {activeTab === 'control' && <ControlTab />}
        {activeTab === 'cameras' && <CamerasTab />}
        {activeTab === 'ring' && <RingTab />}
        {activeTab === 'schedule' && <ScheduleTab />}
        {activeTab === 'history' && <HistoryTab />}
      </main>

      {/* Footer */}
      <footer className="max-w-2xl mx-auto px-4 py-6 text-center text-xs text-gray-400">
        Smart Home Skill v2.0
      </footer>
    </div>
  );
}

export default App;
