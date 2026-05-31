# Kiro AI IDE — Security Specification

## Security Model

### Threat Model

| Threat | Severity | Mitigation |
|--------|----------|------------|
| Code injection via user input | Critical | Input validation, sandboxing |
| Unauthorized API access | Critical | JWT auth, API key validation |
| Credential theft | Critical | Secrets management, env vars |
| Data exfiltration | High | Encryption at rest, access logs |
| Plugin vulnerabilities | High | Sandboxed execution, validation |
| Denial of Service | Medium | Rate limiting, resource limits |

## Authentication

### JWT Tokens

```json
{
  "sub": "user_id",
  "iss": "kiro-ai",
  "exp": 1717200000,
  "iat": 1717113600,
  "scope": ["analyze", "comment", "report"]
}
```

### API Keys

- Generated with 256-bit entropy
- Stored as bcrypt hashes
- Support for scopes and expiration

### OAuth 2.0 Integration

- Authorization Code flow
- PKCE for public clients
- Support for GitHub, GitLab, SSO

## Authorization

### Permission Scopes

| Scope | Description |
|-------|-------------|
| `analyze` | Run analysis |
| `read` | Read findings and reports |
| `comment` | Add comments |
| `admin` | Manage users and plugins |

### Role-Based Access Control

| Role | Permissions |
|------|-------------|
| Viewer | read |
| Developer | analyze, read, comment |
| Lead | analyze, read, comment, admin |
| Admin | all |

## Input Validation

### File Path Validation

```python
# Reject paths containing:
- Null bytes (\0)
- Path traversal (..)
- Absolute paths outside workspace
- Symlinks to outside workspace

def validate_path(path: str) -> bool:
    resolved = Path(path).resolve()
    if not str(resolved).startswith(WORKSPACE_ROOT):
        return False
    return True
```

### Code Input Sanitization

- Maximum file size: 10MB
- Encoding validation: UTF-8 only
- BOM detection and handling
- Null byte stripping

### Command Injection Prevention

```python
# All external commands use subprocess with:
- shell=False
- Whitelist of allowed commands
- Argument validation with regex
- No user-controlled command strings
```

## Data Protection

### Encryption at Rest

- AES-256-GCM for database
- Per-user encryption keys
- Key rotation support

### Encryption in Transit

- TLS 1.3 required
- Certificate pinning for mobile
- Perfect forward secrecy

### Secrets Management

```yaml
# Environment variables (preferred)
KIRO_SECRET_KEY=xxx
KIRO_DATABASE_PASSWORD=xxx

# HashiCorp Vault integration
vault:
  enabled: true
  address: https://vault.internal
  path: secret/kiro
```

## Plugin Security

### Sandbox Model

```python
class PluginSandbox:
    # Restricted imports
    allowed_modules = [
        'json', 're', 'ast', 'pathlib'
    ]
    
    # Restricted filesystem access
    allowed_paths = ['/workspace']
    
    # Restricted network access
    allowed_hosts = []
    
    # Execution timeout
    max_execution_seconds = 30
```

### Plugin Manifest Validation

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "permissions": ["read", "analyze"],
  "allowed_imports": ["json", "re"],
  "max_file_size_kb": 100
}
```

### Plugin Isolation

- Each plugin runs in separate process
- IPC via message passing
- Resource limits per plugin
- No shared state

## Rate Limiting

### Per-User Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/api/v1/analyze` | 60 | 1 minute |
| `/api/v1/llm/*` | 30 | 1 minute |
| `/api/v1/*` (other) | 120 | 1 minute |

### Per-IP Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| All | 300 | 1 minute |
| `/api/v1/auth/*` | 10 | 1 minute |

### Response Headers

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1717113660
Retry-After: 45
```

## Audit Logging

### Logged Events

| Event | Data | Retention |
|-------|------|-----------|
| Authentication | user, method, success, IP | 1 year |
| Authorization failure | user, resource, action | 1 year |
| Analysis | user, files, duration | 90 days |
| Findings access | user, finding_id | 90 days |
| Admin actions | admin, action, target | 1 year |

### Log Format

```json
{
  "timestamp": "2026-05-31T12:00:00Z",
  "level": "INFO",
  "event": "analysis.started",
  "user_id": "user_abc123",
  "metadata": {
    "files": ["src/main.py"],
    "session_id": "sess_xyz"
  }
}
```

## Vulnerability Disclosure

### Reporting

- security@kiro-ai.com
- Response within 48 hours
- Public disclosure after 90 days

### Security Updates

- Critical: 24-48 hours
- High: 7 days
- Medium: 30 days
- Low: next release

## Compliance

### Data Residency

- EU: GDPR compliant
- US: SOC 2 Type II
- Support for regional deployments

### Privacy

- No telemetry without consent
- Data export capability
- Account deletion (GDPR)

### Code Scanning

- No source code stored on servers
- Analysis performed in memory
- Temporary storage encrypted

## Security Checklist

### Deployment

- [ ] TLS configured with valid certificate
- [ ] Secrets stored in vault/env
- [ ] Database encrypted
- [ ] Rate limiting enabled
- [ ] WAF configured
- [ ] Monitoring enabled

### Configuration

- [ ] Default credentials changed
- [ ] JWT expiry configured
- [ ] API key rotation enabled
- [ ] Plugin sandboxing enabled
- [ ] Audit logging configured

### Operations

- [ ] Regular security updates
- [ ] Penetration testing
- [ ] Incident response plan
- [ ] Backup verification
- [ ] Access review quarterly
