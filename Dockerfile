# Stage 1: Build dependencies
FROM python:3.14-slim AS builder

# Update base OS packages to patch known Debian vulnerabilities (util-linux, zlib1g)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Configure virtual environment
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV UV_COMPILE_BYTECODE=1

# Upgrade system pip, install uv, upgrade setuptools and create virtualenv
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --upgrade uv "setuptools>=78.1.1" && \
    uv venv $VIRTUAL_ENV
COPY requirements.txt /app/
RUN uv pip install --no-cache -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.14-slim

# trivy:ignore:AVD-DS-0002: Privilege dropping is handled dynamically via gosu appuser in docker-entrypoint.sh
# checkov:skip=CKV_DOCKER_3: Privilege dropping is handled dynamically via gosu appuser in docker-entrypoint.sh

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONPATH=/app

# Update base OS packages and install runtime system dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    openssl \
    procps \
    psmisc \
    curl \
    git \
    iputils-ping \
    iptables \
    nftables \
    gosu \
    libcap2-bin \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Upgrade system pip in runtime image to eliminate vendored package vulnerabilities
RUN pip install --no-cache-dir --upgrade pip

# Create unprivileged user (UID 1000) and configure passwordless sudo for network firewall tools
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    echo "appuser ALL=(ALL) NOPASSWD: /usr/sbin/iptables, /usr/sbin/nft, /usr/sbin/ip, /sbin/iptables, /sbin/nft, /sbin/ip" > /etc/sudoers.d/appuser && \
    chmod 0440 /etc/sudoers.d/appuser

# Transparent wrappers for iptables/nft allowing non-root appuser execution
RUN printf '#!/bin/sh\nif [ "$(id -u)" = "0" ]; then exec /usr/sbin/iptables "$@"; else exec sudo /usr/sbin/iptables "$@"; fi\n' > /usr/local/bin/iptables && \
    printf '#!/bin/sh\nif [ "$(id -u)" = "0" ]; then exec /usr/sbin/nft "$@"; else exec sudo /usr/sbin/nft "$@"; fi\n' > /usr/local/bin/nft && \
    chmod +x /usr/local/bin/iptables /usr/local/bin/nft

# Set working directory
WORKDIR /app

# Copy the virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy entrypoint script
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh && sed -i 's/\r$//' /app/docker-entrypoint.sh

# Copy application code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY dist-react/ /app/dist-react/
COPY bot/ /app/bot/
COPY locales/ /app/locales/
COPY updater/ /app/updater/
COPY host/ /app/host/
COPY update.sh /app/
COPY register_node.py /app/

# Set initial volume mount points and ownership
RUN mkdir -p /app/config /app/bin /app/backups /var/run/sentinel && \
    chown -R appuser:appuser /app /var/run/sentinel
VOLUME [ "/app/config", "/app/bin" ]

# Healthcheck to monitor service status (DS-0026)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || curl -f -k https://localhost:2053/ || exit 1

# Entrypoint performs volume permission normalization and drops privileges to appuser
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run the backend as a module (executed under appuser)
CMD ["python", "-m", "backend.main"]
