#!/bin/bash
# Start Claude-Telegram Bridge with Cloudflare Tunnel (local development)

set -e

echo "Starting Claude-Telegram Bridge with Cloudflare Tunnel..."
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

# Source .env and enforce tunnel mode
set -a
source .env
set +a

# Enforce tunnel mode (override any .env setting)
export DEPLOYMENT_MODE=tunnel

echo "Mode: tunnel (Cloudflare quick tunnel)"
echo ""

# Start containers with tunnel profile
docker_compose --profile tunnel up -d

echo ""
echo "Services starting... Webhook will auto-configure on startup."
echo "The bridge service will automatically detect the tunnel URL and register the webhook."
echo ""
echo "This process includes automatic retries and may take up to 60 seconds."
sleep 2

echo ""
echo "Deployment complete!"
echo ""
echo "Check webhook status:"
echo "  docker_compose exec bridge python bridge.py get-webhook-info"
echo ""
echo "Useful commands:"
echo "  View tunnel URL:  docker_compose logs cloudflared | grep trycloudflare.com"
echo "  Monitor logs:     docker_compose logs -f bridge"
echo "  Check status:     docker_compose ps"
echo "  Health check:     docker_compose exec bridge curl -s http://localhost:8080/health"
echo "  Verify webhook:   docker_compose exec bridge python bridge.py verify-webhook"
echo "  Stop services:    docker_compose --profile tunnel down"
echo ""
