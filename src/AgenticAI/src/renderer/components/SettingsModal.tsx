import React, { useState, useEffect } from 'react';
import { FiX, FiCheck, FiAlertCircle } from 'react-icons/fi';
import { useAppStore } from '../store/useAppStore';

type Provider = 'ollama' | 'openai' | 'anthropic';

export const SettingsModal: React.FC<{ isOpen: boolean; onClose: () => void }> = ({ isOpen, onClose }) => {
  const { aiConfig, setAiConfig, ollamaModels, setOllamaModels } = useAppStore();

  const [provider, setProvider] = useState<Provider>('ollama');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Ollama
  const [ollamaEndpoint, setOllamaEndpoint] = useState('http://localhost:11434');
  const [ollamaModel, setOllamaModel] = useState('codellama');
  const [ollamaTemperature, setOllamaTemperature] = useState(0.7);

  // OpenAI
  const [openaiApiKey, setOpenaiApiKey] = useState('');
  const [openaiModel, setOpenaiModel] = useState('gpt-4');

  // Anthropic
  const [anthropicApiKey, setAnthropicApiKey] = useState('');
  const [anthropicModel, setAnthropicModel] = useState('claude-3-5-sonnet-20241022');

  useEffect(() => {
    if (aiConfig) {
      setProvider(aiConfig.provider);
      setOllamaEndpoint(aiConfig.ollamaEndpoint || 'http://localhost:11434');
      setOllamaModel(aiConfig.ollamaModel || 'codellama');
      setOllamaTemperature(aiConfig.ollamaTemperature || 0.7);
      setOpenaiApiKey(aiConfig.openaiApiKey || '');
      setOpenaiModel(aiConfig.openaiModel || 'gpt-4');
      setAnthropicApiKey(aiConfig.anthropicApiKey || '');
      setAnthropicModel(aiConfig.anthropicModel || 'claude-3-5-sonnet-20241022');
    }
  }, [aiConfig]);

  useEffect(() => {
    if (provider === 'ollama' && isOpen) {
      fetchModels();
    }
  }, [provider, isOpen]);

  const fetchModels = async () => {
    if (window.electronAPI?.ollamaListModels) {
      const models = await window.electronAPI.ollamaListModels();
      setOllamaModels(models);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);

    try {
      if (provider === 'ollama') {
        const health = await window.electronAPI?.ollamaHealth();
        if (health?.available) {
          setTestResult({ success: true, message: `Connected! Latency: ${health.latencyMs}ms` });
        } else {
          setTestResult({ success: false, message: health?.error || 'Connection failed' });
        }
      } else {
        setTestResult({ success: true, message: `${provider} API key configured` });
      }
    } catch (error: any) {
      setTestResult({ success: false, message: error.message });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = () => {
    const config: any = { provider };
    
    if (provider === 'ollama') {
      config.ollamaEndpoint = ollamaEndpoint;
      config.ollamaModel = ollamaModel;
      config.ollamaTemperature = ollamaTemperature;
    } else if (provider === 'openai') {
      config.openaiApiKey = openaiApiKey;
      config.openaiModel = openaiModel;
    } else {
      config.anthropicApiKey = anthropicApiKey;
      config.anthropicModel = anthropicModel;
    }

    setAiConfig(config);
    window.electronAPI?.storage?.updateSettings({ aiConfig: config });
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="close-btn" onClick={onClose}><FiX size={20} /></button>
        </div>

        <div className="settings-content">
          {/* Provider Tabs */}
          <div className="settings-section">
            <h3>AI Provider</h3>
            <div className="provider-tabs">
              {(['ollama', 'openai', 'anthropic'] as Provider[]).map(p => (
                <button
                  key={p}
                  className={`provider-tab ${provider === p ? 'active' : ''}`}
                  onClick={() => setProvider(p)}
                >
                  {p === 'ollama' && 'Ollama (Local)'}
                  {p === 'openai' && 'OpenAI'}
                  {p === 'anthropic' && 'Anthropic'}
                </button>
              ))}
            </div>
          </div>

          {/* Ollama Settings */}
          {provider === 'ollama' && (
            <div className="settings-section">
              <div className="form-group">
                <label>Endpoint</label>
                <input
                  type="text"
                  value={ollamaEndpoint}
                  onChange={e => setOllamaEndpoint(e.target.value)}
                  placeholder="http://localhost:11434"
                />
              </div>
              <div className="form-group">
                <label>Model</label>
                <div className="model-select">
                  <select value={ollamaModel} onChange={e => setOllamaModel(e.target.value)}>
                    {ollamaModels.length === 0 ? (
                      <option value="">No models found - click refresh</option>
                    ) : (
                      ollamaModels.map(m => (
                        <option key={m.name} value={m.name}>{m.name}</option>
                      ))
                    )}
                  </select>
                  <button onClick={fetchModels} title="Refresh models from Ollama">🔄</button>
                </div>
                {ollamaModels.length === 0 && (
                  <p className="hint">Press refresh to load installed models from Ollama</p>
                )}
              </div>
              <div className="form-group">
                <label>Temperature: {ollamaTemperature}</label>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={ollamaTemperature}
                  onChange={e => setOllamaTemperature(parseFloat(e.target.value))}
                />
              </div>
            </div>
          )}

          {/* OpenAI Settings */}
          {provider === 'openai' && (
            <div className="settings-section">
              <div className="form-group">
                <label>API Key</label>
                <input
                  type="password"
                  value={openaiApiKey}
                  onChange={e => setOpenaiApiKey(e.target.value)}
                  placeholder="sk-..."
                />
              </div>
              <div className="form-group">
                <label>Model</label>
                <select value={openaiModel} onChange={e => setOpenaiModel(e.target.value)}>
                  <option value="gpt-4">GPT-4</option>
                  <option value="gpt-4-turbo">GPT-4 Turbo</option>
                  <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                </select>
              </div>
            </div>
          )}

          {/* Anthropic Settings */}
          {provider === 'anthropic' && (
            <div className="settings-section">
              <div className="form-group">
                <label>API Key</label>
                <input
                  type="password"
                  value={anthropicApiKey}
                  onChange={e => setAnthropicApiKey(e.target.value)}
                  placeholder="sk-ant-..."
                />
              </div>
              <div className="form-group">
                <label>Model</label>
                <select value={anthropicModel} onChange={e => setAnthropicModel(e.target.value)}>
                  <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
                  <option value="claude-3-opus-20240229">Claude 3 Opus</option>
                  <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
                </select>
              </div>
            </div>
          )}

          {/* Test Result */}
          {testResult && (
            <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
              {testResult.success ? <FiCheck /> : <FiAlertCircle />}
              {testResult.message}
            </div>
          )}
        </div>

        <div className="settings-footer">
          <button onClick={handleTestConnection} disabled={testing}>
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          <div className="footer-right">
            <button onClick={onClose}>Cancel</button>
            <button className="primary" onClick={handleSave}>Save</button>
          </div>
        </div>
      </div>
    </div>
  );
};
