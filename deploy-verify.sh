#!/bin/bash
# Deployment Verification Script for claudecode-telegram
# Run this script on the Ubuntu server to verify deployment readiness

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check functions
check_command() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 is installed"
        return 0
    else
        log_error "$1 is not installed"
        return 1
    fi
}

# Header
echo "======================================================"
echo "  claudecode-telegram Deployment Verification"
echo "======================================================"
echo ""

# Step 1: Environment Setup
log_info "Step 1: Checking environment setup..."

# Check required commands
REQUIRED_COMMANDS=("docker" "docker-compose" "tmux" "curl" "python3")
MISSING_COMMANDS=()

for cmd in "${REQUIRED_COMMANDS[@]}"; do
    if ! check_command "$cmd"; then
        MISSING_COMMANDS+=("$cmd")
    fi
done

if [ ${#MISSING_COMMANDS[@]} -ne 0 ]; then
    log_error "Missing required commands: ${MISSING_COMMANDS[*]}"
    echo ""
    echo "Install missing commands:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y docker.io docker-compose tmux curl python3"
    exit 1
fi

echo ""

# Step 2: .env file check
log_info "Step 2: Checking .env file..."

if [ ! -f .env ]; then
    log_error ".env file not found"
    echo ""
    echo "Create .env file from template:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    echo "Required variables:"
    echo "  - TELEGRAM_BOT_TOKEN"
    echo "  - TELEGRAM_WEBHOOK_SECRET"
    echo "  - DM_ALLOWED_USER_ID=244055394"
    echo "  - WEBHOOK_DOMAIN=coder.luandro.com"
    exit 1
else
    log_success ".env file exists"

    # Load .env
    source .env

    # Check critical variables
    CRITICAL_VARS=("TELEGRAM_BOT_TOKEN" "DM_ALLOWED_USER_ID")
    MISSING_VARS=()

    for var in "${CRITICAL_VARS[@]}"; do
        if [ -z "${!var}" ]; then
            MISSING_VARS+=("$var")
        else
            log_success "$var is set"
        fi
    done

    if [ ${#MISSING_VARS[@]} -ne 0 ]; then
        log_error "Missing required environment variables: ${MISSING_VARS[*]}"
        exit 1
    fi

    # Verify DM_ALLOWED_USER_ID is correct
    if [ "$DM_ALLOWED_USER_ID" != "244055394" ]; then
        log_warning "DM_ALLOWED_USER_ID is $DM_ALLOWED_USER_ID (expected: 244055394)"
    else
        log_success "DM_ALLOWED_USER_ID correctly set to 244055394"
    fi

    # Check optional but recommended variables
    if [ -z "$TELEGRAM_WEBHOOK_SECRET" ]; then
        log_warning "TELEGRAM_WEBHOOK_SECRET not set (recommended for security)"
        echo "  Generate with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
    else
        log_success "TELEGRAM_WEBHOOK_SECRET is configured"
    fi
fi

echo ""

# Step 3: DNS Resolution
log_info "Step 3: Verifying DNS resolution..."

DOMAIN="${WEBHOOK_DOMAIN:-coder.luandro.com}"

if SERVER_IP=$(dig +short "$DOMAIN" | head -1); then
    if [ -n "$SERVER_IP" ]; then
        log_success "DNS resolves: $DOMAIN → $SERVER_IP"
    else
        log_error "DNS resolution failed: $DOMAIN does not resolve"
        exit 1
    fi
else
    log_error "DNS lookup failed for $DOMAIN"
    exit 1
fi

echo ""

# Step 4: tmux Session
log_info "Step 4: Checking tmux session..."

TMUX_SESSION="${TMUX_SESSION:-claude}"

if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    log_success "tmux session '$TMUX_SESSION' is running"
else
    log_error "tmux session '$TMUX_SESSION' not found"
    echo ""
    echo "Start tmux session:"
    echo "  tmux new -s $TMUX_SESSION"
    echo "  # In tmux: claude --dangerously-skip-permissions"
    echo "  # Detach: Ctrl+b d"
    exit 1
fi

echo ""

# Step 5: Docker Stack
log_info "Step 5: Checking Docker stack..."

# Check if containers exist
if docker-compose ps | grep -q "claudecode-telegram"; then
    log_success "Docker stack exists"

    # Check if running
    if docker-compose ps | grep -q "Up"; then
        log_success "Containers are running"

        # Show status
        echo ""
        docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Health}}"
        echo ""

        # Check health
        if docker-compose ps | grep "bridge" | grep -q "healthy"; then
            log_success "Bridge container is healthy"
        else
            log_warning "Bridge container health check not passing"
        fi
    else
        log_warning "Containers exist but are not running"
        echo ""
        echo "Start containers:"
        echo "  docker-compose up -d"
    fi
else
    log_warning "Docker stack not started"
    echo ""
    echo "Start Docker stack:"
    echo "  docker-compose up -d"
fi

echo ""

# Step 6: Webhook Configuration
log_info "Step 6: Checking webhook configuration..."

if docker-compose ps | grep -q "bridge.*Up"; then
    # Get webhook info
    WEBHOOK_INFO=$(docker-compose exec -T bridge claudecode-telegram get-webhook-info 2>/dev/null || echo "{}")

    if echo "$WEBHOOK_INFO" | grep -q "\"ok\": true"; then
        WEBHOOK_URL=$(echo "$WEBHOOK_INFO" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('result', {}).get('url', 'NOT SET'))" 2>/dev/null || echo "NOT SET")

        if [ "$WEBHOOK_URL" != "NOT SET" ] && [ -n "$WEBHOOK_URL" ]; then
            log_success "Webhook is configured: $WEBHOOK_URL"

            # Check for errors
            PENDING_COUNT=$(echo "$WEBHOOK_INFO" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('result', {}).get('pending_update_count', 0))" 2>/dev/null || echo "0")

            if [ "$PENDING_COUNT" -gt 0 ]; then
                log_warning "Webhook has $PENDING_COUNT pending updates (delivery issues)"
            else
                log_success "No pending webhook updates"
            fi
        else
            log_warning "Webhook not configured"
            echo ""
            echo "Set webhook:"
            echo "  docker-compose exec bridge claudecode-telegram set-webhook --domain $DOMAIN"
        fi
    else
        log_error "Failed to get webhook info"
    fi
else
    log_warning "Cannot check webhook (bridge container not running)"
fi

echo ""

# Step 7: HTTPS Connectivity
log_info "Step 7: Testing HTTPS connectivity..."

if curl -I -s -f -m 5 "https://$DOMAIN/health" >/dev/null 2>&1; then
    log_success "HTTPS endpoint is accessible: https://$DOMAIN/health"
else
    log_warning "HTTPS health endpoint not accessible (this may be expected if Caddy is still getting certificates)"
    echo "  Try manually: curl -I https://$DOMAIN/health"
fi

echo ""

# Summary
echo "======================================================"
echo "  Verification Summary"
echo "======================================================"
echo ""

# Generate checklist
CHECKS_PASSED=0
CHECKS_TOTAL=0

check_result() {
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    if [ "$1" = "0" ]; then
        log_success "$2"
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
    else
        log_error "$2"
    fi
}

# Evaluate results
[ -n "$TELEGRAM_BOT_TOKEN" ]; check_result $? "Environment configured"
[ "$DM_ALLOWED_USER_ID" = "244055394" ]; check_result $? "DM allowlist set correctly"
[ -n "$SERVER_IP" ]; check_result $? "DNS resolves"
tmux has-session -t "$TMUX_SESSION" 2>/dev/null; check_result $? "tmux session running"
docker-compose ps | grep -q "bridge.*Up.*healthy"; check_result $? "Docker stack healthy"

echo ""
echo "Results: $CHECKS_PASSED/$CHECKS_TOTAL checks passed"
echo ""

if [ "$CHECKS_PASSED" -eq "$CHECKS_TOTAL" ]; then
    log_success "All critical checks passed!"
    echo ""
    echo "Next steps:"
    echo "  1. Run QA tests (see VERIFICATION_SUMMARY.md)"
    echo "  2. Test DM from user 244055394"
    echo "  3. Verify end-to-end message flow"
    echo ""
    echo "For detailed testing:"
    echo "  RUN_DEPLOYMENT_CHECKS=1 pytest tests/test_https_connectivity.py -m integration"
    exit 0
else
    log_warning "Some checks failed. Review errors above."
    echo ""
    echo "See VERIFICATION_SUMMARY.md for troubleshooting steps."
    exit 1
fi
