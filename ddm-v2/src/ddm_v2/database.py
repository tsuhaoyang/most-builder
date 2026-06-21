from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ddm_v2.settings import get_settings

logger = logging.getLogger(__name__)


def get_engine():
    settings = get_settings()
    is_production = os.getenv("ENV", "development").lower() in {"production", "prod"}

    echo = settings.database_echo
    if echo and is_production:
        logger.warning(
            "DATABASE_ECHO=true is set in a production environment. "
            "SQL logging will expose sensitive query data. "
            "Set DATABASE_ECHO=false for production."
        )
        echo = False

    return create_async_engine(
        settings.database_url,
        echo=echo,
        pool_size=10,
        max_overflow=20,
    )


_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
