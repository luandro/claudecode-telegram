#!/bin/bash
# Start Claude-Telegram Bridge with Cloudflare Tunnel (local development)

set -e

# Source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

echo "Starting Claude-Telegram Bridge with Cloudflare Tunnel..."
echo ""

# Validate and load environment
validate_env_file
load_env_file

# Enforce tunnel mode (override any .env setting)
export DEPLOYMENT_MODE=tunnel

echo "Mode: tunnel (Cloudflare quick tunnel)"
echo ""

# Ensure tmux session exists
ensure_tmux_session

# Start containers with tunnel profile
BRIDGE_MODE=tunnel docker_compose --profile tunnel up -d --force-recreate

echo ""
echo "Services starting... Webhook will auto-configure on startup."
echo "The bridge service will automatically detect the tunnel URL and register the webhook."
echo ""
echo "This process includes automatic retries and may take up to 2 minutes."

# Wait for cloudflared to start, be healthy, and extract tunnel URL
echo "Waiting for tunnel URL..."
TUNNEL_URL_FILE="${CLAUDE_DIR:-${HOME}/.claude}/cloudflared_tunnel_url"
MAX_WAIT=90
ELAPSED=0
TUNNEL_URL=""

while [ $ELAPSED -lt $MAX_WAIT ]; do
    # Extract tunnel URL from logs
    TUNNEL_URL=$(docker_compose logs cloudflared 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)

    if [ -n "$TUNNEL_URL" ]; then
        # Check if tunnel is actually registered and healthy
        if docker_compose logs cloudflared 2>/dev/null | grep -q "Registered tunnel connection"; then
            echo "$TUNNEL_URL" > "$TUNNEL_URL_FILE"
            echo "Tunnel URL detected and healthy: $TUNNEL_URL"
            break
        fi
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    echo -n "."
done

echo ""

if [ ! -f "$TUNNEL_URL_FILE" ]; then
    log_warning "Could not detect tunnel URL automatically"
    echo "The bridge will retry detection. You can also manually set the webhook:"
    echo "  docker_compose exec bridge python bridge.py set-webhook --domain <tunnel-url>"
    sleep 2
else
    # Tunnel URL found - now configure the webhook
    TUNNEL_DOMAIN=$(cat "$TUNNEL_URL_FILE" | sed 's|https://||')
    echo ""
    log_info "Configuring Telegram webhook..."

    # Wait for bridge service to be healthy
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
    MAX_WEBHOOK_RETRIES=5
    WEBHOOK_RETRY=0
    WEBHOOK_SUCCESS=false

    while [ $WEBHOOK_RETRY -lt $MAX_WEBHOOK_RETRIES ]; do
        if docker_compose exec -T bridge python bridge.py set-webhook --domain "$TUNNEL_DOMAIN" 2>&1 | grep -q "Webhook configured"; then
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
        echo "  docker compose exec bridge python bridge.py set-webhook --domain $TUNNEL_DOMAIN"
    fi
fi

echo ""
log_success "Deployment complete!"
echo ""
echo "Check webhook status:"
echo "  docker compose exec bridge python bridge.py get-webhook-info"
echo ""
echo "Useful commands:"
echo "  View tunnel URL:  docker compose logs cloudflared | grep trycloudflare.com"
echo "  Monitor logs:     docker compose logs -f bridge"
echo "  Check status:     docker compose ps"
echo "  Health check:     docker compose exec bridge curl -s http://localhost:8080/health"
echo "  Verify webhook:   docker compose exec bridge python bridge.py verify-webhook"
echo "  Stop services:    docker compose --profile tunnel down"
echo ""
