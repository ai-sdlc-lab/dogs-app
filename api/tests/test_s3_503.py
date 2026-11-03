"""S3 failure answers 503 with a fixed body (change 0003, PLAN-0003 T-04, T-05, T-06, T-12)."""

import logging
import re

import pytest
from botocore.exceptions import BotoCoreError, ReadTimeoutError
from s3_stub import (
    URL,
    api,
    build_client,
    connect_timeout,
    connection_error,
    error_response,
    fake_time,
    ok,
    raises,
    set_env,
)

JSON = "application/json; charset=utf-8"
SECURITY = {
    "x-content-type-options": "nosniff",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "referrer-policy": "no-referrer",
}
KEYS = ["dogs/beagle/1.jpg", "dogs/pug/1.jpg", "dogs/README", "dogs/Bad_Breed/x.jpg"]


class Leaky(BotoCoreError):
    fmt = "{detail}"


@pytest.fixture
def clock(monkeypatch):
    set_env(monkeypatch)
    return fake_time(monkeypatch)


def failing(monkeypatch, clock, step=None, request_id=None):
    client, stub = build_client(clock, [step or raises(connect_timeout)])
    return api(monkeypatch, client, request_id), stub


def assert_fixed_body(r):
    assert r.status_code == 503
    body = r.json()
    assert set(body) == {"error", "request_id"}
    assert body["error"] == "dependency_unavailable"
    assert isinstance(body["request_id"], str) and body["request_id"]


# --- failure responses --------------------------------------------------------------------------


def test_dogs_s3_failure_returns_503(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock)
    assert_fixed_body(web.get("/api/dogs"))


def test_dogs_by_breed_s3_failure_returns_503(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock)
    assert_fixed_body(web.get("/api/dogs/pug"))  # not 404


def test_s3_failure_body_has_no_detail(monkeypatch, clock):
    leak = Leaky(detail="MARKER-7f3 /var/task/app/secret.py test-bucket")
    web, _ = failing(monkeypatch, clock, raises(leak))
    r = web.get("/api/dogs")
    assert_fixed_body(r)
    seen = r.text + " ".join(f"{k} {v}" for k, v in r.headers.items())
    for text in ("MARKER-7f3", "/var/task", "secret.py", "test-bucket", "botocore", "boto"):
        assert text not in seen


def test_s3_failure_midway_returns_503(monkeypatch, clock):
    client, _ = build_client(clock, [ok(KEYS[:2], "t1"), raises(connect_timeout)])
    r = api(monkeypatch, client).get("/api/dogs")
    assert_fixed_body(r)
    assert "url" not in r.text  # no partial list


def test_s3_error_response_returns_503(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock, error_response("AccessDenied", 403))
    assert_fixed_body(web.get("/api/dogs"))


@pytest.mark.parametrize(
    "exc",
    [connect_timeout, lambda: ReadTimeoutError(endpoint_url=URL), connection_error],
    ids=["connect", "read", "conn"],
)
def test_s3_connection_error_returns_503(monkeypatch, clock, exc):
    web, _ = failing(monkeypatch, clock, raises(exc))
    assert_fixed_body(web.get("/api/dogs"))


def test_s3_other_client_error_returns_503(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock, raises(Leaky(detail="boom")))
    assert_fixed_body(web.get("/api/dogs"))


def test_503_has_no_retry_after(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock)
    assert "retry-after" not in web.get("/api/dogs").headers


def test_503_has_security_headers(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock)
    r = web.get("/api/dogs")
    assert r.status_code == 503
    assert r.headers.get_list("content-type") == [JSON]
    for name, value in SECURITY.items():
        assert r.headers.get_list(name) == [value], name


# --- request_id ---------------------------------------------------------------------------------


def test_503_request_id_from_lambda_context(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock, request_id="8f2c1c3e-aaaa-bbbb-cccc-0123456789ab")
    assert web.get("/api/dogs").json()["request_id"] == "8f2c1c3e-aaaa-bbbb-cccc-0123456789ab"


def test_503_request_id_generated_when_missing(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock)
    ids = [web.get("/api/dogs").json()["request_id"] for _ in range(2)]
    assert all(re.fullmatch(r"[0-9a-f]{32}", i) for i in ids)
    assert ids[0] != ids[1]


def test_503_ignores_request_id_header(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock)
    hostile = {"X-Request-Id": "caller-chosen-1", "request_id": "caller-chosen-2"}
    r = web.get("/api/dogs?request_id=caller-chosen-3", headers=hostile)
    assert_fixed_body(r)
    assert "caller-chosen" not in r.text
    assert "caller-chosen" not in " ".join(r.headers.values())


# --- unchanged behaviour ------------------------------------------------------------------------


def test_dogs_by_breed_rejects_without_s3_call(monkeypatch, clock):
    web, stub = failing(monkeypatch, clock)
    assert web.get("/api/dogs/Bad_Breed").status_code == 422
    assert stub.calls == []


def test_empty_breed_404_passthrough(monkeypatch, clock):
    client, _ = build_client(clock, [ok(KEYS)])
    assert api(monkeypatch, client).get("/api/dogs/husky").status_code == 404


def test_missing_bucket_setting_unchanged(monkeypatch, clock):
    monkeypatch.delenv("DOGS_BUCKET")
    web, stub = failing(monkeypatch, clock)
    r = web.get("/api/dogs")
    assert (r.status_code, r.text) == (500, "Internal Server Error")
    assert stub.calls == []


def test_non_s3_error_not_503(monkeypatch, clock):
    web, _ = failing(monkeypatch, clock, raises(ValueError("programming error")))
    assert web.get("/api/dogs").status_code == 500


def test_healthy_s3_responses_unchanged(monkeypatch, clock):
    client, _ = build_client(clock, [ok(KEYS)])
    web = api(monkeypatch, client)
    dogs = web.get("/api/dogs")
    assert dogs.status_code == 200
    assert [d["breed"] for d in dogs.json()] == ["beagle", "pug"]
    assert all(
        d["url"].startswith("https://test-bucket.s3.eu-north-1.amazonaws.com/dogs/") for d in dogs.json()
    )
    pug = web.get("/api/dogs/pug")
    assert pug.status_code == 200 and [d["breed"] for d in pug.json()] == ["pug"]
    assert web.get("/api/dogs/husky").status_code == 404
    assert web.get("/api/health").json() == {"status": "ok"}


def test_health_ok_when_s3_failing(monkeypatch, clock):
    web, stub = failing(monkeypatch, clock)
    r = web.get("/api/health")
    assert (r.status_code, r.json()) == (200, {"status": "ok"})
    assert stub.calls == []


# --- accepted logging risk (SPEC-0003 section 7; replace when the logging follow-up lands) -------


def test_s3_failure_adds_no_log_record(monkeypatch, clock, caplog):
    web, _ = failing(monkeypatch, clock)
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    assert web.get("/api/dogs").status_code == 503
    mine = [r for r in caplog.records if r.name == "root" or r.name.startswith("app")]
    assert mine == []
