---
name: fastapi-dev
description: Develop and review FastAPI endpoints for DDM v2 MOST platform
---

# FastAPI Development for DDM v2

Develop or review FastAPI code following DDM v2 project conventions:

## API Structure
- **Version Prefix**: All endpoints use `/api/v2` prefix
- **Route Organization**: Group by domain (`/worksheets`, `/templates`, `/exports`, etc.)
- **Authentication**: Use `require_role()` dependency with RBAC (viewer < IE < manager < admin)
- **Response Format**: Follow Pydantic v2 schemas in `src/ddm_v2/schemas/v2/`

## Code Standards
- **Python 3.11+**: Target version from pyproject.toml
- **Async/Await**: Use SQLAlchemy 2.0 async patterns
- **Dependencies**: Import from `ddm_v2.api.deps` for DB sessions and auth
- **Error Handling**: Use structured error responses from `error_handlers.py`
- **Type Hints**: Full Pydantic v2 type annotations

## Database Patterns
- **Session Scope**: Use `Depends(get_db, scope="function")` for proper commit timing
- **Transactions**: Explicit commit/rollback in service layer
- **Model Access**: Use v2 models from `src/ddm_v2/models/v2/`
- **Migrations**: Alembic migrations in `migrations/` directory

## Testing
- **Unit Tests**: Mark with `@pytest.mark.unit` (no DB required)
- **Integration Tests**: Mark with `@pytest.mark.integration` (needs DATABASE_URL)
- **Fixtures**: Use existing test fixtures from `tests/` directory

Please work on: $ARGUMENTS

Follow the established patterns in `src/ddm_v2/api/routes/v2/` for consistency.