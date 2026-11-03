"""Test support for change 0003 (PLAN-0003 T-01): fake clock, stub transport, client builder.

The client is the real one from the production `main.s3()` (production Config, DeadlineSession and
install()). Only the bottom of the session, `DeadlineSession._raw_send`, is replaced by the stub.
"""

import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from botocore.awsrequest import AWSResponse
from botocore.exceptions import ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError
from fastapi.testclient import TestClient

from app import main, s3_limits

REAL_S3 = main.s3  # the cached factory, before any test replaces it
BUCKET = "test-bucket"
URL = "https://s3.eu-north-1.amazonaws.com"
NO_WEB = Path("/nonexistent-web-dir")


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def set_env(monkeypatch):
    """Fake keys, region and bucket: the tests run offline."""
    for k, v in {
        "AWS_REGION": "eu-north-1",
        "AWS_ACCESS_KEY_ID": "x",
        "AWS_SECRET_ACCESS_KEY": "y",
        "DOGS_BUCKET": BUCKET,
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(k, v)


def fake_time(monkeypatch):
    """Fake time: the deadline code reads it and botocore's backoff sleep advances it."""
    c = FakeClock()
    monkeypatch.setattr(s3_limits, "now", c.now)
    monkeypatch.setattr(time, "sleep", c.sleep)
    return c


class StubRaw:
    """Raw body: `chunk` bytes per read, each read costs `cost` fake seconds."""

    def __init__(self, clock, data, chunk=None, cost=0):
        self.clock, self.data, self.cost = clock, data, cost
        self.chunk = chunk or len(data) or 1
        self.closed = False
        self.released = False

    def read1(self, _amt=None):
        if self.closed or not self.data:
            return b""
        if self.clock:
            self.clock.t += self.cost
        out, self.data = self.data[: self.chunk], self.data[self.chunk :]
        return out

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


def listing(keys, next_token=None):
    contents = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    more = f"<NextContinuationToken>{next_token}</NextContinuationToken>" if next_token else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Name>{BUCKET}</Name><Prefix></Prefix><KeyCount>{len(keys)}</KeyCount><MaxKeys>1000</MaxKeys>"
        f"<IsTruncated>{'true' if next_token else 'false'}</IsTruncated>{more}{contents}</ListBucketResult>"
    ).encode()


class Stub:
    """Scripted transport: attempt n runs steps[n] (the last step repeats). Records every attempt."""

    def __init__(self, session, clock, steps):
        self.session, self.clock = session, clock
        self.calls, self.raws, self.start = [], [], clock.t if clock else 0.0
        self.script(steps)

    def script(self, steps):
        self.steps, self.n = steps, 0

    def __call__(self, request):
        timeout = self.session._timeout.clone()  # the production per-attempt timeouts
        self.calls.append(
            SimpleNamespace(
                t=self.clock.t if self.clock else 0.0,
                connect=timeout.connect_timeout,
                read=timeout.read_timeout,
            )
        )
        step = self.steps[min(self.n, len(self.steps) - 1)]
        self.n += 1
        return step(self, timeout, request)

    def response(self, body, status=200, chunk=None, cost=0):
        raw = StubRaw(self.clock, body, chunk, cost)
        self.raws.append(raw)
        return AWSResponse(URL, status, {"Content-Type": "application/xml"}, raw)


# --- steps: (stub, timeout, request) -> AWSResponse, or raise ---------------------------------


def ok(keys=(), next_token=None):
    def step(stub, _timeout, request):
        prefix = parse_qs(urlsplit(request.url).query).get("prefix", [""])[0]
        return stub.response(listing([k for k in keys if k.startswith(prefix)], next_token))

    return step


def raises(exc, at=None):
    """Fail with `exc` (an instance or a zero-argument factory); `at`: fake seconds from the start."""

    def step(stub, _timeout, _request):
        if at is not None:
            stub.clock.t = stub.start + at
        raise exc() if callable(exc) else exc

    return step


def hang():
    """Spends the whole read timeout it was given, then times out."""

    def step(stub, timeout, _request):
        stub.clock.t += timeout.read_timeout
        raise ReadTimeoutError(endpoint_url=URL)

    return step


def drip(cost=4):
    """200 response that sends one byte per read, each read taking `cost` fake seconds."""

    def step(stub, _timeout, _request):
        return stub.response(b"<" * 1000, chunk=1, cost=cost)

    return step


def error_response(code="AccessDenied", status=403):
    def step(stub, _timeout, _request):
        body = f"<Error><Code>{code}</Code><Message>denied</Message></Error>".encode()
        return stub.response(body, status=status)

    return step


def connect_timeout():
    return ConnectTimeoutError(endpoint_url=URL)


def connection_error():
    return EndpointConnectionError(endpoint_url=URL)


# --- builders --------------------------------------------------------------------------------


def build_client(clock, steps):
    client = REAL_S3.__wrapped__()
    session = client._endpoint.http_session
    stub = Stub(session, clock, steps)
    session._raw_send = stub
    return client, stub


def with_context(app, request_id):
    """Sets scope["aws.context"] as Mangum does (None: leave it out)."""

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and request_id is not None:
            scope = {**scope, "aws.context": SimpleNamespace(aws_request_id=request_id)}
        await app(scope, receive, send)

    return wrapped


def api(monkeypatch, client, request_id=None):
    monkeypatch.setattr(main, "s3", lambda: client)
    return TestClient(with_context(main.build(NO_WEB), request_id), raise_server_exceptions=False)
