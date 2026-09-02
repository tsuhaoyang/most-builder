---
name: db-schema
description: Work with PostgreSQL database schema, migrations, and data models
---

# Database Schema Development

Handle PostgreSQL database schema changes, migrations, and model updates for DDM v2:

## Database Technology
- **PostgreSQL**: Primary database with JSONB support
- **SQLAlchemy 2.0**: Async ORM with modern patterns
- **Alembic**: Database migration management
- **AsyncPG**: Async PostgreSQL driver

## Migration Workflow
- **Generate Migration**: `PYTHONPATH=src alembic revision --autogenerate -m "description"`
- **Review Changes**: Always inspect auto-generated migration files
- **Apply Migration**: `PYTHONPATH=src alembic upgrade head`
- **Rollback**: `PYTHONPATH=src alembic downgrade -1`

## Model Standards
- **V2 Models**: All new models in `src/ddm_v2/models/v2/`
- **Async Patterns**: Use SQLAlchemy 2.0 async session patterns
- **Type Safety**: Full type hints with proper SQLAlchemy typing
- **JSONB Usage**: Store complex structured data in JSONB columns
- **Relationships**: Proper foreign keys and relationship definitions

## Data Integrity
- **Constraints**: Database-level constraints for data validation
- **Indexes**: Performance indexes for common queries
- **Seed Data**: Use scripts in `scripts/` for development data
- **Backup Strategy**: Regular dumps for data protection

## Common Patterns
- **Audit Fields**: created_at, updated_at timestamps
- **Soft Deletes**: Use status fields instead of hard deletes where appropriate
- **RBAC Integration**: User and role relationship patterns
- **Versioning**: Support for draft/published content workflows

Please work on: $ARGUMENTS

Always test migrations against a copy of production-like data before applying.