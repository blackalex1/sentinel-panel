# Stage 1: Build dependencies
FROM python:3.14-slim AS builder

# Set working directory
WORKDIR /app

# Configure virtual environment
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV UV_COMPILE_BYTECODE=1

# Install uv directly and create virtualenv
RUN pip install --no-cache-dir uv && \
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

# Install runtime system dependencies (including procps, psmisc, and iputils-ping)
RUN apt-get update && apt-get install -y --no-install-recommends \
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
COPY register_node.py /app/

# Set volume mount points
VOLUME [ "/app/config", "/app/bin" ]

# Run the backend as a module
CMD ["python", "-m", "backend.main"]
