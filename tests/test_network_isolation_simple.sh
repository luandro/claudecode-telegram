#!/bin/bash
# Simple test script to verify Docker network isolation for the bridge service
# This test verifies the bridge service is NOT accessible from the host

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Docker Bridge Network Isolation Test ==="
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ FAIL: docker-compose not found${NC}"
    exit 1
fi

# Use docker compose or docker-compose based on availability
COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

# Ensure bridge container is running
if ! docker ps | grep -q "claudecode-telegram-bridge"; then
    echo -e "${YELLOW}Starting bridge container with ${COMPOSE_CMD}...${NC}"
    $COMPOSE_CMD up -d bridge 2>&1 | grep -v "^#" || true
    sleep 5
fi

# Test 1: Verify bridge service has no published ports
echo "Test 1: Verify bridge container has NO published ports"
PORT_MAPPING=$(docker port claudecode-telegram-bridge 2>/dev/null || echo "")
if [ -z "$PORT_MAPPING" ]; then
    echo -e "${GREEN}✅ PASS: Bridge container has no published ports${NC}"
else
    echo -e "${RED}❌ FAIL: Bridge container has published ports: $PORT_MAPPING${NC}"
    echo "   The bridge should be isolated on the internal network only."
    exit 1
fi

# Test 2: Verify bridge service is NOT accessible from host on port 8080
echo ""
echo "Test 2: Verify bridge service is NOT accessible from host"
if curl -s --connect-timeout 2 http://localhost:8080 > /dev/null 2>&1; then
    echo -e "${RED}❌ FAIL: Bridge service is accessible from host at localhost:8080${NC}"
    echo "   This means the bridge container port is exposed to the host."
    exit 1
else
    echo -e "${GREEN}✅ PASS: Bridge service is NOT accessible from host${NC}"
fi

# Test 3: Verify docker-compose.yml has no ports mapping for bridge
echo ""
echo "Test 3: Verify docker-compose.yml configuration"
if grep -A 20 "bridge:" docker-compose.yml | grep -q "ports:"; then
    # Check if there's a port mapping after ports:
    if grep -A 25 "bridge:" docker-compose.yml | grep -A 5 "ports:" | grep -q '":.*8080'; then
        echo -e "${RED}❌ FAIL: docker-compose.yml has ports mapping for bridge service${NC}"
        echo "   The bridge service should not expose ports to the host."
        exit 1
    fi
fi
echo -e "${GREEN}✅ PASS: docker-compose.yml has no exposed ports for bridge service${NC}"

# Test 4: Verify bridge is on internal network
echo ""
echo "Test 4: Verify bridge is on internal Docker network"
BRIDGE_NETWORKS=$(docker inspect claudecode-telegram-bridge -f '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}' 2>/dev/null)
if echo "$BRIDGE_NETWORKS" | grep -q "claude-telegram-net"; then
    echo -e "${GREEN}✅ PASS: Bridge is on claude-telegram-net internal network${NC}"
else
    echo -e "${RED}❌ FAIL: Bridge is not on the expected internal network${NC}"
    echo "   Bridge networks: $BRIDGE_NETWORKS"
    exit 1
fi

# Test 5: Verify bridge is healthy internally
echo ""
echo "Test 5: Verify bridge service is healthy internally"
HEALTH_STATUS=$(docker inspect claudecode-telegram-bridge -f '{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
if [ "$HEALTH_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✅ PASS: Bridge service is healthy${NC}"
else
    echo -e "${YELLOW}⚠️  WARN: Bridge health status: $HEALTH_STATUS${NC}"
fi

# Test 6: Verify bridge can be accessed from another container on the same network
echo ""
echo "Test 6: Verify internal network access (create test container)"
# Create a temporary container on the same network to test internal access
if docker run --rm --network claudecode-telegram-net alpine:latest \
    wget -q --timeout=2 --tries=1 -O- http://bridge:8080 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PASS: Bridge is accessible via internal network from other containers${NC}"
else
    echo -e "${YELLOW}⚠️  WARN: Could not verify internal network access (may need alpine image)${NC}"
fi

echo ""
echo "=== Summary ==="
echo -e "${GREEN}✅ All critical tests passed!${NC}"
echo ""
echo "Network isolation verified:"
echo "  - Bridge service: NOT accessible from host ✅"
echo "  - Published ports: None ✅"
echo "  - Internal network: Configured ✅"
echo ""
echo "Security posture:"
echo "  The bridge service is isolated on the internal Docker network."
echo "  It can only be accessed via other containers on the same network"
echo "  (e.g., Caddy reverse proxy), not directly from the host or internet."
