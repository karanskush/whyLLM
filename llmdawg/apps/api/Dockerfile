# ============================================================
# whyllm API — Production Dockerfile
# Multi-stage build: build deps → runtime image
# Non-root user, no dev tools in the final image.
# ============================================================

# ---- Stage 1: dependency installer -------------------------
FROM python:3.11-slim AS builder

# Prevents Python from writing .pyc to disk and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build tools needed for compiled extensions (asyncpg, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only the project manifest first — layer cache is invalidated only
# when dependencies change, not every code edit.
COPY pyproject.toml ./

# Install into an isolated prefix so we can copy it cleanly to the runner
RUN pip install --prefix=/install "hatchling" && \
    pip install --prefix=/install .


# ---- Stage 2: runtime image ---------------------------------
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Minimal runtime packages only
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user — running as root in a container is a security risk
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy application source
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Set ownership
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Healthcheck — uses PORT if injected (Railway), falls back to 8000 (Docker Compose)
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run migrations then start the server.
# PORT is injected by Railway; falls back to 8000 for local Docker Compose.
CMD ["sh", "-c", "alembic upgrade head && uvicorn whyllm_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --loop uvloop --http h11 --access-log"]
