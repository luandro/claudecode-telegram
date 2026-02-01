#!/bin/bash
# Start Claude-Telegram Bridge with Cloudflare Tunnel (local development)

set -e

echo "Starting Claude-Telegram Bridge with Cloudflare Tunnel..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found"
    echo "Please create .env from .env.example and configure your settings"
    exit 1
fi

# Start containers with tunnel profile
docker-compose --profile tunnel up -d

echo ""
echo "Waiting for services to start..."
sleep 5

# Get the tunnel URL from cloudflared logs
echo ""
echo "Getting Cloudflare Tunnel URL..."
TUNNEL_URL=$(docker-compose logs cloudflared 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)

if [ -z "$TUNNEL_URL" ]; then
    echo "Warning: Could not automatically detect tunnel URL"
    echo "Check logs manually: docker-compose logs cloudflared"
    echo ""
    echo "Look for a line like:"
    echo "  https://random-name.trycloudflare.com"
else
    echo "Tunnel URL: $TUNNEL_URL"
    echo ""

    # Wait for DNS propagation
    echo "Waiting for DNS propagation (this can take 30-60 seconds)..."
    DOMAIN="${TUNNEL_URL#https://}"

    # Try to set webhook with retries
    echo "Setting Telegram webhook (with retries)..."
    for i in {1..6}; do
        echo "Attempt $i/6..."
        if docker-compose exec -T bridge python bridge.py set-webhook --domain "$DOMAIN" 2>&1 | grep -q "successfully"; then
            echo "✅ Webhook set successfully!"
            break
        else
            if [ $i -lt 6 ]; then
                echo "⏳ Waiting 10 seconds for DNS propagation..."
                sleep 10
            else
                echo "⚠️ Webhook setup failed after 6 attempts"
                echo ""
                echo "This is normal for quick tunnels. DNS propagation can take a few minutes."
                echo "Try setting the webhook manually in 1-2 minutes:"
                echo "  docker-compose exec bridge python bridge.py set-webhook --domain $DOMAIN"
            fi
        fi
    done
fi

echo ""
echo "Deployment complete!"
echo ""
echo "Useful commands:"
echo "  View tunnel URL:  docker-compose logs cloudflared | grep trycloudflare.com"
echo "  Monitor logs:     docker-compose logs -f bridge"
echo "  Check status:     docker-compose ps"
echo "  Stop services:    docker-compose --profile tunnel down"
echo ""
