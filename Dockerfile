# Stage 1: Unified Builder
FROM python:3.11-slim as builder
WORKDIR /app
RUN pip install --no-cache-dir poetry
ENV POETRY_HTTP_TIMEOUT=2400
ENV POETRY_REQUESTS_TIMEOUT=2400
ENV PIP_DEFAULT_TIMEOUT=2400
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_INSTALLER_MAX_WORKERS=1

# Copy the TOML and lock file
COPY pyproject.toml poetry.lock* ./

# Build venvs: install lightweight backend first, then add AI deps for worker
RUN --mount=type=cache,target=/root/.cache/pypoetry \
    poetry install --without ai --no-interaction --no-ansi --no-root && \
    cp -r .venv .venv-backend && \
    poetry install --with ai --no-interaction --no-ansi --no-root && \
    mv .venv .venv-worker

# Stage 2: Backend Runtime
FROM python:3.11-slim as backend
WORKDIR /app
RUN apt-get update && apt-get install -y fonts-dejavu postgresql-client && rm -rf /var/lib/apt/lists/*
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
RUN apt-get update && apt-get install -y fonts-dejavu ffmpeg libsm6 libxext6 postgresql-client && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 1000 appuser && useradd -r -u 1000 -g appuser appuser
COPY --from=builder --chown=appuser:appuser /app/.venv-worker /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY --chown=appuser:appuser . .
RUN mkdir -p /data /data/reports /data/media /data/models /data/datasets /data/media && chown -R appuser:appuser /data
USER appuser
CMD ["python", "-m", "celery", "-A", "app.core.celery_worker.celery_app", "worker", "-l", "info", "-c", "4"]