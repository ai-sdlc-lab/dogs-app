"""S3 limits (SPEC-0003): 3 s connect, 5 s read, 3 attempts (standard mode), 8 s deadline per request.

The deadline lives in a ContextVar set by `s3_deadline()`; the cached client and the session hold no
per-request state. Private botocore parts used (guarded by test_botocore_internals_available):
URLLib3Session.send / _timeout / _manager.connection_pool_kw, AWSResponse.raw, client._endpoint.http_session.
"""

import contextlib
import contextvars
import time

import urllib3.exceptions
from botocore import exceptions as bce
from botocore.httpsession import URLLib3Session
from urllib3.util import Timeout

CONNECT_TIMEOUT = 3
READ_TIMEOUT = 5
MAX_ATTEMPTS = 3
DEADLINE = 8
CHUNK = 65536

_current = contextvars.ContextVar("s3_deadline", default=None)


def now() -> float:
    """The only time source of the deadline code (tests replace it)."""
    return time.monotonic()


class DeadlineExceeded(Exception):
    """Not a botocore error type, so the standard retry handler never retries it."""


class Deadline:
    def __init__(self):
        self.start = now()
        self.limit = DEADLINE

    def left(self) -> float:
        return self.limit - (now() - self.start)


@contextlib.contextmanager
def s3_deadline():
    token = _current.set(Deadline())
    try:
        yield _current.get()
    finally:
        _current.reset(token)


class _Timeout(Timeout):
    """Pool-level timeout; every request gets a clone shrunk to the time left of its own deadline."""

    def clone(self):
        deadline = _current.get()
        if deadline is None:
            return Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT)
        left = max(deadline.left(), 0.001)
        return Timeout(connect=min(CONNECT_TIMEOUT, left), read=min(READ_TIMEOUT, left))


class _Bounded:
    """Wraps the raw response: reads in small pieces, each bounded by the time left (slow drip)."""

    def __init__(self, raw, deadline, request):
        self._raw = raw
        self._deadline = deadline
        self._request = request

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def _set_socket_timeout(self, seconds):
        sock = getattr(getattr(self._raw, "_connection", None), "sock", None)
        if sock is not None:
            sock.settimeout(seconds)

    def _translate(self, exc):
        url = self._request.url
        if isinstance(exc, urllib3.exceptions.ReadTimeoutError):
            return bce.ReadTimeoutError(endpoint_url=url, request=self._request, error=exc)
        if isinstance(exc, urllib3.exceptions.ProtocolError):
            return bce.ConnectionClosedError(endpoint_url=url, request=self._request, error=exc)
        if isinstance(exc, Exception) and not isinstance(exc, (DeadlineExceeded, bce.BotoCoreError)):
            return bce.HTTPClientError(request=self._request, error=exc)
        return exc

    def stream(self, *_args, **_kwargs):
        read1 = getattr(self._raw, "read1", None)  # ponytail: read(1) fallback is slow on big bodies
        try:
            while True:
                left = self._deadline.left()
                if left <= 0:
                    raise DeadlineExceeded
                self._set_socket_timeout(min(READ_TIMEOUT, left))
                data = read1(CHUNK) if read1 else self._raw.read(1)
                if not data:
                    break
                yield data
        except BaseException as exc:  # abandon: close the connection, never reuse it
            self._raw.close()
            self._raw.release_conn()
            translated = self._translate(exc)
            if translated is exc:
                raise
            raise translated from exc
        self._raw.release_conn()


class DeadlineSession(URLLib3Session):
    @classmethod
    def adopt(cls, session):
        """Turn the client's own session into a DeadlineSession; verify, proxies and certs stay as built."""
        session.__class__ = cls
        timeout = _Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT)
        session._timeout = timeout
        session._manager.connection_pool_kw["timeout"] = timeout
        return session

    def _raw_send(self, request):
        """The bottom of the session (tests replace this one call)."""
        return URLLib3Session.send(self, request)

    def send(self, request):
        deadline = _current.get()
        if deadline is None:
            return self._raw_send(request)
        if deadline.left() <= 0:
            raise DeadlineExceeded  # no attempt starts at or after the deadline
        wants_stream = request.stream_output
        request.stream_output = True  # so the body is read below, under the deadline
        response = self._raw_send(request)
        response.raw = _Bounded(response.raw, deadline, request)
        if not wants_stream:
            _ = response.content
        return response


def _refuse_late_retry(response=None, caught_exception=None, attempts=1, **_):
    """Stop (instead of sleeping) when a retry might be due but the backoff could run past the deadline.

    Independent of botocore's retry classification: every exception and every response that is not 2xx/3xx
    counts (incl. 4xx throttling codes); refusing a retry that would not have happened is harmless.
    """
    deadline = _current.get()
    if deadline is None or attempts >= MAX_ATTEMPTS:
        return None
    status = response[0].status_code if response and response[0] is not None else 0
    failed = caught_exception is not None or status >= 400
    if failed and deadline.left() <= 2 ** (attempts - 1):  # largest standard-mode backoff: 1 s, then 2 s
        raise DeadlineExceeded
    return None


def install(client):
    DeadlineSession.adopt(client._endpoint.http_session)
    client.meta.events.register_first("needs-retry.s3", _refuse_late_retry)
    return client
