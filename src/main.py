import time
from contextlib import asynccontextmanager
from venv import logger

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from src.ratelimiter import RateLimiterStore
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


# Configure rate limits: 10 requests burst, 2 tokens added every 1 second.
limiter = RateLimiterStore(max_tokens=10, refill_rate=2, interval=1.0)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware that enforces per-IP rate limiting on every request.
    Adds standard rate limit headers to every response.
    """
    # Identify the client by IP address.
    client_ip = request.client.host
    bucket = limiter.get_bucket(client_ip)

    # Check if the client has tokens available.
    if not bucket.allow_request():
        retry_after = bucket.get_reset_time() - time.time()
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Try again later."},
            headers={
                "Retry-After": str(max(1, int(retry_after))),
                "X-RateLimit-Limit": str(bucket.max_tokens),
                "X-RateLimit-Remaining": str(bucket.get_remaining()),
                "X-RateLimit-Reset": str(int(bucket.get_reset_time())),
            },
        )

    # Request is allowed. Process it and add rate limit headers to the response.
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(bucket.max_tokens)
    response.headers["X-RateLimit-Remaining"] = str(bucket.get_remaining())
    response.headers["X-RateLimit-Reset"] = str(int(bucket.get_reset_time()))
    return response


@app.get("/")
async def root(key: str = Depends(verify_api_key)):
    return {"message": "Hello World"}
