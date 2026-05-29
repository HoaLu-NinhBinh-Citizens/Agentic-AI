# TLS Certificates for Redis
# Generate self-signed certificates for development:
# openssl req -x509 -newkey rsa:4096 -keyout redis.key -out redis.crt -days 365 -nodes -subj "/CN=redis"
# openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt -days 365 -nodes -subj "/CN=Redis-CA"
#
# For production, use cert-manager or external secrets management (Vault, AWS Secrets Manager, etc.)

PLACEHOLDER=For development only - replace with actual certificate content
