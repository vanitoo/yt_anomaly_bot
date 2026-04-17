"""
Alembic environment configuration.

Supports async SQLAlchemy engines (aiosqlite / asyncpg).
Reads DATABASE_URL from .env automatically.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make sure the project root is on sys.path so `bot.*` imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.models.orm import Base  # noqa: E402  (must come after sys.path fix)

# Load .env so DATABASE_URL is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment variable if set
database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db")
config.set_main_option("sqlalchemy.url", database_url)

# Set up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata object for 'autogenerate' support
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — generate SQL without a live connection
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Renders SQL to stdout / a file instead of executing against a live DB.
    Useful for generating migration scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — run against a live async engine
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations inside a sync wrapper."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run async migrations using the current or new event loop."""
    try:
        # Try to get the running event loop
        loop = asyncio.get_running_loop()
        # If we're inside an existing loop, schedule migrations as a task
        asyncio.ensure_future(run_async_migrations())
    except RuntimeError:
        # No running loop, create a new one
        asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
