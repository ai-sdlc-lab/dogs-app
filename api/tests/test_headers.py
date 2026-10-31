"""SR-004 security headers and SR-003 output handling (change 0002, PLAN-0002 A-01 to A-05)."""

import mimetypes
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import main

BUCKET = "sdlc-lab-app-dogs-dev-992382408037"
HOST = f"{BUCKET}.s3.eu-north-1.amazonaws.com"
COMMON = {
    "X-Content-Type-Options": "nosniff",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "no-referrer",
}
FALLBACK_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)
CSP = FALLBACK_CSP.replace("img-src 'self';", f"img-src 'self' https://{HOST};")
HTML_ONLY = ("Content-Security-Policy", "Cross-Origin-Opener-Policy")
JSON = "application/json; charset=utf-8"
HTML = "text/html; charset=utf-8"
JS = "text/javascript; charset=utf-8"
JS_PATH = "/assets/index-abc.js"
REAL_S3 = main.s3  # the cached boto3 factory, before any test replaces it
WEB = Path(__file__).resolve().parents[2] / "web"

# SPEC 9 web-build fixture (each file longer than 10 bytes, so Range: bytes=0-9 is a real 206).
FILES = {
    "index.html": b"<!doctype html><html><head><title>Dogs</title></head><body></body></html>\n",
    "assets/index-abc.js": b"console.log('dogs');\n",
    "assets/index-abc.css": b"body { margin: 0; }\n",
    "assets/dog.png": b"\x89PNG\r\n\x1a\n" + bytes(32),
    "favicon.ico": b"\x00\x00\x01\x00" + bytes(32),
    "assets/logo.svg": b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>\n',
    "sub/index.html": b"<!doctype html><title>sub</title>\n",
}


class FakeS3:
    """Like test_api.FakeS3, for the deployed bucket name."""

    keys = ["dogs/beagle/1.jpg", "dogs/pug/1.jpg", "dogs/README", "dogs/Bad_Breed/x.jpg"]

    def get_paginator(self, _):
        return self

    def paginate(self, Bucket, Prefix):
        assert Bucket == BUCKET
        return [{"Contents": [{"Key": k} for k in self.keys if k.startswith(Prefix)]}]

    def generate_presigned_url(self, op, Params, ExpiresIn):
        assert op == "get_object" and ExpiresIn == main.URL_TTL
        return f"https://{HOST}/{Params['Key']}?X-Amz-Signature=x"


class MarkupS3(FakeS3):
    keys = ["dogs/pug/<script>.jpg"]


class BrokenS3:
    def get_paginator(self, _):
        raise RuntimeError("S3 listing failed")


@pytest.fixture
def web(tmp_path):
    for name, body in FILES.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(body)
    return tmp_path


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("DOGS_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_REGION", "eu-north-1")
    monkeypatch.setattr(main, "s3", FakeS3)
    main.csp.cache_clear()
    yield monkeypatch
    main.csp.cache_clear()


@pytest.fixture
def client(web, settings):
    return TestClient(main.build(web), raise_server_exceptions=False)


def assert_headers(r, ctype, html):
    for name, value in COMMON.items():
        assert r.headers.get_list(name) == [value], name
    if ctype is None:
        assert "content-type" not in r.headers
    else:
        assert r.headers.get_list("content-type") == [ctype]
    if html:
        assert r.headers.get_list("content-security-policy") == [CSP]
        assert r.headers.get_list("cross-origin-opener-policy") == ["same-origin"]
    else:
        for name in HTML_ONLY:
            assert name not in r.headers, name
    assert not [k for k in r.headers if k.lower().startswith("access-control-")]
    assert "cache-control" not in r.headers


def csp_of(client):
    return client.get("/").headers["content-security-policy"]


