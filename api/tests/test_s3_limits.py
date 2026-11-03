"""Limits and configuration of the real S3 client (change 0003, PLAN-0003 T-02, T-14, T-15)."""

import boto3
import pytest
from botocore.awsrequest import AWSRequest, AWSResponse
from botocore.exceptions import BotoCoreError
from botocore.httpsession import URLLib3Session
from s3_stub import BUCKET, REAL_S3, build_client, connect_timeout, fake_time, raises, set_env

from app import main, s3_limits


@pytest.fixture
def clock(monkeypatch):
    set_env(monkeypatch)
    return fake_time(monkeypatch)


def real_client(monkeypatch):
    set_env(monkeypatch)
    return REAL_S3.__wrapped__()


def test_s3_client_timeouts_configured(monkeypatch):
    config = real_client(monkeypatch).meta.config
    assert config.connect_timeout <= 3
    assert config.read_timeout <= 5


def test_s3_client_retries_configured(monkeypatch):
    retries = real_client(monkeypatch).meta.config.retries
    assert retries["mode"] == "standard"
    total = retries.get("total_max_attempts") or retries["max_attempts"] + 1  # botocore stores retries + 1
    assert total == 3


def test_s3_overall_deadline_is_8s(clock):
    assert s3_limits.DEADLINE == 8
    assert 10 - s3_limits.DEADLINE >= 2  # margin under the 10 s function timeout
    with s3_limits.s3_deadline() as deadline:
        assert deadline.left() == 8
        clock.t += 3
        assert deadline.left() == 5


def test_at_most_three_attempts(clock):
    client, stub = build_client(clock, [raises(connect_timeout)])
    with s3_limits.s3_deadline(), pytest.raises(BotoCoreError):
        list(client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET))
    assert len(stub.calls) == 3


def test_botocore_internals_available(monkeypatch):
    client = real_client(monkeypatch)
    session = client._endpoint.http_session
    checks = {
        "URLLib3Session.send": callable(getattr(URLLib3Session, "send", None)),
        "client._endpoint.http_session (DeadlineSession installed)": isinstance(
            session, s3_limits.DeadlineSession
        ),
        "session._timeout": hasattr(session, "_timeout"),
        "session._manager.connection_pool_kw['timeout']": "timeout" in session._manager.connection_pool_kw,
        "AWSResponse.raw": AWSResponse("https://x", 200, {}, object()).raw is not None,
        "AWSPreparedRequest.stream_output": hasattr(
            AWSRequest(method="GET", url="https://x").prepare(), "stream_output"
        ),
        "events.register_first": callable(getattr(client.meta.events, "register_first", None)),
    }
    assert [name for name, present in checks.items() if not present] == []


def test_deadline_session_keeps_tls_verification(monkeypatch):
    set_env(monkeypatch)
    plain = boto3.client("s3", region_name="eu-north-1", endpoint_url=main.s3.__wrapped__().meta.endpoint_url)
    mine = main.s3.__wrapped__()._endpoint.http_session
    stock = plain._endpoint.http_session
    assert isinstance(mine, s3_limits.DeadlineSession)
    assert plain.meta.endpoint_url.startswith("https://")
    assert mine._verify is not False
    assert mine._verify == stock._verify  # same CA bundle setting as the default session
    assert mine._cert_file == stock._cert_file
    assert vars(mine._proxy_config) == vars(stock._proxy_config)
