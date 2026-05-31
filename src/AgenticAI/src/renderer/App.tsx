import React from 'react';
import { Sidebar } from './components/Sidebar';
import { EditorPanel } from './components/Editor';
import { TaskPanel } from './components/TaskPanel';
import { ChatPanel } from './components/ChatPanel';
import './App.css';

const App: React.FC = () => {
  return (
    <div className="app">
      <Sidebar />
      <EditorPanel />
      <TaskPanel />
      <ChatPanel />
    </div>
  );
};

export default App;
