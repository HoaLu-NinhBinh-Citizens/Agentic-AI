# AI Configuration Guide for AI_SUPPORT

This guide explains how to configure AI providers for AI_SUPPORT embedded engineering assistant.

## Quick Setup Options

### Option 1: OpenAI (Recommended for best quality)
1. Get an API key from [OpenAI Platform](https://platform.openai.com/api-keys)
2. Set environment variable:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```
3. Test configuration:
   ```bash
   curl http://localhost:8000/api/ai/config/status
   ```

### Option 2: Ollama (Local, Free, Recommended for embedded work)
1. Install Ollama from [ollama.ai](https://ollama.ai/)
2. Start Ollama server:
   ```bash
   ollama serve
   ```
3. Pull a model (recommended for embedded engineering):
   ```bash
   ollama pull llama3.2
   ```
4. Test connection:
   ```bash
   curl http://localhost:8000/api/ai/config/status
   ```

### Option 3: Anthropic Claude
1. Get API key from [Anthropic Console](https://console.anthropic.com/)
2. Set environment variable:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```
3. Test configuration.

## Configuration Status Check

After setting up, check your configuration:

```bash
# Check AI provider status
curl http://localhost:8000/api/ai/config/status

# Test AI connection
curl -X POST http://localhost:8000/api/ai/test \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Test connection"}'
```

## Troubleshooting

### Common Issues

#### 1. "AI Not Configured" Error
**Symptoms**: Chat returns "AI provider not configured" error.

**Solution**:
```bash
# Check if environment variables are set
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY
echo $OLLAMA_BASE_URL

# If using Ollama, check if it's running
curl http://localhost:11434/api/tags
```

#### 2. "Authentication Failed" Error
**Symptoms**: "API key invalid" or "authentication failed".

**Solution**:
- Verify API key is correct and not expired
- Check API key permissions and quota
- Regenerate API key if necessary

#### 3. "Connection Timeout" Error
**Symptoms**: Requests time out after 30 seconds.

**Solution**:
- Check network connectivity
- Verify AI provider service status
- Try a simpler query
- Consider using Ollama locally for faster response

#### 4. "Rate Limit Exceeded" Error
**Symptoms**: "Too many requests" error.

**Solution**:
- Wait 60 seconds before retrying
- Reduce request frequency
- Upgrade API plan if needed

## Advanced Configuration

### Multiple Provider Fallback

The system automatically falls back between available providers in this order:
1. OpenAI (if configured)
2. Anthropic (if configured)
3. Ollama (if available)

### Custom Model Selection

Edit `configs/llm.yaml` to customize:
```yaml
llm:
  provider: auto  # or "openai", "anthropic", "ollama"
  
providers:
  openai:
    default_model: gpt-4o-mini  # Cost-effective option
  
  ollama:
    default_model: llama3.2  # Good for embedded engineering
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API key | (required if using OpenAI) |
| `ANTHROPIC_API_KEY` | Anthropic API key | (required if using Anthropic) |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `LLM_PROVIDER` | Force specific provider | `auto` |

## Embedded Engineering Optimization

For embedded engineering tasks, we recommend:

### Best Models for Embedded Work

1. **Ollama with Code Models**:
   ```bash
   ollama pull codellama
   ollama pull deepseek-coder
   ```

2. **OpenAI Models**:
   - `gpt-4o` - Best overall, but expensive
   - `gpt-4o-mini` - Good balance of cost and quality
   - `gpt-3.5-turbo` - Fast and cheap, less accurate

### Configuration for Embedded Context

Edit `configs/llm.yaml`:
```yaml
llm:
  temperature: 0.2  # Lower for more deterministic code
  max_tokens: 4096  # Higher for complex embedded code
  
local_provider:
  default_model: "codellama"  # Specialized for code
  temperature: 0.3
```

## Testing Your Setup

Run the complete test suite:

```bash
# Start the server
cd src/interfaces/server
python main.py

# In another terminal, test configuration
curl http://localhost:8000/api/ai/config/status

# Test AI response
curl -X POST http://localhost:8000/api/ai/test \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain SPI initialization sequence for STM32"}'

# Test chat via WebSocket (using wscat)
wscat -c ws://localhost:8000/ws/test_session
# Then send: {"type": "chat", "message": "Hello AI_SUPPORT!"}
```

## Support

If you encounter issues:
1. Check server logs: `tail -f server.log`
2. Verify environment variables are set
3. Test AI provider connectivity directly
4. Check the [AI_SUPPORT documentation](../README.md)

For embedded-specific issues:
- Ensure models support code generation
- Use lower temperature for deterministic output
- Provide clear hardware context in queries