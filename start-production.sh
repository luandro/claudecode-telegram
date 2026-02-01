#!/bin/bash
# Start Claude-Telegram Bridge with Caddy (production deployment with public IP)

set -e

echo "Starting Claude-Telegram Bridge in production mode..."
echo ""

# Detect and use appropriate docker compose command
docker_compose() {
    if docker compose version &>/dev/null 2>&1; then
        docker compose "$@"
    elif command -v docker-compose &>/dev/null 2>&1; then
        docker-compose "$@"
    else
        echo "Error: Neither 'docker compose' nor 'docker-compose' found" >&2
        return 1
    fi
}

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found"
    echo "Please create .env from .env.example and configure your settings"
    exit 1
fi

# Source .env to get configuration
set -a
source .env
set +a

# Enforce production mode (override any .env setting)
export DEPLOYMENT_MODE=production

# Validate WEBHOOK_DOMAIN is set
if [ -z "$WEBHOOK_DOMAIN" ]; then
    echo "Error: WEBHOOK_DOMAIN not set in .env"
    echo "Please set your domain (e.g., WEBHOOK_DOMAIN=coder.luandro.com)"
    exit 1
fi

# Validate domain format (basic check)
if ! echo "$WEBHOOK_DOMAIN" | grep -qE '^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'; then
    echo "Error: Invalid WEBHOOK_DOMAIN format: $WEBHOOK_DOMAIN"
    echo "Expected format: example.com or subdomain.example.com"
    exit 1
fi

echo "Mode: production"
echo "Domain: $WEBHOOK_DOMAIN"
echo ""

# Check port configuration
CADDY_HTTP_PORT=${CADDY_HTTP_PORT:-8081}
CADDY_HTTPS_PORT=${CADDY_HTTPS_PORT:-8443}

if [ "$CADDY_HTTP_PORT" = "80" ] || [ "$CADDY_HTTPS_PORT" = "443" ]; then
    echo "Using privileged ports (80/443)"
    echo "Checking if system allows unprivileged port binding..."

    PORT_START=$(sysctl -n net.ipv4.ip_unprivileged_port_start 2>/dev/null || echo "1024")
    if [ "$PORT_START" -gt "80" ]; then
        echo ""
        echo "Warning: System does not allow binding to ports 80/443 for rootless Docker"
        echo "Run this command to allow it:"
        echo "  echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee -a /etc/sysctl.conf && sudo sysctl -p"
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Start containers with production profile
docker_compose --profile production up -d

echo ""
echo "Services starting... Webhook will auto-configure on startup."
sleep 2

echo ""
echo "Deployment complete!"
echo ""
echo "Check webhook status:"
echo "  docker_compose exec bridge python bridge.py get-webhook-info"
echo ""
echo "Useful commands:"
echo "  Monitor logs:     docker_compose logs -f bridge caddy"
echo "  Check status:     docker_compose ps"
echo "  Health check:     docker_compose exec bridge curl -s http://localhost:8080/health"
echo "  Verify webhook:   docker_compose exec bridge python bridge.py verify-webhook"
echo "  Manual setup:     docker_compose exec bridge python bridge.py set-webhook --domain $WEBHOOK_DOMAIN"
echo "  Stop services:    docker_compose --profile production down"
echo ""
