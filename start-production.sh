#!/bin/bash
# Start Claude-Telegram Bridge with Caddy (production deployment with public IP)

set -e

# Source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

echo "Starting Claude-Telegram Bridge in production mode..."
echo ""

# Validate and load environment
validate_env_file
load_env_file

# Set deployment mode
export DEPLOYMENT_MODE=production

# Validate WEBHOOK_DOMAIN is set
if [ -z "$WEBHOOK_DOMAIN" ]; then
    log_error "WEBHOOK_DOMAIN not set in .env"
    echo "Please set your domain (e.g., WEBHOOK_DOMAIN=coder.luandro.com)"
    exit 1
fi

# Validate domain format (basic check)
if ! echo "$WEBHOOK_DOMAIN" | grep -qE '^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'; then
    log_error "Invalid WEBHOOK_DOMAIN format: $WEBHOOK_DOMAIN"
    echo "Expected format: example.com or subdomain.example.com"
    exit 1
fi

echo "Mode: production"
echo "Domain: $WEBHOOK_DOMAIN"
echo ""

# Ensure tmux session exists
ensure_tmux_session

# Check port configuration
CADDY_HTTP_PORT=${CADDY_HTTP_PORT:-8081}
CADDY_HTTPS_PORT=${CADDY_HTTPS_PORT:-8443}

if [ "$CADDY_HTTP_PORT" = "80" ] || [ "$CADDY_HTTPS_PORT" = "443" ]; then
    echo "Using privileged ports (80/443)"
    echo "Checking if system allows unprivileged port binding..."

    PORT_START=$(sysctl -n net.ipv4.ip_unprivileged_port_start 2>/dev/null || echo "1024")
    if [ "$PORT_START" -gt "80" ]; then
        echo ""
        log_warning "System does not allow binding to ports 80/443 for rootless Docker"
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
echo ""

# Wait for bridge service to be healthy and configure webhook
log_info "Waiting for bridge service..."
MAX_BRIDGE_WAIT=30
BRIDGE_ELAPSED=0

while [ $BRIDGE_ELAPSED -lt $MAX_BRIDGE_WAIT ]; do
    if docker_compose exec -T bridge curl -sf http://localhost:8080/health >/dev/null 2>&1; then
        echo "Bridge service is healthy"
        break
    fi
    sleep 2
    BRIDGE_ELAPSED=$((BRIDGE_ELAPSED + 2))
    echo -n "."
done
echo ""

# Configure webhook with retries
log_info "Configuring Telegram webhook..."
MAX_WEBHOOK_RETRIES=5
WEBHOOK_RETRY=0
WEBHOOK_SUCCESS=false

while [ $WEBHOOK_RETRY -lt $MAX_WEBHOOK_RETRIES ]; do
    if docker_compose exec -T bridge python bridge.py set-webhook --domain "$WEBHOOK_DOMAIN" 2>&1 | grep -q "Webhook configured"; then
        log_success "Webhook configured successfully"
        WEBHOOK_SUCCESS=true
        break
    fi

    WEBHOOK_RETRY=$((WEBHOOK_RETRY + 1))
    if [ $WEBHOOK_RETRY -lt $MAX_WEBHOOK_RETRIES ]; then
        echo "Retrying webhook configuration ($WEBHOOK_RETRY/$MAX_WEBHOOK_RETRIES)..."
        sleep 3
    fi
done

if [ "$WEBHOOK_SUCCESS" = false ]; then
    log_warning "Failed to configure webhook after $MAX_WEBHOOK_RETRIES attempts"
    echo "You can configure it manually:"
    echo "  docker compose exec bridge python bridge.py set-webhook --domain $WEBHOOK_DOMAIN"
fi

echo ""
log_success "Deployment complete!"
echo ""
echo "Check webhook status:"
echo "  docker compose exec bridge python bridge.py get-webhook-info"
echo ""
echo "Useful commands:"
echo "  Monitor logs:     docker compose logs -f bridge caddy"
echo "  Check status:     docker compose ps"
echo "  Health check:     docker compose exec bridge curl -s http://localhost:8080/health"
echo "  Verify webhook:   docker compose exec bridge python bridge.py verify-webhook"
echo "  Manual setup:     docker compose exec bridge python bridge.py set-webhook --domain $WEBHOOK_DOMAIN"
echo "  Stop services:    docker compose --profile production down"
echo ""
