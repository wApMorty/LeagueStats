"""Alembic environment configuration for PostgreSQL migrations.

This file is executed when running Alembic commands (upgrade, downgrade, revision, etc.).
It configures:
- Database connection from environment variables (.env file)
- Async engine for PostgreSQL with asyncpg driver
- Metadata target for autogenerate (src.db.Base.metadata)
"""

import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import models and configuration
import sys
from pathlib import Path

# Add parent directory to path to import src module
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import Base  # Import Base to get metadata
from src.config import settings  # Import settings to get DATABASE_URL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url with DATABASE_URL from .env
# Convert postgresql:// to postgresql+asyncpg://
db_url = settings.database_url
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Remove psycopg2-specific parameters that are incompatible with asyncpg
# Replace sslmode=require with ssl=require
if "?" in db_url:
    base_url, params = db_url.split("?", 1)
    # Remove sslmode and channel_binding (psycopg2 params)
    # asyncpg uses ssl=require instead
    import urllib.parse

    parsed_params = urllib.parse.parse_qs(params)

    # For Neon, we need ssl='require' as a connect_arg
    # But for the URL, we can omit it as Neon enforces SSL by default
    # Remove psycopg2-specific params
    parsed_params.pop('sslmode', None)
    parsed_params.pop('channel_binding', None)

    # Rebuild URL without incompatible params
    if parsed_params:
        new_params = urllib.parse.urlencode(parsed_params, doseq=True)
        db_url = f"{base_url}?{new_params}"
    else:
        db_url = base_url

config.set_main_option("sqlalchemy.url", db_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Get configuration for async engine
    configuration = config.get_section(config.config_ini_section, {})

    # Create async engine
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection pooling for migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
