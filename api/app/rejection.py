"""Rejected input (SPEC-0004): request ID, `input.rejected` log event and the fixed 422 response."""

import contextlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

BUILD_INFO = Path(__file__).parent / "build_info.json"  # written into the Lambda zip by `make build-info`
PATH_MAX = 200


def request_id(request: Request) -> str:
    """Lambda request ID from the platform context, else 128 random bits as 32 hex; never raises."""
    with contextlib.suppress(Exception):
        rid = request.scope["aws.context"].aws_request_id  # set by Mangum; never a header or query value
        if isinstance(rid, str) and rid:
            return rid
    return secrets.token_hex(16)


def version() -> str:
    try:
        sha = json.loads(BUILD_INFO.read_text())["sha"]
    except Exception:
        return "unknown"
    return sha if isinstance(sha, str) and sha else "unknown"


def _write(request: Request, rid: str, reason: str) -> None:
    with contextlib.suppress(Exception):  # a logging failure never reaches the response (SPEC 7.3a)
        try:
            ip = request.scope["aws.event"]["requestContext"]["http"]["sourceIp"]
        except Exception:
            ip = None
        event = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": "WARN",
            "event": "input.rejected",
            "outcome": "failure",
            "request_id": rid,
            "actor": "anonymous",
            "source_ip": ip if isinstance(ip, str) and ip else "unknown",
            # scope["path"] (decoded, no query string); request.url would strip newlines
            "http": {"method": request.method, "path": request.scope["path"][:PATH_MAX], "status": 422},
            "reason": reason,
            "service": "dogs-app",
            "version": version(),
        }
        # ensure_ascii (default) escapes newline, control and non-ASCII characters: one line
        print(json.dumps(event), flush=True)


def rejected(request: Request, reason: str) -> JSONResponse:
    rid = request_id(request)
    _write(request, rid, reason)
    return JSONResponse(status_code=422, content={"error": "invalid_input", "request_id": rid})
