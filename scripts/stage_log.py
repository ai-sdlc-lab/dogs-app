"""Local stage log: JSON Lines events in .claude/stage-log.jsonl, entries older than 30 days dropped
at every stage start (SPEC-0001 §6, §7). Same fields as appsec-baseline stage/log.py.

Usage: python3 -I -B scripts/stage_log.py EVENT OUTCOME [key=value ...]   (also prunes)
"""

import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / ".claude" / "stage-log.jsonl"
RETENTION = timedelta(days=30)
_CONTROL = re.compile("[\\x00-\\x1f\\x7f\\u2028\\u2029]")
EVENTS = {
    "stage.start",
    "stage.round",
    "review.finding",
    "gate.allow",
    "gate.block",
    "gate.escalate",
    "owner.decision",
    "authz.denied",
    "authz.ask",
    "input.rejected",
    "verify.pass",
    "verify.fail",
    "pr.merged",
}
EXTRA_KEYS = {"reason", "actor", "change", "stage", "request_id", "detail", "item", "count"}
REQUIRED = ("ts", "level", "service", "version", "event", "outcome", "reason", "actor", "change", "stage", "request_id")


def _clean(v, limit=200) -> str:
    s = _CONTROL.sub(" ", str(v)).lstrip()
    while s.startswith("::"):
        s = s[2:].lstrip()
    return s[:limit]


def _version() -> str:
    try:
        return (ROOT / "appsec-baseline.lock").read_text().strip()[:40]
    except OSError:
        return "unknown"


def write(event: str, outcome: str, *, log: Path = LOG, **fields) -> dict:
    if event not in EVENTS or outcome not in ("success", "failure", "denied"):
        raise ValueError(f"bad event {event}/{outcome}")
    rec = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": "WARN" if outcome != "success" else "INFO",
        "service": "stage-loop",
        "version": _version(),
        "event": event,
        "outcome": outcome,
        "reason": "",
        "actor": "session",
        "change": "",
        "stage": "",
        "request_id": "",
    }
    for k, v in fields.items():
        if k not in EXTRA_KEYS:
            raise ValueError(f"field {k!r} can't be set")
        rec[k] = v if isinstance(v, (int, bool)) else _clean(v)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def prune(log: Path = LOG, now: datetime | None = None) -> int:
    """Drop entries older than 30 days. Unparsable lines are kept (evidence), never silently deleted."""
    if not log.exists():
        return 0
    cutoff = (now or datetime.now(UTC)) - RETENTION
    keep, dropped = [], 0
    for line in log.read_bytes().decode("utf-8", "replace").splitlines():
        try:
            ts = datetime.fromisoformat(json.loads(line)["ts"].replace("Z", "+00:00"))
            old = ts < cutoff  # a naive timestamp raises TypeError here and the line is kept
        except (ValueError, KeyError, TypeError, AttributeError):
            keep.append(line)
            continue
        if old:
            dropped += 1
        else:
            keep.append(line)
    tmp = log.with_suffix(".tmp")
    tmp.write_text("".join(f"{x}\n" for x in keep))
    os.replace(tmp, log)
    return dropped


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    prune()
    kv = dict(a.split("=", 1) for a in sys.argv[3:] if "=" in a)  # only EXTRA_KEYS are accepted
    write(sys.argv[1], sys.argv[2], **kv)
