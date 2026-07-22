from contextlib import asynccontextmanager
from venv import logger

from fastapi import Depends, FastAPI

from src.middlewares import RateLimitMiddleware
from src.routers import documents, health, queries

from .auth import verify_api_key
from .database import init_db


# https://fastapi.tiangolo.com/advanced/events/#lifespan
# Its a generator that helps do stuff at the startup of the system and at the shutdown of the system (after yield)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Without try/except the app crashes if the database is unreachable.
    try:
        await init_db()
    except Exception:
        logger.warning("Database unavailable at startup — deferring")
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(queries.router)

# Middlewares
app.add_middleware(RateLimitMiddleware)


@app.get("/")
async def root(key: str = Depends(verify_api_key)):
    return {"message": "Hello World"}
