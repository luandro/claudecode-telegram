# Build stage - compiles tmux from source
FROM python:3.13-slim AS tmux-builder

# Build dependencies for tmux compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    bison \
    libevent-dev \
    libncurses-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Compile tmux with error handling
ENV TMUX_VERSION=3.6a
RUN echo "Downloading tmux ${TMUX_VERSION}..." && \
    curl -fL https://github.com/tmux/tmux/releases/download/${TMUX_VERSION}/tmux-${TMUX_VERSION}.tar.gz -o /tmp/tmux.tar.gz && \
    echo "Extracting..." && \
    tar xzf /tmp/tmux.tar.gz -C /tmp && \
    echo "Configuring..." && \
    cd /tmp/tmux-${TMUX_VERSION} && \
    ./configure && \
    echo "Compiling with $(nproc) threads..." && \
    make -j$(nproc) && \
    echo "Installing..." && \
    make install && \
    echo "Cleaning up..." && \
    cd / && \
    rm -rf /tmp/tmux-* && \
    echo "tmux ${TMUX_VERSION} installed successfully"

# Runtime stage
FROM python:3.13-slim

# Copy compiled tmux from builder (binary only - tmux doesn't create /usr/local/share/tmux)
COPY --from=tmux-builder /usr/local/bin/tmux /usr/local/bin/tmux

# Install runtime dependencies only
# libevent-core-2.1-7t64 provides libevent_core-2.1.so.7 needed by tmux
# The "t64" suffix is part of Debian's time64 transition
RUN apt-get update && apt-get install -y --no-install-recommends \
    libevent-core-2.1-7t64 \
    libncurses6 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Verify tmux installation and functionality
RUN tmux -V && \
    tmux new-session -d -s test_verification && \
    tmux kill-session -t test_verification && \
    echo "tmux ready and functional"

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml bridge.py ./
COPY claudecode_telegram/ /app/claudecode_telegram/
COPY hooks/ /app/hooks/

# Install the package
RUN pip install --no-cache-dir -e .

# Create directory for Claude config mount
RUN mkdir -p /claude

# Ensure logs are visible
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the bridge
CMD ["python", "bridge.py"]
