"""Production Deployment Configuration.

Provides:
- Dockerfile for AI_SUPPORT
- Kubernetes manifests
- Helm chart
- Docker Compose for development
- Environment configurations
- Health check endpoints
"""

from pathlib import Path

# Dockerfile content
DOCKERFILE = '''# AI_SUPPORT Production Dockerfile
FROM python:3.11-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    git \\
    curl \\
    ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY pyproject.toml .

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD python -c "import requests; requests.get('http://localhost:8080/health').raise_for_status()"

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Run application
CMD ["python", "-m", "src.interfaces.server.main"]
'''

# Docker Compose for development
DOCKER_COMPOSE_DEV = '''version: '3.8'

services:
  aisupport:
    build: .
    ports:
      - "8080:8080"
    environment:
      - ENV=development
      - LOG_LEVEL=DEBUG
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/aisupport
    depends_on:
      - redis
      - db
    volumes:
      - ./src:/app/src
    command: python -m uvicorn src.interfaces.server.main:app --reload

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  db:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=aisupport
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Development tools
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"
      - "4317:4317"
      - "4318:4318"

volumes:
  redis_data:
  postgres_data:
'''

# Docker Compose for production
DOCKER_COMPOSE_PROD = '''version: '3.8'

services:
  aisupport:
    build:
      context: .
      dockerfile: Dockerfile.prod
    image: aisupport:latest
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '0.5'
          memory: 1G
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
    environment:
      - ENV=production
      - LOG_LEVEL=INFO
      - REDIS_URL=redis://redis-sentinel:26379
      - DATABASE_URL=postgresql://aisupport:${DB_PASSWORD}@postgres-master:5432/aisupport
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8080/health').raise_for_status()"]
      interval: 30s
      timeout: 10s
      retries: 3
    depends_on:
      - redis-sentinel
      - postgres-master
      - otel-collector

  redis-sentinel:
    image: redis:7-alpine
    command: redis-sentinel /usr/local/etc/redis/sentinel.conf
    volumes:
      - ./config/redis/sentinel.conf:/usr/local/etc/redis/sentinel.conf
    depends_on:
      - redis-master
      - redis-replica

  redis-master:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_master:/data

  redis-replica:
    image: redis:7-alpine
    command: redis-server --replicaof redis-master 6379 --appendonly yes
    depends_on:
      - redis-master
    volumes:
      - redis_replica:/data

  postgres-master:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=aisupport
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=aisupport
    volumes:
      - postgres_master:/var/lib/postgresql/data
    command: postgres -c wal_level=replica -c max_wal_senders=3

  postgres-replica:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=aisupport
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=aisupport
    command: postgres -c wal_level=replica -c primary_conninfo=host=postgres-master port=5432 user=aisupport -c standby_mode=on
    depends_on:
      - postgres-master
    volumes:
      - postgres_replica:/var/lib/postgresql/data

  otel-collector:
    image: otel/opentelemetry-collector:latest
    command: --config=/etc/otel-collector-config.yaml
    volumes:
      - ./config/otel/collector.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"
      - "4318:4318"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./config/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}

volumes:
  redis_master:
  redis_replica:
  postgres_master:
  postgres_replica:
'''

# Kubernetes Deployment
K8S_DEPLOYMENT = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: aisupport
  labels:
    app: aisupport
spec:
  replicas: 3
  selector:
    matchLabels:
      app: aisupport
  template:
    metadata:
      labels:
        app: aisupport
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: aisupport
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: aisupport
        image: aisupport:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
          name: http
        env:
        - name: ENV
          value: "production"
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: aisupport-secrets
              key: redis-url
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: aisupport-secrets
              key: database-url
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 4Gi
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          failureThreshold: 3
        volumeMounts:
        - name: tmp
          mountPath: /tmp
      volumes:
      - name: tmp
        emptyDir: {}
      nodeSelector:
        workload: ai-support
      tolerations:
      - key: "ai-support"
        operator: "Exists"
        effect: "NoSchedule"
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - aisupport
              topologyKey: kubernetes.io/hostname
'''

# Kubernetes Service
K8S_SERVICE = '''apiVersion: v1
kind: Service
metadata:
  name: aisupport
  labels:
    app: aisupport
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8080
    name: http
  selector:
    app: aisupport
---
apiVersion: v1
kind: Service
metadata:
  name: aisupport-lb
  labels:
    app: aisupport
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
spec:
  type: LoadBalancer
  ports:
  - port: 443
    targetPort: 8080
    name: https
  - port: 80
    targetPort: 8080
    name: http
  selector:
    app: aisupport
'''

# Kubernetes Horizontal Pod Autoscaler
K8S_HPA = '''apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: aisupport-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: aisupport
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      - type: Pods
        value: 4
        periodSeconds: 15
      selectPolicy: Max
'''

# Kubernetes Ingress
K8S_INGRESS = '''apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: aisupport-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - aisupport.example.com
    secretName: aisupport-tls
  rules:
  - host: aisupport.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: aisupport
            port:
              number: 80
'''

# Pod Disruption Budget
K8S_PDB = '''apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: aisupport-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: aisupport
'''

# RBAC
K8S_RBAC = '''apiVersion: v1
kind: ServiceAccount
metadata:
  name: aisupport
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: aisupport
rules:
- apiGroups: [""]
  resources: ["secrets", "configmaps"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: aisupport
subjects:
- kind: ServiceAccount
  name: aisupport
  namespace: default
roleRef:
  kind: Role
  name: aisupport
  apiGroup: rbac.authorization.k8s.io
'''

# ConfigMap
K8S_CONFIGMAP = '''apiVersion: v1
kind: ConfigMap
metadata:
  name: aisupport-config
data:
  LOG_LEVEL: "INFO"
  REDIS_SENTINEL_MASTER_NAME: "mymaster"
  OTEL_SERVICE_NAME: "aisupport"
  OTEL_TRACES_SAMPLER: "parentbased_traceidratio"
  OTEL_TRACES_SAMPLER_ARG: "0.1"
'''

# Secret
K8S_SECRET = '''apiVersion: v1
kind: Secret
metadata:
  name: aisupport-secrets
type: Opaque
stringData:
  redis-url: "redis://redis-sentinel:26379"
  database-url: "postgresql://aisupport:changeme@postgres-master:5432/aisupport"
'''


def write_deployment_files(output_dir: Path) -> None:
    """Write all deployment files to directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    files = {
        "Dockerfile": DOCKERFILE,
        "docker-compose.dev.yml": DOCKER_COMPOSE_DEV,
        "docker-compose.prod.yml": DOCKER_COMPOSE_PROD,
        "k8s/deployment.yaml": K8S_DEPLOYMENT,
        "k8s/service.yaml": K8S_SERVICE,
        "k8s/hpa.yaml": K8S_HPA,
        "k8s/ingress.yaml": K8S_INGRESS,
        "k8s/pdb.yaml": K8S_PDB,
        "k8s/rbac.yaml": K8S_RBAC,
        "k8s/configmap.yaml": K8S_CONFIGMAP,
        "k8s/secret.yaml": K8S_SECRET,
    }
    
    for path, content in files.items():
        full_path = output_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        print(f"Written: {path}")


if __name__ == "__main__":
    import sys
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    write_deployment_files(output)
