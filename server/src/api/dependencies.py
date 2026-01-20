"""FastAPI dependency injection for database sessions and other resources."""

from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import AsyncSessionLocal, Database


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for async database session.

    Yields:
        AsyncSession: SQLAlchemy async session

    Usage:
        @app.get("/endpoint")
        async def endpoint(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionLocal() as session:
        yield session


def get_db() -> Generator[Database, None, None]:
    """
    Dependency injection for Database instance (legacy sync wrapper).

    Yields:
        Database: Database instance with sync API

    Usage:
        @app.get("/endpoint")
        def endpoint(db: Database = Depends(get_db)):
            ...
    """
    db = Database()
    try:
        yield db
    finally:
        # Database cleanup if needed
        pass
