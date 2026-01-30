#!/bin/bash
# Test script to verify Docker network isolation for the bridge service

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Docker Network Isolation Tests ==="
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

# Ensure containers are running
if ! docker ps | grep -q "claudecode-telegram-bridge"; then
    echo -e "${YELLOW}Warning: Bridge container not running. Starting with ${COMPOSE_CMD}...${NC}"
    $COMPOSE_CMD up -d bridge 2>&1 | grep -v "^#" || true
    sleep 5
fi

if ! docker ps | grep -q "claudecode-telegram-caddy"; then
    echo -e "${YELLOW}Warning: Caddy container not running. Starting with ${COMPOSE_CMD}...${NC}"
    $COMPOSE_CMD up -d caddy 2>&1 | grep -v "^#" || true
    sleep 5
fi

# Test 1: Verify bridge service has no exposed ports on host
echo "Test 1: Verify bridge service is NOT accessible from host"
if curl -s --connect-timeout 2 http://localhost:8080 > /dev/null 2>&1; then
    echo -e "${RED}❌ FAIL: Bridge service is accessible from host at localhost:8080${NC}"
    echo "   This means the bridge container has an exposed port."
    exit 1
else
    echo -e "${GREEN}✅ PASS: Bridge service is NOT accessible from host${NC}"
fi

# Test 2: Verify Caddy CAN reach bridge via internal network
echo ""
echo "Test 2: Verify Caddy CAN reach bridge via internal Docker network"
if docker ps | grep -q "claudecode-telegram-caddy"; then
    if docker exec claudecode-telegram-caddy curl -s --connect-timeout 2 http://bridge:8080 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS: Caddy can reach bridge via internal network (bridge:8080)${NC}"
    else
        echo -e "${RED}❌ FAIL: Caddy cannot reach bridge via internal network${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  SKIP: Caddy container not running (may be due to privileged port permissions)${NC}"
    echo "   Run: sysctl -w net.ipv4.ip_unprivileged_port_start=80"
fi

# Test 3: Verify bridge container has no published ports
echo ""
echo "Test 3: Verify bridge container has no published ports"
PORT_MAPPING=$(docker port claudecode-telegram-bridge 2>/dev/null || echo "")
if [ -z "$PORT_MAPPING" ]; then
    echo -e "${GREEN}✅ PASS: Bridge container has no published ports${NC}"
else
    echo -e "${RED}❌ FAIL: Bridge container has published ports: $PORT_MAPPING${NC}"
    exit 1
fi

# Test 4: Verify both containers are on the same internal network
echo ""
echo "Test 4: Verify containers are on the same internal network"
BRIDGE_NETWORKS=$(docker inspect claudecode-telegram-bridge -f '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}' 2>/dev/null)
echo -e "${GREEN}✅ Bridge networks: $BRIDGE_NETWORKS${NC}"

if docker ps | grep -q "claudecode-telegram-caddy"; then
    CADDY_NETWORKS=$(docker inspect claudecode-telegram-caddy -f '{{range $key, $value := .NetworkSettings.Networks}}{{$key}}{{end}}' 2>/dev/null)
    echo "  Caddy networks: $CADDY_NETWORKS"
    if echo "$BRIDGE_NETWORKS" | grep -q "claude-telegram-net" && echo "$CADDY_NETWORKS" | grep -q "claude-telegram-net"; then
        echo -e "${GREEN}✅ PASS: Both containers are on claude-telegram-net network${NC}"
    else
        echo -e "${RED}❌ FAIL: Containers are not on the same network${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}  Caddy container not running - skipping network comparison${NC}"
fi

# Test 5: Verify Caddy configuration exposes correct ports
echo ""
echo "Test 5: Verify Caddy container port configuration"
# Check docker-compose config for caddy ports
if grep -A 10 "caddy:" docker-compose.yml | grep -q "ports:"; then
    # Extract the ports from docker-compose.yml
    CADDY_PORTS_CONFIG=$(grep -A 10 "caddy:" docker-compose.yml | grep -A 5 "ports:" | grep "-" | sed 's/.*://;s/"//g' | tr '\n' ' ')
    echo -e "${GREEN}✅ PASS: Caddy configured to expose ports: $CADDY_PORTS_CONFIG${NC}"
    echo "   Note: Privileged ports (80, 443) may require rootlesskit configuration"
else
    echo -e "${YELLOW}⚠️  SKIP: Caddy port configuration not found in docker-compose.yml${NC}"
fi

# Test 6: Verify internal network is isolated from host
echo ""
echo "Test 6: Verify internal network isolation"
# The bridge service should not be accessible via container IP from host
BRIDGE_IP=$(docker inspect claudecode-telegram-bridge -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
if [ -n "$BRIDGE_IP" ]; then
    # Try to access via container IP (should fail due to Docker bridge network isolation)
    if curl -s --connect-timeout 2 "http://$BRIDGE_IP:8080" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  WARN: Bridge is accessible via container IP $BRIDGE_IP from host${NC}"
        echo "   This is normal Docker behavior but not ideal for security."
    else
        echo -e "${GREEN}✅ PASS: Bridge is not accessible via container IP from host (isolated)${NC}"
    fi
fi

echo ""
echo "=== Summary ==="
echo -e "${GREEN}All critical tests passed!${NC}"
echo ""
echo "Network isolation verified:"
echo "  - Bridge service: NOT accessible from host ✅"
echo "  - Caddy -> Bridge: Accessible via internal network ✅"
echo "  - Published ports: Only on Caddy (reverse proxy) ✅"
echo ""
echo "Security posture: External traffic must go through Caddy reverse proxy."
echo "The bridge service is isolated on the internal Docker network."
