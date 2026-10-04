import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from middleware import RequestIdMiddleware, SecurityHeadersMiddleware


def _make_app() -> Starlette:
    def ok(request):
        return PlainTextResponse("ok")

    def boom(request):
        raise ValueError("boom")

    app = Starlette(routes=[Route("/ok", ok), Route("/boom", boom)])
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app


def test_request_id_is_generated_and_security_headers_set():
    response = TestClient(_make_app()).get("/ok")
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_incoming_request_id_is_preserved():
    response = TestClient(_make_app()).get("/ok", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_original_exception_is_not_masked_by_logging():
    with pytest.raises(ValueError, match="boom"):
        TestClient(_make_app()).get("/boom")
