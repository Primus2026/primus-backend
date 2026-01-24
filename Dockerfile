# Stage 1: Unified Builder
FROM python:3.11-slim as builder
WORKDIR /app
RUN pip install --no-cache-dir poetry

# Copy the TOML with the CPU source config
COPY pyproject.toml poetry.lock* ./

# 1. Build Backend Venv (Lightweight, No AI)
RUN poetry config virtualenvs.in-project true \
    && poetry install --without ai --no-interaction --no-ansi --no-root \
    && mv .venv .venv-backend

# 2. Build Worker Venv (Includes AI + GPU Torch support)
# Poetry will pull standard wheels from PyPI which support CUDA
RUN rm -rf .venv \
    && poetry config virtualenvs.in-project true \
    && poetry install --with ai --no-interaction --no-ansi --no-root \
    && mv .venv .venv-worker

# Stage 2: Backend Runtime
FROM python:3.11-slim as backend
WORKDIR /app
RUN apt-get update && apt-get install -y fonts-dejavu && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 1000 appuser && useradd -r -u 1000 -g appuser appuser
COPY --from=builder --chown=appuser:appuser /app/.venv-backend /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY --chown=appuser:appuser . .
RUN mkdir -p /data /data/reports /data/media /data/models /data/datasets /data/media && chown -R appuser:appuser /data
USER appuser
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

# Stage 3: Worker Runtime
FROM python:3.11-slim as worker
WORKDIR /app
# Install libs for OpenCV (GL/X11 stubs)
RUN apt-get update && apt-get install -y fonts-dejavu ffmpeg libsm6 libxext6 && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 1000 appuser && useradd -r -u 1000 -g appuser appuser
COPY --from=builder --chown=appuser:appuser /app/.venv-worker /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY --chown=appuser:appuser . .
RUN mkdir -p /data /data/reports /data/media /data/models /data/datasets /data/media && chown -R appuser:appuser /data
USER appuser
CMD ["python", "-m", "celery", "-A", "app.core.celery_worker.celery_app", "worker", "-l", "info", "-c", "4"]