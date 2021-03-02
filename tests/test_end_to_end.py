
import pytest
from testfixtures import LogCapture
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from  starlette_log_requests_middleware import LogRequestsMiddleware

from logging import getLogger

logger = getLogger("test_log_request_middleware")
class TestCaseLogRequestsMiddleware:
    @pytest.fixture(scope="class")
    def app(self):
        app_ = Starlette()
        app_.add_middleware(LogRequestsMiddleware,logger=logger)

        @app_.route("/json")
        def foo(request):
            return JSONResponse("some_response")


        return app_

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_request_logged(self, client):
        # Do a request

         with LogCapture() as l:
            client.get("/json")
            l.check_present(
                ('test_log_request_middleware', 'DEBUG', 'request: GET /json  -> 200 some_response')
            )

        # Get metrics
      

   