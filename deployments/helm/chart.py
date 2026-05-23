"""Helm Chart for AI_SUPPORT.

Provides production-ready Helm chart for Kubernetes deployment.
"""

# Chart.yaml
CHART_YAML = '''apiVersion: v2
name: aisupport
description: AI_SUPPORT - Autonomous Embedded Engineering Platform
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - embedded
  - firmware
  - debugging
  - ai
  - engineering
maintainers:
  - name: AI_SUPPORT Team
    email: team@aisupport.local
'''

# values.yaml
VALUES_YAML = '''# Default values for aisupport.

replicaCount: 3

image:
  repository: aisupport/aisupport
  pullPolicy: IfNotPresent
  tag: "latest"

imagePullSecrets: []
nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  annotations: {}
  name: ""

podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8080"
  prometheus.io/path: "/metrics"

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000

securityContext:
  capabilities:
    drop:
    - ALL
  readOnlyRootFilesystem: false
  allowPrivilegeEscalation: false

service:
  type: ClusterIP
  port: 80
  targetPort: 8080

ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
  hosts:
    - host: aisupport.local
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: aisupport-tls
      hosts:
        - aisupport.local

resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 250m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

nodeSelector:
  workload: ai-support

tolerations: []

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

# Application configuration
config:
  logLevel: INFO
  environment: production

# Redis configuration
redis:
  enabled: true
  architecture: replication
  auth:
    enabled: false
  sentinel:
    enabled: true
    masterSet: mymaster
  master:
    count: 1
  replica:
    count: 2

# PostgreSQL configuration
postgresql:
  enabled: true
  auth:
    username: aisupport
    database: aisupport
  primary:
    persistence:
      enabled: true
      size: 10Gi
  readReplicas:
    persistence:
      enabled: true
      size: 10Gi

# Prometheus configuration
prometheus:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s

# Grafana configuration
grafana:
  enabled: true
  adminPassword: ""

# OpenTelemetry configuration
otel:
  enabled: true
  collector:
    enabled: true
  agent:
    enabled: true

# Ingress configuration
certManager:
  enabled: true
  issuer:
    name: letsencrypt-prod
    kind: ClusterIssuer

# Pod Disruption Budget
pdb:
  enabled: true
  minAvailable: 2
'''

# templates/deployment.yaml
DEPLOYMENT_TEMPLATE = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "aisupport.fullname" . }}
  labels:
    {{- include "aisupport.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "aisupport.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "aisupport.selectorLabels" . | nindent 8 }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "aisupport.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
        - name: {{ .Chart.Name }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8080
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 3
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          env:
            - name: ENV
              value: {{ .Values.config.environment | quote }}
            - name: LOG_LEVEL
              value: {{ .Values.config.logLevel | quote }}
            {{- if .Values.redis.enabled }}
            - name: REDIS_URL
              value: {{ printf "redis://%s-redis-master:6379" .Release.Name }}
            {{- end }}
            {{- if .Values.postgresql.enabled }}
            - name: DATABASE_URL
              value: {{ printf "postgresql://%s:%s@%s-postgresql:5432/%s" .Values.postgresql.auth.username .Values.postgresql.auth.password .Release.Name .Values.postgresql.auth.database }}
            {{- end }}
          {{- if .Values.otel.enabled }}
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: {{ printf "http://%s-otel-collector:4317" .Release.Name }}
          {{- end }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
'''

# templates/service.yaml
SERVICE_TEMPLATE = '''apiVersion: v1
kind: Service
metadata:
  name: {{ include "aisupport.fullname" . }}
  labels:
    {{- include "aisupport.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: {{ .Values.service.targetPort }}
      protocol: TCP
      name: http
  selector:
    {{- include "aisupport.selectorLabels" . | nindent 4 }}
'''

# templates/hpa.yaml
HPA_TEMPLATE = '''{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "aisupport.fullname" . }}
  labels:
    {{- include "aisupport.labels" . | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "aisupport.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    {{- if .Values.autoscaling.targetCPUUtilizationPercentage }}
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
    {{- end }}
    {{- if .Values.autoscaling.targetMemoryUtilizationPercentage }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetMemoryUtilizationPercentage }}
    {{- end }}
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
    scaleUp:
      stabilizationWindowSeconds: 0
{{- end }}
'''

# templates/pdb.yaml
PDB_TEMPLATE = '''{{- if .Values.pdb.enabled }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "aisupport.fullname" . }}
  labels:
    {{- include "aisupport.labels" . | nindent 4 }}
spec:
  {{- if .Values.pdb.minAvailable }}
  minAvailable: {{ .Values.pdb.minAvailable }}
  {{- else if .Values.pdb.maxUnavailable }}
  maxUnavailable: {{ .Values.pdb.maxUnavailable }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "aisupport.selectorLabels" . | nindent 4 }}
{{- end }}
'''

# templates/ingress.yaml
INGRESS_TEMPLATE = '''{{- if .Values.ingress.enabled -}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "aisupport.fullname" . }}
  labels:
    {{- include "aisupport.labels" . | nindent 4 }}
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  {{- if .Values.ingress.tls }}
  tls:
    {{- range .Values.ingress.tls }}
    - secretName: {{ .secretName }}
      hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
    {{- end }}
  {{- end }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ $.Release.Name }}
                port:
                  number: {{ $.Values.service.port }}
          {{- end }}
    {{- end }}
{{- end }}
'''

# helpers.tpl
HELPERS_TPL = '''{{/*
Expand the name of the chart.
*/}}
{{- define "aisupport.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "aisupport.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "aisupport.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "aisupport.labels" -}}
helm.sh/chart: {{ include "aisupport.chart" . }}
{{ include "aisupport.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "aisupport.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aisupport.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "aisupport.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "aisupport.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
'''

def write_helm_files(output_dir):
    """Write Helm chart files."""
    import os
    from pathlib import Path
    
    base = Path(output_dir)
    
    # Chart files
    (base / "Chart.yaml").write_text(CHART_YAML)
    (base / "values.yaml").write_text(VALUES_YAML)
    
    # Templates
    templates = base / "templates"
    templates.mkdir(exist_ok=True)
    
    (templates / "deployment.yaml").write_text(DEPLOYMENT_TEMPLATE)
    (templates / "service.yaml").write_text(SERVICE_TEMPLATE)
    (templates / "hpa.yaml").write_text(HPA_TEMPLATE)
    (templates / "pdb.yaml").write_text(PDB_TEMPLATE)
    (templates / "ingress.yaml").write_text(INGRESS_TEMPLATE)
    
    # Helpers
    (templates / "_helpers.tpl").write_text(HELPERS_TPL)
    
    # Note about templates
    print("Helm chart structure created. Note: templates are simplified - in production use complete Helm templates.")


if __name__ == "__main__":
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "."
    write_helm_files(output)
