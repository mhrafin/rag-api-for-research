from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from config import get_settings

settings = get_settings()

# We need async so that FastAPI can handle many requests at the same time.
# Synchronous drivers waits for every database round trip. We don't want that with FastAPI.
async_engine = create_async_engine(settings.database_url)

AsyncSession = async_sessionmaker(bind=async_engine)


def get_db():
    """A generator that creates a fresh session. Finally the session is closed after a request is handled.

    Yields:
        AsyncSession: An async session
    """
    db = AsyncSession()
    try:
        yield db
    finally:
        db.aclose()
