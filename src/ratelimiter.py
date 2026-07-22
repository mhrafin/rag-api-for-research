import threading
import time


class TokenBucket:
    """
    Token Bucket rate limiter.

    Each bucket starts full at `max_tokens` and refills `refill_rate`
    tokens every `interval` seconds, up to the maximum capacity.
    """

    def __init__(self, max_tokens: int, refill_rate: int, interval: float):
        """
        Initialize a new Token Bucket.

        :param max_tokens: Maximum number of tokens the bucket can hold (burst capacity).
        :param refill_rate: Number of tokens added per refill interval.
        :param interval: Time in seconds between refills.
        """

        assert max_tokens > 0
        assert refill_rate > 0
        assert interval > 0

        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.interval = interval

        self.tokens = max_tokens
        self.refilled_at = time.time()
        self.lock = threading.Lock()

    def _refill(self):
        """Add tokens based on elapsed time since the last refill."""

        now = time.time()
        elapsed = now - self.refilled_at

        if elapsed >= self.interval:
            num_refills = int(
                elapsed // self.interval
            )  # Counts how many times to refill the bucket based on elapsed time from the last refill
            self.tokens = min(
                self.max_tokens, self.tokens + num_refills * self.refill_rate
            )  # This makes sure that the available tokens never exceed max_tokens

            # Advance the timestamp by the number of full intervals consumed,
            # not to `now`, so partial intervals aren't lost.
            self.refilled_at += num_refills * self.interval

    def allow_request(self, tokens: int = 1) -> bool:
        """
        Attempt to consume `tokens` from the bucket.

        Returns True if the request is allowed, False if the bucket
        does not have enough tokens.
        """

        with self.lock:
            self._refill()  # Instead of using up all the cpu to constantly check to refill, we only check and refill when a token is involved.

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def get_remaining(self) -> int:
        """Return the current number of available tokens."""
        with self.lock:
            self._refill()
            return self.tokens

    def get_reset_time(self) -> float:
        """Return the Unix timestamp when the next refill occurs."""
        with self.lock:
            return self.refilled_at + self.interval


class RateLimiterStore:
    """
    Manages per-user Token Buckets.

    Each unique client key (e.g., IP address) gets its own bucket
    with identical parameters.
    """

    def __init__(self, max_tokens: int, refill_rate: int, interval: float):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.interval = interval
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def get_bucket(self, key: str) -> TokenBucket:
        """
        Return the TokenBucket for a given client key.
        Creates a new bucket if one does not exist yet.
        """
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(
                    max_tokens=self.max_tokens,
                    refill_rate=self.refill_rate,
                    interval=self.interval,
                )
            return self._buckets[key]
