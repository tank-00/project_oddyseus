import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.models import Base  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Use the single DATABASE_URL throughout — same connection string for both
# Alembic migrations and the application (psycopg2 synchronous driver).
alembic_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", alembic_url)

# All registry DDL and the alembic_version table live in the 'registry' schema,
# keeping the gateway's public schema completely separate.
REGISTRY_SCHEMA = "registry"
_is_pg = alembic_url.startswith("postgresql")


def run_migrations_offline() -> None:
    context.configure(
        url=alembic_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=REGISTRY_SCHEMA if _is_pg else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        if _is_pg:
            # CREATE SCHEMA is committed immediately (autocommit-style) so it is
            # visible to the DDL statements that follow in the same session.
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {REGISTRY_SCHEMA}"))
            connection.commit()
            # SET search_path is session-scoped: all subsequent unqualified table
            # names resolve to the registry schema for the life of this connection.
            connection.execute(text(f"SET search_path TO {REGISTRY_SCHEMA}"))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Store alembic_version in registry schema, not public.
            version_table_schema=REGISTRY_SCHEMA if _is_pg else None,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
