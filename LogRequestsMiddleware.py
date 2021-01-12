from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import json
from logging import Logger, getLogger


class LogRequestsMiddleware:
    def __init__(self, app: ASGIApp, logger: Logger = getLogger(__name__)) -> None:
        self.app = app
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            responder = _RequestLoggingResponder(self.app, logger=self.logger)
            await responder(scope, receive, send)
            return

        await self.app(scope, receive, send)


class _RequestLoggingResponder:
    def __init__(self, app: ASGIApp, logger: Logger) -> None:
        self.app = app
        self.receive: Receive = unattached_receive
        self.send: Send = unattached_send
        self.path: str = None
        self.method: str = None
        self.request_body = None
        self.response_body = None
        self.response_status_code = None
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.receive = receive
        self.send = send

        request = Request(scope)
        self.method = request.method
        self.path = request.url.path

        await self.app(scope, self.receive_with_logging, self.send_with_logging)
        self.logger.info(
            f"{self.method} {self.path} {self.response_body} -> {self.response_status_code} {self.response_body}"
        )

    async def receive_with_logging(self) -> Message:
        message = await self.receive()

        assert message["type"] == "http.request"

        body = message["body"]
        more_body = message.get("more_body", False)

        if more_body:
            # Some implementations (e.g. HTTPX) may send one more empty-body message.
            # Make sure they don't send one that contains a body, or it means
            # that clients attempt to stream the request body.
            message = await self.receive()
            if message["body"] != b"":  # pragma: no cover
                raise NotImplementedError("Streaming the request body isn't supported yet")

        self.request_body = body

        return message

    async def send_with_logging(self, message: Message) -> None:

        if message["type"] == "http.response.start":
            self.response_status_code = message.get("status")
            await self.send(message)

        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            more_body = message.get("more_body", False)
            if more_body:  # pragma: no cover
                raise NotImplementedError("Streaming the response body isn't supported yet")

            body = json.loads(body)
            self.response_body = body

            await self.send(message)


async def unattached_receive() -> Message:
    raise RuntimeError("receive awaitable not set")  # pragma: no cover


async def unattached_send(message: Message) -> None:
    raise RuntimeError("send awaitable not set")  # pragma: no cover