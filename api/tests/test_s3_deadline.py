"""The 8 s S3 deadline on the real client over a stubbed transport (change 0003, PLAN-0003 T-03)."""

import threading
import time

import pytest
from botocore.exceptions import ReadTimeoutError
from s3_stub import (
    BUCKET,
    URL,
    api,
    build_client,
    connect_timeout,
    drip,
    error_response,
    fake_time,
    hang,
    ok,
    raises,
    set_env,
)

from app import s3_limits

KEYS = ["dogs/beagle/1.jpg", "dogs/pug/1.jpg"]


@pytest.fixture
def clock(monkeypatch):
    set_env(monkeypatch)
    return fake_time(monkeypatch)


def elapsed(stub, clock):
    return clock.t - stub.start


def test_s3_hang_returns_503_before_function_timeout(monkeypatch, clock):
    client, stub = build_client(clock, [hang()])
    r = api(monkeypatch, client).get("/api/dogs")
    assert r.status_code == 503
    assert elapsed(stub, clock) < 10  # in practice at most 8


def test_s3_slow_drip_returns_503_before_function_timeout(monkeypatch, clock):
    client, stub = build_client(clock, [drip(cost=4)])  # one byte per 4 s: the read timeout never trips
    r = api(monkeypatch, client).get("/api/dogs")
    assert r.status_code == 503
    assert elapsed(stub, clock) < 10
    assert len(stub.calls) == 1  # the abandoned attempt is not retried


@pytest.mark.parametrize("second_failure", [5.5, 7.0])
def test_attempt_started_near_deadline_is_bounded(monkeypatch, clock, second_failure):
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)  # backoff takes no fake time: failures set the clock
    client, stub = build_client(
        clock, [raises(connect_timeout, at=2.9), raises(connect_timeout, at=second_failure), hang()]
    )
    r = api(monkeypatch, client).get("/api/dogs")
    assert r.status_code == 503
    assert elapsed(stub, clock) <= 8
    for call in stub.calls:
        left = max(0, 8 - (call.t - stub.start))
        assert call.connect <= min(3, left) + 1e-9
        assert call.read <= min(5, left) + 1e-9
    if second_failure == 5.5:
        assert [c.read for c in stub.calls][-1] == pytest.approx(
            2.5
        )  # the third attempt got only the time left


def test_backoff_does_not_exceed_deadline(monkeypatch, clock):
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    client, stub = build_client(
        clock, [raises(connect_timeout, at=7.5)]
    )  # a backoff of up to 1 s could pass 8 s
    r = api(monkeypatch, client).get("/api/dogs")
    assert r.status_code == 503
    assert sleeps == []  # the sleep is never entered
    assert len(stub.calls) == 1


@pytest.mark.parametrize("code", ["SlowDown", "RequestTimeout", "Throttling"])
def test_backoff_does_not_exceed_deadline_on_4xx_throttle(monkeypatch, clock, code):
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    reply = error_response(code, status=400)

    def late_400(stub, timeout, request):
        stub.clock.t = stub.start + 7.5
        return reply(stub, timeout, request)

    client, stub = build_client(clock, [late_400])
    r = api(monkeypatch, client).get("/api/dogs")
    assert r.status_code == 503
    assert sleeps == []  # no backoff sleep that could run past 8 s
    assert len(stub.calls) == 1


def test_no_retry_after_deadline(monkeypatch, clock):
    client, stub = build_client(clock, [raises(connect_timeout, at=8.5)])
    r = api(monkeypatch, client).get("/api/dogs")
    assert r.status_code == 503
    assert len(stub.calls) == 1
    stub.script([ok(KEYS)])
    with s3_limits.s3_deadline():
        clock.t += 8  # 8 s used: no attempt may start
        with pytest.raises(s3_limits.DeadlineExceeded):
            client.list_objects_v2(Bucket=BUCKET)
    assert len(stub.calls) == 1


def test_deadline_is_per_request(monkeypatch, clock):
    # sequential half, on the fake clock
    client, stub = build_client(clock, [hang()])
    web = api(monkeypatch, client)
    assert web.get("/api/dogs").status_code == 503  # uses its whole deadline
    stub.script([ok(KEYS)])
    r = web.get("/api/dogs")  # same cached client, a fresh deadline
    assert r.status_code == 200
    assert len(r.json()) == 2

    # concurrent half, in real time with a short deadline (one fake clock cannot serve two threads)
    monkeypatch.undo()
    set_env(monkeypatch)
    monkeypatch.setattr(s3_limits, "DEADLINE", 0.4)

    def by_prefix(stub, timeout, request):
        if "pug" in request.url:
            time.sleep(0.05)
            raise ReadTimeoutError(endpoint_url=URL)
        return ok(KEYS)(stub, timeout, request)

    client, _stub = build_client(None, [by_prefix])
    web = api(monkeypatch, client)
    other = api(monkeypatch, client)  # a second test client: one per thread
    results = {}

    def get(web, path):
        results[path] = web.get(path).status_code

    threads = [
        threading.Thread(target=get, args=(w, p))
        for w, p in ((web, "/api/dogs/pug"), (other, "/api/dogs/beagle"))
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert results == {"/api/dogs/pug": 503, "/api/dogs/beagle": 200}


def test_abandoned_attempt_releases_resources(monkeypatch, clock):
    client, stub = build_client(clock, [drip(cost=4)])
    threads_before = threading.active_count()
    with s3_limits.s3_deadline(), pytest.raises(s3_limits.DeadlineExceeded):
        client.list_objects_v2(Bucket=BUCKET)
    assert stub.raws[0].closed  # the connection is closed
    assert threading.active_count() == threads_before  # no worker kept running for it
    stub.script([ok(KEYS)])
    assert api(monkeypatch, client).get("/api/dogs").status_code == 200
