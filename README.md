# Primus 2026 Backend

This directory contains the FastAPI backend application for the Primus 2026 Warehouse System.

## Project Structure

The project follows a standard FastAPI directory structure:

```
primus-backend/
├── app/
│   ├── main.py           # Application entry point
│   ├── api/              # API Routes (The HTTP Layer)
│   │   └── v1/           # Version 1 endpoints
│   ├── core/             # Cross-cutting concerns (Config, Logging)
│   ├── database/         # Data Persistence (SQLAlchemy models, Session)
│   │   ├── session.py    # Engine and SessionLocal
│   │   └── models.py     # Database Tables
│   ├── models/           # Data Validation (Pydantic Schemas)
│   └── services/         # Business Logic (Repositories)
├── tests/                # Tests
├── pyproject.toml        # Poetry dependencies
└── Dockerfile            # Docker image definition
```

## Development Rules

1.  **Dependency Management**: Use `poetry`.

2.  **Layered Architecture**:
    *   **api/**: Thin routes. No logic. Call services.
    *   **services/**: Business logic and DB interactions.
    *   **models/**: Pydantic schemas ONLY.
    *   **database/**: SQLAlchemy models ONLY.

## Running Locally

### Option 1: Docker (Recommended)
Run the entire stack from the `primus-infra` directory:
```bash
cd ../primus-infra
docker compose up --build
```

### Option 2: Standalone (Dev)
Requires running Postgres/Redis separately.
```bash
poetry install
poetry run uvicorn app.main:app --reload
```
