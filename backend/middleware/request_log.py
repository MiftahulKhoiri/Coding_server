"""Log setiap request (method, path, status, durasi) dan header keamanan dasar."""
import time

from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.logging import get_logger

log = get_logger("http")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        ms = (time.monotonic() - start) * 1000
        if not request.url.path.startswith("/preview/"):
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
        ip = request.client.host if request.client else "-"
        path = request.url.path
        if path.startswith("/preview/"):
            path = "/preview/***/" + "/".join(path.split("/")[3:])
        log.info("%s %s %s %d %.1fms", ip, request.method, path, response.status_code, ms)
        return response
