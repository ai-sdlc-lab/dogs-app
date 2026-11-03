"""Real-network check of the slow-drip abandon case (change 0003, PLAN-0003 T-16).

The client is built like production (same limits, `install()`), but points at a loopback server over plain
http because the production endpoint is fixed to the S3 https host.
"""

import socketserver
import threading
import time

import boto3
import pytest
from botocore.config import Config
from s3_stub import listing, set_env

from app import s3_limits

HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: application/xml\r\n"


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        sock, buf = self.request, b""
        while b"\r\n\r\n" not in buf:
            data = sock.recv(4096)
            if not data:
                return
            buf += data
        if self.server.mode == "ok":
            body = listing(["dogs/pug/1.jpg"])
            sock.sendall(HEAD + b"Content-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
            return
        if self.server.mode == "silent":
            time.sleep(10)
            return
        sock.sendall(HEAD + b"Content-Length: 100000\r\n\r\n")
        try:
            while True:  # one byte per 0.2 s until the client goes away
                sock.sendall(b"<")
                time.sleep(0.2)
        except OSError:
            self.server.closed.set()


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    mode = "drip"

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.closed = threading.Event()


def _client(server):
    client = boto3.client(
        "s3",
        region_name="eu-north-1",
        endpoint_url=f"http://127.0.0.1:{server.server_address[1]}",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=s3_limits.CONNECT_TIMEOUT,
            read_timeout=s3_limits.READ_TIMEOUT,
            retries={"mode": "standard", "total_max_attempts": s3_limits.MAX_ATTEMPTS},
        ),
    )
    s3_limits.install(client)
    return client


def test_shrunken_timeouts_applied_by_real_pool(monkeypatch):
    set_env(monkeypatch)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "127.0.0.1")
    monkeypatch.setattr(s3_limits, "DEADLINE", 0.5)
    server = Server()
    server.mode = "silent"  # reads the request, never answers
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = _client(server)
        started = time.monotonic()
        with s3_limits.s3_deadline(), pytest.raises(s3_limits.DeadlineExceeded):
            client.list_objects_v2(Bucket="b")
        assert time.monotonic() - started < 2.5  # far below the 5 s read default
    finally:
        server.shutdown()
        server.server_close()


def test_slow_drip_abandon_over_real_socket(monkeypatch):
    set_env(monkeypatch)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "127.0.0.1")
    monkeypatch.setattr(s3_limits, "DEADLINE", 1.0)
    server = Server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = _client(server)
        started = time.monotonic()
        with s3_limits.s3_deadline(), pytest.raises(s3_limits.DeadlineExceeded):
            client.list_objects_v2(Bucket="b")
        assert time.monotonic() - started < 2.5  # the 1 s deadline plus slack
        assert server.closed.wait(3), "the abandoned connection was not closed"
        server.mode = "ok"  # the same client still works
        with s3_limits.s3_deadline():
            assert client.list_objects_v2(Bucket="b")["Contents"][0]["Key"] == "dogs/pug/1.jpg"
    finally:
        server.shutdown()
        server.server_close()
