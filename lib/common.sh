#!/bin/bash
# Common functions for Claude Code Telegram bridge scripts
# Source this file in other scripts: source "$(dirname "$0")/lib/common.sh"

#-------------------------------------------------------------------------------
# Docker Compose Detection
#-------------------------------------------------------------------------------
docker_compose() {
    if docker compose version &>/dev/null 2>&1; then
        docker compose "$@"
    elif command -v docker-compose &>/dev/null 2>&1; then
        docker-compose "$@"
    else
        echo "Error: Neither 'docker compose' nor 'docker-compose' found" >&2
        echo "Please install Docker Compose to continue" >&2
        return 1
    fi
}

#-------------------------------------------------------------------------------
# Environment File Management
#-------------------------------------------------------------------------------
validate_env_file() {
    if [ ! -f .env ]; then
        echo "Error: .env file not found"
        echo "Please create .env from .env.example and configure your settings"
        exit 1
    fi
}

load_env_file() {
    set -a
    source .env
    set +a
}

#-------------------------------------------------------------------------------
# Tmux Session Management
#-------------------------------------------------------------------------------
ensure_tmux_session() {
    local session_name="${TMUX_SESSION:-claude}"
    local system_tmux="${SYSTEM_TMUX:-tmux}"  # Use PATH instead of hardcoded path

    # Check if tmux binary exists
    if ! command -v "$system_tmux" &>/dev/null; then
        log_error "tmux not found at '$system_tmux'"
        echo "Please install tmux: apt-get install tmux" >&2
        return 1
    fi

    # Verify tmux is functional
    if ! $system_tmux -V &>/dev/null; then
        log_error "tmux exists but is not functional"
        return 1
    fi

    # Check if session already exists
    if $system_tmux has-session -t "$session_name" 2>/dev/null; then
        return 0  # Session exists, nothing to do
    fi

    # Attempt to create session
    if ! $system_tmux new -s "$session_name" -d 2>/dev/null; then
        log_error "Failed to create tmux session '$session_name'"
        echo "Manual creation: tmux new -s $session_name" >&2
        return 1
    fi

    echo "Created tmux session '$session_name'"
    echo "  Attach with: tmux attach -t $session_name"
    echo ""
}

#-------------------------------------------------------------------------------
# Logging Functions
#-------------------------------------------------------------------------------
log_info() {
    echo -e "\033[0;34m[INFO]\033[0m $*"
}

log_success() {
    echo -e "\033[0;32m[OK]\033[0m $*"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $*" >&2
}

log_warning() {
    echo -e "\033[0;33m[WARN]\033[0m $*"
}
