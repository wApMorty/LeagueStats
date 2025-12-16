from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool, MetaData, Table, Column, Integer, String, Float, TIMESTAMP, ForeignKey, text

from alembic import context

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Define database schema as SQLAlchemy metadata for migration tracking
# This mirrors the schema created by src/db.py methods
target_metadata = MetaData()

# Champions table - Riot API integration schema
champions_table = Table(
    'champions',
    target_metadata,
    Column('id', Integer, primary_key=True),
    Column('key', String),
    Column('name', String, nullable=False),
    Column('title', String),
    Column('created_at', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
)

# Matchups table - Champion vs Champion statistics
matchups_table = Table(
    'matchups',
    target_metadata,
    Column('id', Integer, primary_key=True),
    Column('champion', Integer, ForeignKey('champions.id', ondelete='CASCADE'), nullable=False),
    Column('enemy', Integer, ForeignKey('champions.id', ondelete='CASCADE'), nullable=False),
    Column('winrate', Float, nullable=False),
    Column('delta1', Float, nullable=False),
    Column('delta2', Float, nullable=False),
    Column('pickrate', Float, nullable=False),
    Column('games', Integer, nullable=False)
)

# Champion scores table - Calculated tier list metrics
champion_scores_table = Table(
    'champion_scores',
    target_metadata,
    Column('id', Integer, ForeignKey('champions.id', ondelete='CASCADE'), primary_key=True),
    Column('avg_delta2', Float),
    Column('variance', Float),
    Column('coverage', Float),
    Column('peak_impact', Float),
    Column('volatility', Float),
    Column('target_ratio', Float)
)

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


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
