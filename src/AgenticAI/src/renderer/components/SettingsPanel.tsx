import React, { useState, useEffect, useCallback } from 'react';
import { FiSettings, FiX, FiSave, FiCheck, FiAlertCircle } from 'react-icons/fi';
import { OllamaModel, OllamaHealthStatus } from '../../shared/types';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

type Provider = 'ollama' | 'openai' | 'anthropic';

interface SettingsState {
  provider: Provider;
  ollamaEndpoint: string;
  ollamaModel: string;
  ollamaTemperature: number;
  openaiApiKey: string;
  openaiModel: string;
  anthropicApiKey: string;
  anthropicModel: string;
  fontSize: number;
  autoSave: boolean;
  autoSaveDelay: number;
}

const OPENAI_MODELS = [
  { id: 'gpt-4', name: 'GPT-4', description: 'Most capable, slower' },
  { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', description: 'Fast, cost effective' },
  { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', description: 'Fastest, lower cost' },
];

const ANTHROPIC_MODELS = [
  { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', description: 'Balanced performance' },
  { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus', description: 'Most capable' },
  { id: 'claude-3-haiku-20240307', name: 'Claude 3 Haiku', description: 'Fastest, lowest cost' },
];

export const SettingsPanel: React.FC<SettingsProps> = ({ isOpen, onClose }) => {
  const [settings, setSettings] = useState<SettingsState>({
    provider: 'ollama',
    ollamaEndpoint: 'http://localhost:11434',
    ollamaModel: 'codellama',
    ollamaTemperature: 0.7,
    openaiApiKey: '',
    openaiModel: 'gpt-4',
    anthropicApiKey: '',
    anthropicModel: 'claude-3-5-sonnet-20241022',
    fontSize: 14,
    autoSave: true,
    autoSaveDelay: 1000,
  });

  const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
  const [ollamaHealth, setOllamaHealth] = useState<OllamaHealthStatus | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [pulling, setPulling] = useState(false);
  const [pullProgress, setPullProgress] = useState(0);
  const [pullStatus, setPullStatus] = useState('');

  useEffect(() => {
    loadSettings();
    if (settings.provider === 'ollama') {
      checkOllamaHealth();
      fetchModels();
    }
  }, []);

  const loadSettings = async () => {
    if (window.electronAPI?.storage) {
      const stored = await window.electronAPI.storage.getSettings();
      if (stored) {
        setSettings(prev => ({
          ...prev,
          provider: (stored.aiProvider as Provider) || 'ollama',
          ollamaModel: stored.ollamaModel || 'codellama',
          ollamaTemperature: stored.ollamaTemperature || 0.7,
          openaiModel: stored.openaiModel || 'gpt-4',
          anthropicModel: stored.anthropicModel || 'claude-3-5-sonnet-20241022',
          fontSize: stored.fontSize || 14,
          autoSave: stored.autoSave ?? true,
          autoSaveDelay: stored.autoSaveDelay || 1000,
        }));
      }
      
      const storedConfig = await window.electronAPI.storage.getAIConfig?.();
      if (storedConfig) {
        setSettings(prev => ({
          ...prev,
          provider: storedConfig.provider || 'ollama',
          ollamaEndpoint: storedConfig.ollamaEndpoint || 'http://localhost:11434',
          ollamaModel: storedConfig.ollamaModel || 'codellama',
          ollamaTemperature: storedConfig.ollamaTemperature || 0.7,
          openaiApiKey: storedConfig.openaiApiKey || '',
          openaiModel: storedConfig.openaiModel || 'gpt-4',
          anthropicApiKey: storedConfig.anthropicApiKey || '',
          anthropicModel: storedConfig.anthropicModel || 'claude-3-5-sonnet-20241022',
        }));
      }
      
      const apiKey = await window.electronAPI.storage.getAPIKey?.();
      if (apiKey) {
        setSettings(prev => ({ 
          ...prev, 
          openaiApiKey: apiKey 
        }));
      }
    }
  };

  const checkOllamaHealth = async () => {
    if (!window.electronAPI?.ollamaHealth) return;
    
    try {
      const status = await window.electronAPI.ollamaHealth();
      setOllamaHealth(status);
    } catch (error) {
      setOllamaHealth({ available: false, error: 'Failed to check health' });
    }
  };

  const fetchModels = async () => {
    if (!window.electronAPI?.ollamaListModels) return;
    
    try {
      const models = await window.electronAPI.ollamaListModels();
      setOllamaModels(models);
    } catch (error) {
      console.error('Failed to fetch models:', error);
    }
  };

  const handlePullModel = async () => {
    if (!window.electronAPI?.ollamaPullModel) return;

    setPulling(true);
    setPullProgress(0);
    setPullStatus('Starting pull...');

    try {
      const success = await window.electronAPI.ollamaPullModel(settings.ollamaModel, (progress) => {
        if (progress.percent !== undefined) {
          setPullProgress(progress.percent);
        }
        setPullStatus(progress.status || 'Pulling...');
      });

      if (success) {
        setPullStatus('Model pulled successfully!');
        fetchModels();
      } else {
        setPullStatus('Failed to pull model');
      }
    } catch (error: any) {
      setPullStatus(`Error: ${error.message}`);
    } finally {
      setPulling(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);

    try {
      if (settings.provider === 'ollama') {
        if (!window.electronAPI?.ollamaHealth) {
          setTestResult({ success: false, message: 'API not available' });
          return;
        }
        const health = await window.electronAPI.ollamaHealth();
        if (health.available) {
          setTestResult({ success: true, message: `Connected! Latency: ${health.latencyMs}ms` });
        } else {
          setTestResult({ success: false, message: health.error || 'Connection failed' });
        }
      } else if (settings.provider === 'openai') {
        setTestResult({ success: true, message: 'OpenAI API key configured' });
      } else {
        setTestResult({ success: true, message: 'Anthropic API key configured' });
      }
    } catch (error: any) {
      setTestResult({ success: false, message: error.message });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      if (window.electronAPI?.storage) {
        await window.electronAPI.storage.updateSettings({
          aiProvider: settings.provider,
          ollamaModel: settings.ollamaModel,
          ollamaTemperature: settings.ollamaTemperature,
          openaiModel: settings.openaiModel,
          anthropicModel: settings.anthropicModel,
          fontSize: settings.fontSize,
          autoSave: settings.autoSave,
          autoSaveDelay: settings.autoSaveDelay,
        });

        await window.electronAPI.storage.setAIConfig?.({
          provider: settings.provider,
          ollamaEndpoint: settings.ollamaEndpoint,
          ollamaModel: settings.ollamaModel,
          ollamaTemperature: settings.ollamaTemperature,
          openaiApiKey: settings.openaiApiKey,
          openaiModel: settings.openaiModel,
          anthropicApiKey: settings.anthropicApiKey,
          anthropicModel: settings.anthropicModel,
        });

        if (settings.openaiApiKey) {
          await window.electronAPI.storage.setAPIKey?.(settings.openaiApiKey);
        }
        
        await window.electronAPI.ai.initialize({
          provider: settings.provider,
          apiKey: settings.provider === 'openai' ? settings.openaiApiKey : 
                 settings.provider === 'anthropic' ? settings.anthropicApiKey : undefined,
          model: settings.provider === 'openai' ? settings.openaiModel :
                 settings.provider === 'anthropic' ? settings.anthropicModel :
                 settings.ollamaModel,
          temperature: settings.ollamaTemperature,
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

  const openOllamaWebsite = () => {
    window.open('https://ollama.com', '_blank');
  };

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h2><FiSettings /> AI Settings</h2>
          <button className="close-btn" onClick={onClose}><FiX /></button>
        </div>

        <div className="settings-content">
          {/* Provider Selection */}
          <section className="settings-section">
            <h3>Provider</h3>
            <div className="provider-tabs">
              <button 
                className={settings.provider === 'ollama' ? 'active' : ''} 
                onClick={() => setSettings(prev => ({ ...prev, provider: 'ollama' }))}
              >
                Ollama (Local)
              </button>
              <button 
                className={settings.provider === 'openai' ? 'active' : ''} 
                onClick={() => setSettings(prev => ({ ...prev, provider: 'openai' }))}
              >
                OpenAI
              </button>
              <button 
                className={settings.provider === 'anthropic' ? 'active' : ''} 
                onClick={() => setSettings(prev => ({ ...prev, provider: 'anthropic' }))}
              >
                Anthropic
              </button>
            </div>
          </section>

          {/* Ollama Settings */}
          {settings.provider === 'ollama' && (
            <section className="settings-section">
              <h3>Ollama Configuration</h3>
              
              {ollamaHealth && !ollamaHealth.available && (
                <div className="health-warning">
                  <span><FiAlertCircle /> Ollama is not running</span>
                  <button onClick={openOllamaWebsite}>Install Ollama</button>
                </div>
              )}

              <div className="form-group">
                <label>Endpoint</label>
                <input
                  type="text"
                  value={settings.ollamaEndpoint}
                  onChange={e => setSettings(prev => ({ ...prev, ollamaEndpoint: e.target.value }))}
                  placeholder="http://localhost:11434"
                />
              </div>

              <div className="form-group">
                <label>Model</label>
                <div className="model-select">
                  <select 
                    value={settings.ollamaModel} 
                    onChange={e => setSettings(prev => ({ ...prev, ollamaModel: e.target.value }))}
                  >
                    {ollamaModels.length === 0 ? (
                      <option value="">No models installed</option>
                    ) : (
                      ollamaModels.map(m => (
                        <option key={m.name} value={m.name}>{m.name}</option>
                      ))
                    )}
                  </select>
                  <button onClick={fetchModels} title="Refresh models">Refresh</button>
                </div>
                {settings.ollamaModel && !ollamaModels.find(m => m.name === settings.ollamaModel) && (
                  <div className="model-warning">
                    <span>Model not installed</span>
                    <button 
                      onClick={handlePullModel} 
                      disabled={pulling || !ollamaHealth?.available}
                    >
                      {pulling ? 'Pulling...' : 'Pull Now'}
                    </button>
                  </div>
                )}
                {pulling && (
                  <div className="pull-progress">
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${pullProgress}%` }} />
                    </div>
                    <span>{pullProgress}% - {pullStatus}</span>
                  </div>
                )}
              </div>

              <div className="form-group">
                <label>Temperature 
                  <span className="tooltip" title="Controls randomness. Lower = more focused, Higher = more creative">ℹ️</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={settings.ollamaTemperature}
                  onChange={e => setSettings(prev => ({ ...prev, ollamaTemperature: parseFloat(e.target.value) }))}
                />
                <span className="value">{settings.ollamaTemperature}</span>
              </div>
            </section>
          )}

          {/* OpenAI Settings */}
          {settings.provider === 'openai' && (
            <section className="settings-section">
              <h3>OpenAI Configuration</h3>
              
              <div className="form-group">
                <label>API Key</label>
                <div className="api-key-input">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={settings.openaiApiKey}
                    onChange={e => setSettings(prev => ({ ...prev, openaiApiKey: e.target.value }))}
                    placeholder="sk-..."
                  />
                  <button 
                    className="toggle-visibility"
                    onClick={() => setShowApiKey(!showApiKey)}
                  >
                    {showApiKey ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>

              <div className="form-group">
                <label>Model</label>
                <select 
                  value={settings.openaiModel} 
                  onChange={e => setSettings(prev => ({ ...prev, openaiModel: e.target.value }))}
                >
                  {OPENAI_MODELS.map(model => (
                    <option key={model.id} value={model.id}>
                      {model.name} - {model.description}
                    </option>
                  ))}
                </select>
              </div>
            </section>
          )}

          {/* Anthropic Settings */}
          {settings.provider === 'anthropic' && (
            <section className="settings-section">
              <h3>Anthropic Configuration</h3>
              
              <div className="form-group">
                <label>API Key</label>
                <div className="api-key-input">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={settings.anthropicApiKey}
                    onChange={e => setSettings(prev => ({ ...prev, anthropicApiKey: e.target.value }))}
                    placeholder="sk-ant-..."
                  />
                  <button 
                    className="toggle-visibility"
                    onClick={() => setShowApiKey(!showApiKey)}
                  >
                    {showApiKey ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>

              <div className="form-group">
                <label>Model</label>
                <select 
                  value={settings.anthropicModel} 
                  onChange={e => setSettings(prev => ({ ...prev, anthropicModel: e.target.value }))}
                >
                  {ANTHROPIC_MODELS.map(model => (
                    <option key={model.id} value={model.id}>
                      {model.name} - {model.description}
                    </option>
                  ))}
                </select>
              </div>
            </section>
          )}

          {/* Test Result */}
          {testResult && (
            <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
              {testResult.message}
            </div>
          )}

          {/* Editor Settings */}
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
          <button 
            className="test-btn" 
            onClick={handleTestConnection}
            disabled={testing}
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button className="save-btn" onClick={handleSave} disabled={isSaving}>
            {saved ? <FiCheck /> : <FiSave />}
            {isSaving ? 'Saving...' : 'Save'}
          </button>
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
            width: 550px;
            max-height: 85vh;
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

          .provider-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
          }

          .provider-tabs button {
            flex: 1;
            padding: 10px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text-primary);
            cursor: pointer;
            transition: all 0.2s;
          }

          .provider-tabs button.active {
            background: var(--accent);
            border-color: var(--accent);
            color: white;
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

          .form-group input[type="text"],
          .form-group input[type="password"],
          .form-group input[type="number"],
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

          .form-group input[type="range"] {
            width: calc(100% - 50px);
            display: inline-block;
          }

          .form-group .value {
            display: inline-block;
            width: 40px;
            text-align: right;
            color: var(--text-secondary);
            font-size: 12px;
          }

          .tooltip {
            margin-left: 4px;
            color: var(--text-secondary);
            cursor: help;
          }

          .api-key-input {
            display: flex;
            gap: 8px;
          }

          .api-key-input input {
            flex: 1;
          }

          .toggle-visibility,
          .model-select button {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 8px 12px;
            border-radius: 4px;
            cursor: pointer;
          }

          .toggle-visibility:hover,
          .model-select button:hover {
            background: var(--bg-hover);
          }

          .model-select {
            display: flex;
            gap: 8px;
          }

          .model-select select {
            flex: 1;
          }

          .health-warning {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px;
            background: rgba(241, 76, 76, 0.1);
            border: 1px solid var(--error);
            border-radius: 4px;
            margin-bottom: 16px;
          }

          .health-warning span {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--error);
          }

          .health-warning button {
            background: var(--accent);
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            color: white;
            cursor: pointer;
          }

          .model-warning {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 8px;
            padding: 8px;
            background: rgba(220, 217, 61, 0.1);
            border-radius: 4px;
            font-size: 13px;
          }

          .model-warning button {
            background: var(--warning);
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
          }

          .pull-progress {
            margin-top: 8px;
          }

          .progress-bar {
            height: 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 4px;
          }

          .progress-fill {
            height: 100%;
            background: var(--accent);
            transition: width 0.3s;
          }

          .test-result {
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 16px;
            font-size: 13px;
          }

          .test-result.success {
            background: rgba(78, 201, 176, 0.1);
            border: 1px solid var(--success);
            color: var(--success);
          }

          .test-result.error {
            background: rgba(241, 76, 76, 0.1);
            border: 1px solid var(--error);
            color: var(--error);
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

          .test-btn,
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

          .test-btn {
            margin-right: auto;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-primary);
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

          .save-btn:disabled,
          .test-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
          }
        `}</style>
      </div>
    </div>
  );
};

export default SettingsPanel;