# method, path, request headers, status, Content-Type (None: no body), HTML headers expected
CASES = [
    ("GET", "/api/health", {}, 200, JSON, False),
    ("GET", "/api/dogs", {}, 200, JSON, False),
    ("GET", "/api/dogs/pug", {}, 200, JSON, False),
    ("GET", "/api/dogs/husky", {}, 404, JSON, False),
    ("GET", "/api/dogs/Bad_Breed", {}, 404, JSON, False),
    ("GET", "/api/nope", {}, 404, JSON, False),
    ("GET", "/nope", {}, 404, JSON, False),
    ("GET", "/assets/missing.js", {}, 404, JSON, False),
    ("POST", "/api/health", {}, 405, JSON, False),
    ("OPTIONS", "/api/dogs", {}, 405, JSON, False),
    ("GET", "/", {}, 200, HTML, True),
    ("GET", "/index.html", {}, 200, HTML, True),
    ("HEAD", "/", {}, 200, HTML, True),
    ("GET", JS_PATH, {}, 200, JS, False),
    ("GET", "/assets/index-abc.css", {}, 200, "text/css; charset=utf-8", False),
    ("GET", "/assets/dog.png", {}, 200, "image/png", False),
    ("GET", "/favicon.ico", {}, 200, "image/x-icon", False),
    ("GET", "/assets/logo.svg", {}, 200, "image/svg+xml; charset=utf-8", False),
    ("GET", "/sub", {}, 307, None, False),
    ("GET", "/", {"Range": "bytes=0-9"}, 206, HTML, True),
    ("GET", JS_PATH, {"Range": "bytes=0-9"}, 206, JS, False),
    ("GET", JS_PATH, {"Range": "bytes=999999999-"}, 416, None, False),
    ("GET", "/api/dogs", {}, 500, "text/plain; charset=utf-8", False),  # S3 listing raises
]


@pytest.mark.parametrize(("method", "path", "headers", "status", "ctype", "html"), CASES)
def test_security_headers(client, settings, method, path, headers, status, ctype, html):
    if status == 500:  # forced unhandled error
        settings.setattr(main, "s3", BrokenS3)
    r = client.request(method, path, headers=headers, follow_redirects=False)
    assert r.status_code == status
    assert_headers(r, ctype, html)


def test_security_headers_on_unhandled_error(client, settings):
    settings.setattr(main, "s3", BrokenS3)
    r = client.get("/api/dogs")
    assert (r.status_code, r.text) == (500, "Internal Server Error")
    assert_headers(r, "text/plain; charset=utf-8", html=False)


def test_security_headers_replace_existing_values(settings):
    async def inner(scope, receive, send):
        headers = [
            (b"X-Content-Type-Options", b"sniff"),
            (b"referrer-policy", b"origin"),
            (b"Referrer-Policy", b"unsafe-url"),
            (b"content-type", b"application/json"),
        ]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": b"{}"})

    r = TestClient(main.security_headers(inner)).get("/api/x")
    assert_headers(r, JSON, html=False)


def test_content_type_exact_per_asset_type(client, settings):
    wrong = mimetypes.MimeTypes()
    for ext in (".js", ".css", ".png", ".ico", ".svg", ".html"):
        wrong.add_type("application/octet-stream", ext)
    settings.setattr(mimetypes, "_db", wrong)
    assert mimetypes.guess_type("x.js")[0] == "application/octet-stream"  # the table is really altered
    expected = {
        "/": HTML,
        "/index.html": HTML,
        JS_PATH: JS,
        "/assets/index-abc.css": "text/css; charset=utf-8",
        "/assets/dog.png": "image/png",
        "/favicon.ico": "image/x-icon",
        "/assets/logo.svg": "image/svg+xml; charset=utf-8",
    }
    for path, ctype in expected.items():
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers.get_list("content-type") == [ctype], path


def test_csp_image_host_matches_presigned_url_host(client, settings):
    settings.setenv("AWS_ACCESS_KEY_ID", "x")
    settings.setenv("AWS_SECRET_ACCESS_KEY", "y")
    url = REAL_S3.__wrapped__().generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": "dogs/pug/1.jpg"}, ExpiresIn=60
    )
    directives = dict(d.strip().split(" ", 1) for d in csp_of(client).split(";"))
    sources = [s for s in directives["img-src"].split() if s != "'self'"]
    assert len(sources) == 1
    assert urlsplit(sources[0]).scheme == "https"
    assert urlsplit(sources[0]).netloc == urlsplit(url).netloc == HOST


