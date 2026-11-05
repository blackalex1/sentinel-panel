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

# Install uv directly, upgrade setuptools and create virtualenv
RUN pip install --no-cache-dir --upgrade uv "setuptools>=78.1.1" && \
    uv venv $VIRTUAL_ENV
COPY requirements.txt /app/
RUN uv pip install --no-cache -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONPATH=/app

# Update base OS packages and install runtime system dependencies (including procps, psmisc, and iputils-ping)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    openssl \
    procps \
    psmisc \
    curl \
    git \
    iputils-ping \
    iptables \
    nftables \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

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

# Set volume mount points
VOLUME [ "/app/config", "/app/bin" ]

# Healthcheck to monitor service status (DS-0026)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || curl -f -k https://localhost:2053/ || exit 1

# Run the backend as a module
CMD ["python", "-m", "backend.main"]
