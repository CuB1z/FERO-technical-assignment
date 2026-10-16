from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


@cache
def get_engine() -> AsyncEngine:
    return create_async_engine(settings.DATABASE_URL)


@cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
        await session.commit()


DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
