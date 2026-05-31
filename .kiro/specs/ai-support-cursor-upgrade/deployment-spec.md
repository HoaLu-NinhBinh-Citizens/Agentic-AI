# Kiro AI IDE — Deployment Specification

## Overview

Kiro AI IDE supports multiple deployment modes to suit different use cases.

## Deployment Modes

### 1. Local Development

**Use Case:** Individual developers

**Components:**
- CLI application
- Local session storage
- Local LLM provider (Ollama)

**Requirements:**
- Python 3.10+
- 4GB RAM
- 1GB disk space

### 2. Team Server

**Use Case:** Development teams

**Components:**
- API server
- Shared session storage (PostgreSQL)
- Centralized plugin repository
- Team collaboration features

**Requirements:**
- Python 3.10+
- 8GB RAM
- 10GB disk space
- PostgreSQL 14+

### 3. Cloud Deployment

**Use Case:** Large organizations

**Components:**
- Containerized API server
- Managed database
- CDN for static assets
- Multi-tenant isolation

**Requirements:**
- Docker/Kubernetes
- Cloud database (RDS, Cloud SQL)
- Redis for caching
- S3 for artifacts

## Installation

### pip Installation

```bash
pip install kiro-ai
```

### Docker

```bash
# Pull image
docker pull kiroai/kiro:latest

# Run container
docker run -d \
  --name kiro \
  -p 8765:8765 \
  -v ~/.kiro:/root/.kiro \
  kiroai/kiro:latest
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kiro-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kiro-api
  template:
    metadata:
      labels:
        app: kiro-api
    spec:
      containers:
      - name: kiro
        image: kiroai/kiro:latest
        ports:
        - containerPort: 8765
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: kiro-secrets
              key: database-url
```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `KIRO_CONFIG_PATH` | Config file path | No | `~/.kiro/config.yaml` |
| `KIRO_LOG_LEVEL` | Log level | No | `INFO` |
| `KIRO_DATABASE_URL` | Database connection | For server mode | - |
| `KIRO_SECRET_KEY` | Encryption key | For server mode | - |
| `KIRO_LLM_PROVIDER` | LLM provider | No | `openai` |
| `KIRO_LLM_API_KEY` | LLM API key | For cloud LLM | - |
| `KIRO_PORT` | Server port | No | `8765` |
| `KIRO_HOST` | Server host | No | `0.0.0.0` |

## Configuration

### Development Configuration

```yaml
# config/dev.yaml
llm:
  provider: ollama
  base_url: http://localhost:11434

storage:
  type: local
  path: ~/.kiro/data

logging:
  level: DEBUG

server:
  host: 127.0.0.1
  port: 8765
  debug: true
```

### Production Configuration

```yaml
# config/prod.yaml
llm:
  provider: openai
  model: gpt-4o
  api_key: ${KIRO_LLM_API_KEY}
  timeout: 30

storage:
  type: postgresql
  url: ${KIRO_DATABASE_URL}
  pool_size: 10

logging:
  level: INFO
  format: json

server:
  host: 0.0.0.0
  port: 8765
  workers: 4
  timeout: 60

security:
  jwt_secret: ${KIRO_SECRET_KEY}
  jwt_expiry_hours: 24
  rate_limit_per_minute: 100
```

## Database Schema

### Sessions Table

```sql
CREATE TABLE sessions (
    id VARCHAR(64) PRIMARY KEY,
    project_path VARCHAR(512) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(32) DEFAULT 'active',
    metadata JSONB
);

CREATE INDEX idx_sessions_project ON sessions(project_path);
CREATE INDEX idx_sessions_status ON sessions(status);
```

### Findings Table

```sql
CREATE TABLE findings (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) REFERENCES sessions(id),
    file VARCHAR(512) NOT NULL,
    line INTEGER NOT NULL,
    rule_id VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    message TEXT,
    code_context TEXT,
    fix_template TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, file, line, rule_id)
);

CREATE INDEX idx_findings_session ON findings(session_id);
CREATE INDEX idx_findings_severity ON findings(severity);
```

### Comments Table

```sql
CREATE TABLE comments (
    id VARCHAR(64) PRIMARY KEY,
    finding_id INTEGER REFERENCES findings(id),
    thread_id VARCHAR(64),
    author VARCHAR(128) NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(128),
    resolution_state VARCHAR(32) DEFAULT 'open'
);

CREATE INDEX idx_comments_thread ON comments(thread_id);
```

## Backup & Recovery

### Backup Strategy

```bash
# Daily backup at 2 AM
0 2 * * * pg_dump kiro | gzip > /backup/kiro_$(date +%Y%m%d).sql.gz

# Keep 30 days of backups
find /backup -name "kiro_*.sql.gz" -mtime +30 -delete
```

### Recovery Procedure

```bash
# Stop service
systemctl stop kiro

# Restore database
gunzip < /backup/kiro_20260531.sql.gz | psql kiro

# Start service
systemctl start kiro
```

## Monitoring

### Health Checks

```bash
curl http://localhost:8765/health
```

### Metrics Endpoint

```bash
curl http://localhost:8765/metrics
```

### Log Aggregation

Configure log shipping to:
- ELK Stack
- CloudWatch
- Datadog

## Security

### Authentication

- JWT tokens for API access
- API keys for CI/CD integration
- OAuth 2.0 for team SSO

### Network Security

- TLS 1.3 required
- Private networking for databases
- WAF in front of API

### Data Privacy

- Sessions encrypted at rest
- Findings encrypted at rest
- No PII in logs

## Scaling

### Horizontal Scaling

```
                    ┌─────────────┐
                    │   Load      │
                    │   Balancer  │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │  kiro   │      │  kiro   │      │  kiro   │
    │  API 1  │      │  API 2  │      │  API 3  │
    └────┬────┘      └────┬────┘      └────┬────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
                    ┌──────▼──────┐
                    │  PostgreSQL │
                    │  (Primary)  │
                    └─────────────┘
```

### Vertical Scaling

| Instance | vCPUs | RAM | Concurrent Users |
|----------|-------|-----|------------------|
| Small | 2 | 4GB | 10 |
| Medium | 4 | 8GB | 50 |
| Large | 8 | 16GB | 200 |
| XLarge | 16 | 32GB | 500 |

## Disaster Recovery

### RTO (Recovery Time Objective): 4 hours
### RPO (Recovery Point Objective): 1 hour

### Multi-Region Setup

```yaml
# docker-compose.yml for multi-region
services:
  kiro-primary:
    image: kiroai/kiro:latest
    environment:
      - REGION=us-east-1
      - PRIMARY=true

  kiro-replica:
    image: kiroai/kiro:latest
    environment:
      - REGION=us-west-2
      - PRIMARY=false
```
