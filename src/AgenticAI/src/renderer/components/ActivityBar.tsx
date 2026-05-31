import React from 'react';
import { 
  FiFolder, FiSearch, FiGitBranch, FiTerminal, FiSettings 
} from 'react-icons/fi';
import { useAppStore } from '../store/useAppStore';

type ViewType = 'explorer' | 'search' | 'git' | 'terminal' | 'settings';

export const ActivityBar: React.FC = () => {
  const { activeSidebarView, setActiveSidebarView } = useAppStore();

  const views: { id: ViewType; icon: React.ReactNode; label: string }[] = [
    { id: 'explorer', icon: <FiFolder size={24} />, label: 'Explorer' },
    { id: 'search', icon: <FiSearch size={24} />, label: 'Search' },
    { id: 'git', icon: <FiGitBranch size={24} />, label: 'Source Control' },
    { id: 'terminal', icon: <FiTerminal size={24} />, label: 'Terminal' },
  ];

  const handleIconClick = (view: ViewType) => {
    if (view === 'settings') {
      setActiveSidebarView('settings');
    } else {
      setActiveSidebarView(view);
    }
  };

  return (
    <div className="activity-bar">
      <div className="activity-icons">
        {views.map(view => (
          <button
            key={view.id}
            className={`activity-icon ${activeSidebarView === view.id ? 'active' : ''}`}
            onClick={() => handleIconClick(view.id)}
            title={view.label}
          >
            {view.icon}
          </button>
        ))}
      </div>
      <div className="activity-bottom">
        <button
          className={`activity-icon ${activeSidebarView === 'settings' ? 'active' : ''}`}
          onClick={() => handleIconClick('settings')}
          title="Settings"
        >
          <FiSettings size={24} />
        </button>
      </div>
    </div>
  );
};
