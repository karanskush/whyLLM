"""Alembic migration environment — async engine, reads settings from pydantic-settings.

All ORM models are imported via llmdawg_api.models so their metadata is registered
with Base.metadata before autogenerate runs. Add new model modules to that package's
__init__.py — no changes needed here.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from llmdawg_api.config import get_settings
from llmdawg_api.database import Base

# Side-effect import — registers all ORM models with Base.metadata
import llmdawg_api.models  # noqa: F401

config = context.config
settings = get_settings()

# Inject DATABASE_URL from pydantic-settings — alembic.ini has no secrets
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline mode — emit SQL to stdout, no live connection required."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        # Partitioned tables and trigger functions are managed via raw DDL;
        # tell autogenerate to skip them to avoid false positives.
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _include_object(object, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Filter out PostgreSQL system objects from autogenerate diffs."""
    # Skip any table whose name starts with 'spans_' — those are partitions
    if type_ == "table" and name.startswith("spans_"):
        return False
    return True


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
