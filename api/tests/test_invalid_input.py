"""Invalid input returns 422 and is logged as input.rejected (change 0004, PLAN-0004 A-01 to A-04)."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import EndpointConnectionError
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app import main, rejection

NO_WEB = Path("/nonexistent-web-dir")
HEX32 = re.compile(r"[0-9a-f]{32}")
TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")
EVENT_KEYS = {
    "ts",
    "level",
    "event",
    "outcome",
    "request_id",
    "actor",
    "source_ip",
    "http",
    "reason",
    "service",
    "version",
}
BAD = "/api/dogs/Bad_Breed"


class FakeS3:
    calls = 0

    def get_paginator(self, _):
        FakeS3.calls += 1
        return self

    def paginate(self, Bucket, Prefix):
        return [{"Contents": [{"Key": k} for k in ("dogs/pug/1.jpg",) if k.startswith(Prefix)]}]

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://signed.example/{Params['Key']}"


class BrokenS3:
    def get_paginator(self, _):
        raise EndpointConnectionError(endpoint_url="https://s3.example")


class BoomContext:
    @property
    def aws_request_id(self):
        raise RuntimeError("attribute access fails")


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("DOGS_BUCKET", "test-bucket")
    monkeypatch.setattr(main, "s3", FakeS3)
    monkeypatch.setattr(rejection, "BUILD_INFO", tmp_path / "missing" / "build_info.json")
    FakeS3.calls = 0


def with_scope(app, **extra):
    """Adds scope keys as Mangum does (keys with dots are passed through **{...})."""

    async def wrapped(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, **extra}
        await app(scope, receive, send)

    return wrapped


def client(**extra):
    return TestClient(with_scope(main.build(NO_WEB), **extra), raise_server_exceptions=False)


def typed_client(**extra):
    """Test-only app with a typed parameter, to trigger the framework's own validation."""
    api = FastAPI()

    @api.get("/t/{n}")
    def t(n: int):
        return {"n": n}

    api.add_exception_handler(RequestValidationError, main.invalid_request)
    return TestClient(with_scope(main.security_headers(api), **extra), raise_server_exceptions=False)


def context(rid):
    return {"aws.context": SimpleNamespace(aws_request_id=rid)}


def event_of(capsys):
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


# --- request ID (A-01) -------------------------------------------------------------------------


def test_rejected_request_id_from_lambda_context():
    r = client(**context("lambda-req-1")).get(BAD)
    assert r.status_code == 422 and r.json()["request_id"] == "lambda-req-1"


def test_rejected_request_id_generated_when_missing():
    web = client()
    ids = [web.get(BAD).json()["request_id"] for _ in range(2)]
    assert all(HEX32.fullmatch(i) for i in ids)
    assert ids[0] != ids[1]


def test_generated_request_id_is_128_bit_hex():
    request = SimpleNamespace(scope={})
    ids = {rejection.request_id(request) for _ in range(20)}
    assert len(ids) == 20
    assert all(HEX32.fullmatch(i) for i in ids)


def test_rejected_request_id_ignores_request_headers():
    hostile = {"X-Request-Id": "caller-1", "request_id": "caller-2", "X-Amzn-Trace-Id": "caller-3"}
    r = client().get(BAD + "?request_id=caller-4", headers=hostile)
    assert HEX32.fullmatch(r.json()["request_id"])
    assert "caller-" not in r.text


def test_rejected_log_request_id_matches_body(capsys):
    for extra in (context("lambda-req-2"), {}):
        r = client(**extra).get(BAD)
        assert event_of(capsys)["request_id"] == r.json()["request_id"]


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"aws.context": object()},
        {"aws.context": SimpleNamespace(aws_request_id=None)},
        {"aws.context": SimpleNamespace(aws_request_id=12345)},
        {"aws.context": SimpleNamespace(aws_request_id=object())},
        {"aws.context": SimpleNamespace(aws_request_id="")},
        {"aws.context": BoomContext()},
    ],
    ids=["absent", "no-attr", "none", "int", "object", "empty", "raises"],
)
def test_request_id_survives_malformed_aws_context(capsys, extra):
    r = client(**extra).get(BAD)
    assert r.status_code == 422
    assert set(r.json()) == {"error", "request_id"}
    assert HEX32.fullmatch(r.json()["request_id"])
    assert event_of(capsys)["request_id"] == r.json()["request_id"]
    assert "Traceback" not in r.text


# --- log event (A-02) --------------------------------------------------------------------------


def test_rejected_logs_input_rejected_event(capsys):
    event = {"requestContext": {"http": {"sourceIp": "203.0.113.9"}}}
    r = client(**context("rid-9"), **{"aws.event": event}).get(BAD + "?q=1")
    e = event_of(capsys)
    assert set(e) == EVENT_KEYS
    assert TS.fullmatch(e.pop("ts"))
    assert e == {
        "level": "WARN",
        "event": "input.rejected",
        "outcome": "failure",
        "request_id": "rid-9",
        "actor": "anonymous",
        "source_ip": "203.0.113.9",
        "http": {"method": "GET", "path": BAD, "status": 422},
        "reason": "invalid_breed",
        "service": "dogs-app",
        "version": "unknown",
    }
    assert r.json()["request_id"] == "rid-9"