def test_csp_has_no_unsafe_or_wildcard_sources(client):
    for value in (csp_of(client), FALLBACK_CSP):
        for bad in ("unsafe-inline", "unsafe-eval", "*", "data:", "blob:", "http:"):
            assert bad not in value, bad


@pytest.mark.parametrize(
    ("bucket", "region"),
    [
        (None, "eu-north-1"),
        ("Bad.Bucket", "eu-north-1"),
        ("a", "eu-north-1"),
        ("a" * 64, "eu-north-1"),
        ("x; script-src *", "eu-north-1"),
        (BUCKET + "\n", "eu-north-1"),
        (BUCKET, "us-east-1"),
    ],
)
def test_csp_falls_back_without_valid_bucket(client, settings, bucket, region):
    if bucket is None:
        settings.delenv("DOGS_BUCKET")
    else:
        settings.setenv("DOGS_BUCKET", bucket)
    settings.setenv("AWS_REGION", region)
    main.csp.cache_clear()
    assert csp_of(client) == FALLBACK_CSP


def test_headers_independent_of_request_input(client):
    owned = ("content-type", *COMMON, *HTML_ONLY)
    hostile = {"Host": "evil.example", "X-Forwarded-Host": "evil.example", "Origin": "https://evil.example"}
    for path, variant in [
        ("/", "/?a=%0d%0aX-Injected:1"),
        ("/api/health", "/api/health?a=%0d%0aX-Injected:1"),
        ("/nope", "/nope%0d%0aX-Injected:1"),
    ]:
        base = client.get(path)
        for r in (client.get(path, headers=hostile), client.get(variant, headers=hostile)):
            assert {n: r.headers.get_list(n) for n in owned} == {n: base.headers.get_list(n) for n in owned}
            assert "x-injected" not in r.headers
    assert csp_of(client) == CSP


def test_cors_preflight_gets_no_cors_headers(client):
    r = client.options(
        "/api/dogs", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert r.status_code == 405
    assert_headers(r, JSON, html=False)


def test_not_modified_keeps_security_headers(client):
    for path, html in (("/", True), (JS_PATH, False)):
        etag = client.get(path).headers["etag"]
        r = client.get(path, headers={"If-None-Match": etag})
        assert r.status_code == 304, path
        assert_headers(r, None, html)


def test_api_json_encodes_markup_in_filename(client, settings):
    settings.setattr(main, "s3", MarkupS3)
    r = client.get("/api/dogs")
    assert r.headers.get_list("content-type") == [JSON]
    assert r.json() == [{"breed": "pug", "url": f"https://{HOST}/dogs/pug/<script>.jpg?X-Amz-Signature=x"}]
    outside_strings = re.sub(r'"(?:[^"\\]|\\.)*"', '""', r.text)
    assert "<" not in outside_strings


# --- page source (M-09) ------------------------------------------------------------------------

FORBIDDEN = {  # [\x22\x27] = a double or single quote
    "style element": r"<style\b",
    "style attribute": r"\sstyle\s*=\s*[\x22\x27]",
    "event handler attribute": r"\son[a-z]+\s*=\s*[\x22\x27]",
    "handler or style via setAttribute": r"setAttribute\(\s*[\x22\x27](on|style)",
    "eval": r"\beval\s*\(",
    "new Function": r"\bnew\s+Function\b",
    "innerHTML": r"innerHTML",
    "absolute http(s) URL": r"https?://",
}
SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)


def test_page_has_no_inline_code():
    files = [WEB / "index.html", *(p for p in (WEB / "src").rglob("*") if p.is_file())]
    assert len(files) > 2
    for f in files:
        text = f.read_text()
        for what, pattern in FORBIDDEN.items():
            assert not re.search(pattern, text, re.IGNORECASE), f"{f.name}: {what}"
        for attrs, body in SCRIPT.findall(text):
            assert "src=" in attrs and not body.strip(), f"{f.name}: inline script"
