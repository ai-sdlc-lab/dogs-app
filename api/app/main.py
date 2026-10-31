import os
import re
from functools import cache
from pathlib import Path, PurePosixPath

import boto3
from botocore.config import Config
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from mangum import Mangum

PREFIX = "dogs/"  # images live at s3://$DOGS_BUCKET/dogs/<breed>/<file>
BREED = re.compile(r"^[a-z0-9-]{1,40}$")
URL_TTL = 900  # presigned image URLs expire after 15 minutes; the bucket stays private

router = APIRouter()


@cache
def s3():
    # Regional endpoint: presigned URLs on the global s3.amazonaws.com host get a
    # TemporaryRedirect for new buckets, which browsers' <img> requests don't survive.
    region = os.environ.get("AWS_REGION", "eu-north-1")
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def list_dogs(breed: str | None = None) -> list[dict]:
    bucket = os.environ["DOGS_BUCKET"]
    prefix = PREFIX + (f"{breed}/" if breed else "")
    dogs = []
    for page in s3().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            parts = obj["Key"].removeprefix(PREFIX).split("/")
            if len(parts) != 2 or not BREED.match(parts[0]) or not parts[1]:
                continue
            url = s3().generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": obj["Key"]}, ExpiresIn=URL_TTL
            )
            dogs.append({"breed": parts[0], "url": url})
    return dogs


@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.get("/api/dogs")
def dogs():
    return list_dogs()


@router.get("/api/dogs/{breed}")
def dogs_by_breed(breed: str):
    if not BREED.match(breed):
        raise HTTPException(status_code=404, detail="unknown breed")
    found = list_dogs(breed)
    if not found:
        raise HTTPException(status_code=404, detail="unknown breed")
    return found


# --- SR-004 security headers (change 0002) ---------------------------------------------------
# Fixed values; nothing from the request is ever copied into a header (M-01).
COMMON_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"referrer-policy", b"no-referrer"),
]
COOP = (b"cross-origin-opener-policy", b"same-origin")
CSP_NAME = b"content-security-policy"
# Replaced on every response, in any letter case (set, not append: M-02).
OWNED = {name for name, _ in COMMON_HEADERS} | {CSP_NAME, COOP[0], b"content-type"}

# The app's own types win over the runtime MIME table (M-04). Only for 200/206 files outside /api/.
CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}
TEXT_TYPES = {"application/json", "application/javascript", "image/svg+xml"}
BUCKET_NAME = re.compile(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]")  # used with fullmatch: no dots, 3-63 chars


@cache
def csp() -> str:
    """CSP for HTML responses; the image host comes only from validated deployment settings (M-05)."""
    bucket = os.environ.get("DOGS_BUCKET", "")
    region = os.environ.get("AWS_REGION", "eu-north-1")
    valid = BUCKET_NAME.fullmatch(bucket) is not None and region == "eu-north-1"
    img = f"'self' https://{bucket}.s3.{region}.amazonaws.com" if valid else "'self'"  # else fail closed
    return (
        f"default-src 'none'; script-src 'self'; style-src 'self'; img-src {img}; connect-src 'self'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
    )


def suffix(path: str) -> str:
    return ".html" if path.endswith("/") else PurePosixPath(path).suffix.lower()


def secure_headers(status: int, path: str, raw: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """The final header list of a response: SR-004 headers set once, exact Content-Type (SPEC 1.2-1.4)."""
    ctype = next((v.decode("latin-1") for k, v in raw if k.lower() == b"content-type"), None)
    length = next((v for k, v in raw if k.lower() == b"content-length"), None)
    if status in (204, 304) or length == b"0":
        ctype = None  # no body, no Content-Type
    elif ctype is not None:
        if status in (200, 206) and not path.startswith("/api/") and not ctype.startswith("multipart/"):
            ctype = CONTENT_TYPES.get(suffix(path), ctype)  # the path only selects a fixed entry
        base = ctype.split(";")[0].strip().lower()
        if base.startswith("text/") or base in TEXT_TYPES:
            ctype = f"{base}; charset=utf-8"
    headers = [(k, v) for k, v in raw if k.lower() not in OWNED]
    if ctype is not None:
        headers.append((b"content-type", ctype.encode("latin-1")))
    headers += COMMON_HEADERS
    html = ctype is not None and ctype.startswith("text/html")
    if html or (status == 304 and suffix(path) == ".html"):
        headers += [(CSP_NAME, csp().encode("latin-1")), COOP]
    return headers


def security_headers(app):
    """Outermost pure ASGI wrapper: sees every response, including the 500 of ServerErrorMiddleware."""

    async def wrapped(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        path = scope["path"]

        async def send_secure(message):
            if message["type"] == "http.response.start":
                headers = secure_headers(message["status"], path, list(message.get("headers", [])))
                message = {**message, "headers": headers}
            await send(message)

        await app(scope, receive, send_secure)

    return wrapped


def build(web_dir: Path):
    api = FastAPI(title="dogs-app", docs_url=None, redoc_url=None, openapi_url=None)
    api.include_router(router)
    if web_dir.is_dir():
        api.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return security_headers(api)


# The built web app (web/dist) is bundled next to the code in Lambda; absent in tests and the k8s image.
WEB_DIR = Path(os.environ.get("WEB_DIR", Path(__file__).parent.parent / "web"))
app = build(WEB_DIR)
handler = Mangum(app, lifespan="off")
