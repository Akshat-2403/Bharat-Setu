import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Process-local limiter for public credential endpoints."""

    WINDOW_SECONDS = 60
    MAX_ATTEMPTS = 10
    PATHS = {"/api/auth/login", "/api/auth/register"}

    def __init__(self, app):
        super().__init__(app)
        self._attempts = defaultdict(deque)
        self._lock = threading.Lock()

    async def dispatch(self, request, call_next):
        if request.method == "POST" and request.url.path in self.PATHS:
            client_ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            key = (client_ip, request.url.path)
            with self._lock:
                attempts = self._attempts[key]
                while attempts and now - attempts[0] >= self.WINDOW_SECONDS:
                    attempts.popleft()
                if len(self._attempts) > 2048:
                    stale = [bucket for bucket, values in self._attempts.items()
                             if not values or now - values[-1] >= self.WINDOW_SECONDS]
                    for bucket in stale:
                        self._attempts.pop(bucket, None)
                if len(attempts) >= self.MAX_ATTEMPTS:
                    retry_after = max(1, int(self.WINDOW_SECONDS - (now - attempts[0])))
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many authentication attempts. Try again later."},
                        headers={
                            "Retry-After": str(retry_after),
                            "X-Content-Type-Options": "nosniff",
                            "X-Frame-Options": "DENY",
                            "Referrer-Policy": "strict-origin-when-cross-origin",
                        },
                    )

        response = await call_next(request)
        if request.method == "POST" and request.url.path in self.PATHS and response.status_code in {400, 401, 422}:
            with self._lock:
                attempts = self._attempts[key]
                while attempts and now - attempts[0] >= self.WINDOW_SECONDS:
                    attempts.popleft()
                attempts.append(now)
                if len(self._attempts) > 2048:
                    stale = [bucket for bucket, values in self._attempts.items()
                             if not values or now - values[-1] >= self.WINDOW_SECONDS]
                    for bucket in stale:
                        self._attempts.pop(bucket, None)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response
