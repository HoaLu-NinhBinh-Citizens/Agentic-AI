import React, { useState, useEffect } from 'react';
import { FiSettings, FiX, FiSave, FiCheck, FiAlertCircle } from 'react-icons/fi';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

interface SettingsState {
  aiProvider: 'openai' | 'anthropic';
  apiKey: string;
  model: string;
  maxTokens: number;
  temperature: number;
  fontSize: number;
  autoSave: boolean;
  autoSaveDelay: number;
}

const MODELS = {
  openai: [
    { id: 'gpt-4', name: 'GPT-4', description: 'Most capable, slower' },
    { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', description: 'Fast, cost effective' },
    { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', description: 'Fastest, lower cost' },
  ],
  anthropic: [
    { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', description: 'Balanced performance' },
    { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus', description: 'Most capable' },
    { id: 'claude-3-haiku-20240307', name: 'Claude 3 Haiku', description: 'Fastest, lowest cost' },
  ],
};

export const SettingsPanel: React.FC<SettingsProps> = ({ isOpen, onClose }) => {
  const [settings, setSettings] = useState<SettingsState>({
    aiProvider: 'openai',
    apiKey: '',
    model: 'gpt-4',
    maxTokens: 4096,
    temperature: 0.7,
    fontSize: 14,
    autoSave: true,
    autoSaveDelay: 1000,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    if (window.electronAPI?.storage) {
      const stored = await window.electronAPI.storage.getSettings();
      if (stored) {
        setSettings(prev => ({
          ...prev,
          aiProvider: stored.aiProvider || 'openai',
          model: stored.aiModel || 'gpt-4',
          maxTokens: stored.maxTokens || 4096,
          temperature: stored.temperature || 0.7,
          fontSize: stored.fontSize || 14,
          autoSave: stored.autoSave ?? true,
          autoSaveDelay: stored.autoSaveDelay || 1000,
        }));
      }
      
      const apiKey = await window.electronAPI.storage.getAPIKey();
      if (apiKey) {
        setSettings(prev => ({ ...prev, apiKey }));
      }
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      if (window.electronAPI?.storage) {
        await window.electronAPI.storage.updateSettings({
          aiProvider: settings.aiProvider,
          aiModel: settings.model,
          maxTokens: settings.maxTokens,
          temperature: settings.temperature,
          fontSize: settings.fontSize,
          autoSave: settings.autoSave,
          autoSaveDelay: settings.autoSaveDelay,
        });
        
        await window.electronAPI.storage.setAPIKey(settings.apiKey);
        
        await window.electronAPI.ai.initialize({
          provider: settings.aiProvider,
          apiKey: settings.apiKey,
          model: settings.model,
          maxTokens: settings.maxTokens,
          temperature: settings.temperature,
        });
      }
      
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (error) {
      console.error('Failed to save settings:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const testConnection = async () => {
    if (!settings.apiKey) {
      alert('Please enter an API key first');
      return;
    }
    
    try {
      await window.electronAPI?.ai.initialize({
        provider: settings.aiProvider,
        apiKey: settings.apiKey,
        model: settings.model,
      });
      
      const isInitialized = await window.electronAPI?.ai.isInitialized();
      if (isInitialized) {
        alert('Connection successful!');
      } else {
        alert('Connection failed. Please check your API key.');
      }
    } catch (error) {
      alert('Connection failed: ' + (error as Error).message);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h2><FiSettings /> Settings</h2>
          <button className="close-btn" onClick={onClose}><FiX /></button>
        </div>

        <div className="settings-content">
          <section className="settings-section">
            <h3>AI Configuration</h3>
            
            <div className="form-group">
              <label>Provider</label>
              <select
                value={settings.aiProvider}
                onChange={e => setSettings(prev => ({ 
                  ...prev, 
                  aiProvider: e.target.value as 'openai' | 'anthropic',
                  model: MODELS[e.target.value as keyof typeof MODELS][0].id
                }))}
              >
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </div>

            <div className="form-group">
              <label>API Key</label>
              <div className="api-key-input">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={settings.apiKey}
                  onChange={e => setSettings(prev => ({ ...prev, apiKey: e.target.value }))}
                  placeholder="sk-..."
                />
                <button 
                  className="toggle-visibility"
                  onClick={() => setShowApiKey(!showApiKey)}
                >
                  {showApiKey ? 'Hide' : 'Show'}
                </button>
              </div>
              <button className="test-btn" onClick={testConnection}>
                Test Connection
              </button>
            </div>

            <div className="form-group">
              <label>Model</label>
              <select
                value={settings.model}
                onChange={e => setSettings(prev => ({ ...prev, model: e.target.value }))}
              >
                {MODELS[settings.aiProvider].map(model => (
                  <option key={model.id} value={model.id}>
                    {model.name} - {model.description}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Max Tokens</label>
                <input
                  type="number"
                  value={settings.maxTokens}
                  onChange={e => setSettings(prev => ({ ...prev, maxTokens: parseInt(e.target.value) || 4096 }))}
                  min={100}
                  max={32000}
                />
              </div>

              <div className="form-group">
                <label>Temperature</label>
                <input
                  type="number"
                  value={settings.temperature}
                  onChange={e => setSettings(prev => ({ ...prev, temperature: parseFloat(e.target.value) || 0.7 }))}
                  min={0}
                  max={2}
                  step={0.1}
                />
              </div>
            </div>
          </section>

          <section className="settings-section">
            <h3>Editor</h3>
            
            <div className="form-group">
              <label>Font Size</label>
              <input
                type="number"
                value={settings.fontSize}
                onChange={e => setSettings(prev => ({ ...prev, fontSize: parseInt(e.target.value) || 14 }))}
                min={8}
                max={24}
              />
            </div>

            <div className="form-group">
              <label>Auto Save</label>
              <div className="checkbox-group">
                <input
                  type="checkbox"
                  checked={settings.autoSave}
                  onChange={e => setSettings(prev => ({ ...prev, autoSave: e.target.checked }))}
                />
                <span>Enable auto save</span>
              </div>
            </div>

            {settings.autoSave && (
              <div className="form-group">
                <label>Auto Save Delay (ms)</label>
                <input
                  type="number"
                  value={settings.autoSaveDelay}
                  onChange={e => setSettings(prev => ({ ...prev, autoSaveDelay: parseInt(e.target.value) || 1000 }))}
                  min={100}
                  max={10000}
                />
              </div>
            )}
          </section>
        </div>

        <div className="settings-footer">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button className="save-btn" onClick={handleSave} disabled={isSaving}>
            {saved ? <FiCheck /> : <FiSave />}
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      <style>{`
        .settings-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          justify-content: center;
          align-items: center;
          z-index: 1000;
        }

        .settings-panel {
          background: var(--bg-secondary);
          border-radius: 8px;
          width: 500px;
          max-height: 80vh;
          display: flex;
          flex-direction: column;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }

        .settings-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-bottom: 1px solid var(--border);
        }

        .settings-header h2 {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 16px;
          margin: 0;
        }

        .close-btn {
          background: none;
          border: none;
          color: var(--text-secondary);
          cursor: pointer;
          padding: 4px;
        }

        .settings-content {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
        }

        .settings-section {
          margin-bottom: 24px;
        }

        .settings-section h3 {
          font-size: 14px;
          color: var(--text-secondary);
          margin-bottom: 16px;
          text-transform: uppercase;
        }

        .form-group {
          margin-bottom: 16px;
        }

        .form-group label {
          display: block;
          font-size: 13px;
          margin-bottom: 6px;
          color: var(--text-primary);
        }

        .form-group input,
        .form-group select {
          width: 100%;
          padding: 8px 12px;
          background: var(--bg-tertiary);
          border: 1px solid var(--border);
          border-radius: 4px;
          color: var(--text-primary);
          font-size: 13px;
        }

        .form-group input:focus,
        .form-group select:focus {
          outline: none;
          border-color: var(--accent);
        }

        .form-row {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
        }

        .api-key-input {
          display: flex;
          gap: 8px;
        }

        .api-key-input input {
          flex: 1;
        }

        .toggle-visibility {
          background: var(--bg-tertiary);
          border: 1px solid var(--border);
          color: var(--text-secondary);
          padding: 8px 12px;
          border-radius: 4px;
          cursor: pointer;
        }

        .test-btn {
          margin-top: 8px;
          background: var(--bg-tertiary);
          border: 1px solid var(--border);
          color: var(--text-secondary);
          padding: 6px 12px;
          border-radius: 4px;
          font-size: 12px;
          cursor: pointer;
        }

        .test-btn:hover {
          background: var(--bg-hover);
        }

        .checkbox-group {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .checkbox-group input {
          width: auto;
        }

        .settings-footer {
          display: flex;
          justify-content: flex-end;
          gap: 12px;
          padding: 16px 20px;
          border-top: 1px solid var(--border);
        }

        .cancel-btn,
        .save-btn {
          padding: 8px 16px;
          border-radius: 4px;
          font-size: 13px;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .cancel-btn {
          background: transparent;
          border: 1px solid var(--border);
          color: var(--text-primary);
        }

        .save-btn {
          background: var(--accent);
          border: none;
          color: white;
        }

        .save-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
};

export default SettingsPanel;
