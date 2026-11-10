from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import logging

from app.config import settings

logger = logging.getLogger("voxflow.database")


class Base(DeclarativeBase):
    pass


# Use PostgreSQL if available, fallback to SQLite for zero-config startup
db_url = settings.DATABASE_URL
if settings.USE_SQLITE_FALLBACK and "sqlite" not in db_url:
    # Try PostgreSQL first; if it fails on connect, fallback logic is handled in lifespan
    pass

engine = None
AsyncSessionLocal = None


def init_db(url: str = None):
    global engine, AsyncSessionLocal
    target_url = url or (settings.SQLITE_URL if settings.USE_SQLITE_FALLBACK else settings.DATABASE_URL)
    engine = create_async_engine(
        target_url,
        echo=settings.DEBUG,
        future=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine


async def get_db():
    if AsyncSessionLocal is None:
        init_db()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

