"""Pure-ASGI request middleware: request id, access log, JSON 500 (decision D-06)."""

from __future__ import annotations

import logging
import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_setup import accept_or_make_request_id, request_id_var

log = logging.getLogger("app.request")
HEADER = "X-Request-ID"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = accept_or_make_request_id(incoming)
        token = request_id_var.set(request_id)
        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            log.exception("unhandled error", extra={"path": scope["path"]})
            await self._internal_error(send, request_id)
            status = 500
        finally:
            log.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)

    @staticmethod
    async def _internal_error(send: Send, request_id: str) -> None:
        body = b'{"error":{"code":"internal_error","message":"Internal server error","details":[]}}'
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (HEADER.lower().encode(), request_id.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
