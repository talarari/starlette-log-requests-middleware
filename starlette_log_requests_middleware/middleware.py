from typing import Tuple, List, Optional
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import json
from logging import getLogger, Logger
from starlette.routing import Match
from dataclasses import dataclass


@dataclass
class IgnoredRoute:
    path: str
    method: Optional[str] = None


class LogRequestsMiddleware:
    def __init__(
        self, app: ASGIApp, logger: Logger = getLogger(__name__), ignored_routes: List[IgnoredRoute] = []
    ) -> None:
        self.app = app
        self.logger = logger
        self.ignore_routes = ignored_routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            responder = _RequestLoggingResponder(self.app, logger=self.logger, ignored_routes=self.ignore_routes)
            await responder(scope, receive, send)
            return

        await self.app(scope, receive, send)


class _RequestLoggingResponder:
    def __init__(self, app: ASGIApp, logger: Logger, ignored_routes: List[IgnoredRoute]) -> None:
        self.app = app
        self.receive: Receive = unattached_receive
        self.send: Send = unattached_send
        self._path: str = ""
        self._method: str = ""
        self._request_body: bytearray = bytearray()
        self._response_body: bytearray = bytearray()
        self._response_status_code = None
        self._logger = logger
        self._ignored_routes = ignored_routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.receive = receive
        self.send = send

        request = Request(scope)

        if self._should_ignore_request(request):
            await self.app(scope, self.receive, self.send)
            return

        self._method = request.method
        self._path = request.url.path
        headers = Headers(scope=scope)
        self.should_log_request_body = "application/json" in headers.get("content-type", "")

        await self.app(scope, self.receive_with_logging, self.send_with_logging)

        self._safe_log_request_response()

    async def receive_with_logging(self) -> Message:
        message = await self.receive()

        if message["type"] != "http.request":
            return message

        if not self.should_log_request_body:
            return message

        body: bytes = message.get("body", b"")
        self._request_body.extend(body)

        return message

    async def send_with_logging(self, message: Message) -> None:

        if message["type"] == "http.response.start":
            self._response_status_code = message.get("status")
            headers = Headers(raw=message["headers"])
            self.should_log_response_body = "application/json" in headers.get("content-type", "")

            await self.send(message)

        elif message["type"] == "http.response.body":
            if not self.should_log_response_body:
                await self.send(message)
                return

            body: bytes = message.get("body", b"")
            self._response_body.extend(body)

            await self.send(message)

    def _safe_log_request_response(self):
        try:
            request_body = self._request_body and json.loads(self._request_body)
            response_body = self._response_body and json.loads(self._response_body)
            self._logger.debug(
                f"request: {self._method} {self._path} {request_body or ''} -> {self._response_status_code} {response_body or ''}"
            )
        except Exception:
            pass

    def _should_ignore_request(self, request: Request):
        path_tempalte, is_handled_path = self.get_path_template(request)
        if not is_handled_path:
            return False

        for ignored_route in self._ignored_routes:
            if path_tempalte == ignored_route.path and (
                ignored_route.method is None or ignored_route.method.lower() == request.method.lower()
            ):
                return True
        return False

    @staticmethod
    def get_path_template(request: Request) -> Tuple[str, bool]:
        for route in request.app.routes:
            match, child_scope = route.matches(request.scope)
            if match == Match.FULL:
                return route.path, True

        return request.url.path, False


async def unattached_receive() -> Message:
    raise RuntimeError("receive awaitable not set")  # pragma: no cover


async def unattached_send(message: Message) -> None:
    raise RuntimeError("send awaitable not set")  # pragma: no cover