def test_rejected_log_is_single_line_json_for_hostile_path(capsys):
    r = typed_client().get("/t/x%0A%22%09%C3%BC%5C%0D%7B")
    assert r.status_code == 422
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.endswith("\n")
    assert json.loads(out)["http"]["path"] == '/t/x\n"\tü\\\r{'


def test_rejected_log_path_truncated_to_200(capsys):
    typed_client().get("/t/" + "a" * 300)
    assert event_of(capsys)["http"]["path"] == ("/t/" + "a" * 300)[:200]


def test_rejected_log_path_has_no_query_string(capsys):
    typed_client().get("/t/x?secret=QUERYVALUE")
    out = capsys.readouterr().out
    assert "QUERYVALUE" not in out and "secret" not in out
    assert json.loads(out)["http"]["path"] == "/t/x"


def test_rejected_log_source_ip_from_context_not_xff(capsys):
    event = {"requestContext": {"http": {"sourceIp": "203.0.113.9"}}}
    client(**{"aws.event": event}).get(BAD, headers={"X-Forwarded-For": "6.6.6.6"})
    out = capsys.readouterr().out
    assert json.loads(out)["source_ip"] == "203.0.113.9"
    assert "6.6.6.6" not in out
    client().get(BAD, headers={"X-Forwarded-For": "6.6.6.6"})
    assert event_of(capsys)["source_ip"] == "unknown"


def boom(*_a, **_k):
    raise RuntimeError("log write failed MARKER")


def patch_print_and_dumps(monkeypatch):
    monkeypatch.setattr(rejection, "print", boom, raising=False)
    monkeypatch.setattr(rejection, "json", SimpleNamespace(dumps=boom, loads=json.loads))


def patch_event_building(monkeypatch):
    monkeypatch.setattr(rejection, "version", boom)


@pytest.mark.parametrize("patch", [patch_print_and_dumps, patch_event_building])
def test_rejected_still_422_when_log_write_fails(monkeypatch, capsys, patch):
    web = client(**context("rid-f"))
    base = web.get(BAD)
    capsys.readouterr()
    patch(monkeypatch)
    r = web.get(BAD)
    assert r.status_code == 422
    assert r.json() == base.json() == {"error": "invalid_input", "request_id": "rid-f"}
    assert dict(r.headers) == dict(base.headers)
    assert capsys.readouterr().out == ""
    assert "MARKER" not in r.text and "Traceback" not in r.text


def test_framework_validation_error_uses_invalid_input_body(capsys):
    r = typed_client(**context("rid-t")).get("/t/abc")
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_input", "request_id": "rid-t"}
    assert "detail" not in r.text
    e = event_of(capsys)
    assert e["reason"] == "invalid_request" and e["http"]["path"] == "/t/abc"


def test_valid_requests_write_no_input_rejected(monkeypatch, capsys):
    web = client()
    assert web.get("/api/dogs/pug").status_code == 200
    assert web.get("/api/dogs/husky").status_code == 404
    assert web.get("/nope").status_code == 404
    monkeypatch.setattr(main, "s3", BrokenS3)
    assert web.get("/api/dogs").status_code == 503
    assert capsys.readouterr().out == ""


# --- breed rule (A-03) -------------------------------------------------------------------------

MALFORMED = ["Bad_Breed", "%2E%2E", "a" * 41, "h%C3%BCnd", "pug%0A", "pu%00g", "%FF", "pug%22"]


@pytest.mark.parametrize("breed", MALFORMED)
def test_dogs_by_breed_rejects_malformed_breed(breed):
    r = client().get(f"/api/dogs/{breed}")
    assert r.status_code == 422
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    body = r.json()
    assert set(body) == {"error", "request_id"}
    assert body["error"] == "invalid_input" and body["request_id"]


@pytest.mark.parametrize("breed", ["a", "a" * 40, "a-1"])
def test_dogs_by_breed_accepts_boundary_breeds(breed):
    assert client().get(f"/api/dogs/{breed}").status_code in (200, 404)


@pytest.mark.parametrize("breed", MALFORMED)
def test_rejected_body_has_no_request_data(breed):
    r = client().get(f"/api/dogs/{breed}?field=QVALUE")
    assert r.text == json.dumps(r.json(), separators=(",", ":"))
    for text in (breed, "QVALUE", "detail", "breed", "field", "Traceback", "loc"):
        assert text not in r.text
    assert "QVALUE" not in str(r.headers)


def test_encoded_slash_and_empty_breed_stay_404(capsys):
    web = client()
    assert web.get("/api/dogs/a%2Fb").status_code == 404
    # empty breed: no breed value reaches validation (the router may redirect /api/dogs/ to /api/dogs)
    assert web.get("/api/dogs/", follow_redirects=False).status_code in (307, 404)
    assert capsys.readouterr().out == ""
    assert FakeS3.calls == 0


# --- build info (A-04) -------------------------------------------------------------------------


def test_rejected_log_version_from_build_info(monkeypatch, tmp_path, capsys):
    info = tmp_path / "build_info.json"
    sha = "0123456789abcdef0123456789abcdef01234567"
    info.write_text(json.dumps({"sha": sha}))
    monkeypatch.setattr(rejection, "BUILD_INFO", info)
    client().get(BAD)
    assert event_of(capsys)["version"] == sha
    info.unlink()
    client().get(BAD)
    assert event_of(capsys)["version"] == "unknown"
