import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.ratelimiter import RateLimiterStore

# Configure rate limits: 10 requests burst, 2 tokens added every 1 second.
limiter = RateLimiterStore(max_tokens=10, refill_rate=2, interval=1.0)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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
