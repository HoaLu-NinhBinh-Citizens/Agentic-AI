import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OverviewScreen } from '@/screens/OverviewScreen';
import { WorkflowsScreen } from '@/screens/WorkflowsScreen';
import { HardwareScreen } from '@/screens/HardwareScreen';
import { TimelineScreen } from '@/screens/TimelineScreen';
import { TrustScreen } from '@/screens/TrustScreen';
import { ComparisonScreen } from '@/screens/ComparisonScreen';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const navItems = [
  { path: '/', label: 'Overview', icon: '📊' },
  { path: '/workflows', label: 'Workflows', icon: '⚙️' },
  { path: '/comparison', label: 'Compare', icon: '📱' },
  { path: '/trust', label: 'Trust & UX', icon: '🔒' },
  { path: '/hardware', label: 'Hardware', icon: '🔧' },
  { path: '/timeline', label: 'Timeline', icon: '📋' },
];

function Sidebar() {
  const location = useLocation();

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-xl font-bold text-white">AI_SUPPORT</h1>
        <p className="text-sm text-gray-400">Dashboard</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) => `
                  flex items-center gap-3 px-4 py-3 rounded-lg transition-colors
                  ${isActive 
                    ? 'bg-blue-600 text-white' 
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                  }
                `}
              >
                <span className="text-lg">{item.icon}</span>
                <span className="font-medium">{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-800">
        <div className="text-xs text-gray-500 text-center">
          AI_SUPPORT v1.0<br />
          Phase 11: Production Validation
        </div>
      </div>
    </aside>
  );
}

function Header() {
  return (
    <header className="h-16 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-sm text-gray-400">System Online</span>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <button className="px-4 py-2 text-sm bg-gray-700 hover:bg-gray-600 rounded-lg text-white transition-colors">
          Settings
        </button>
      </div>
    </header>
  );
}

function AppContent() {
  return (
    <div className="flex h-screen bg-gray-950">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<OverviewScreen />} />
            <Route path="/workflows" element={<WorkflowsScreen />} />
            <Route path="/comparison" element={<ComparisonScreen />} />
            <Route path="/trust" element={<TrustScreen />} />
            <Route path="/hardware" element={<HardwareScreen />} />
            <Route path="/timeline" element={<TimelineScreen />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
