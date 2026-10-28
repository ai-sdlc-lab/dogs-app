#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write/NotebookEdit/Bash (SPEC-0001 §5, M-03, M-11, M-21, M-24, M-26).

Fails closed: any error or malformed input blocks (exit 2). Decisions:
- deny (exit 2, reason on stderr), or ask (permissionDecision "ask", exit 0), or allow (exit 0, no output).
- Subagents (`agent_id` present): default deny. Only the `author` may write, and only the current stage's
  artifact (stage/<NNNN>-<stage> branch) or, at the code stage, files listed in this repo's PLAN section.
  A payload with `agent_type` but no `agent_id` is denied.
- Main session: TRACE-/THREAT- files only via stage/write_artifact.py; `.github/` only on a code-stage branch;
  `.claude/`, CLAUDE.md, REVIEW.md, stages.yml, appsec-baseline.lock, `.appsec-baseline/` ask the owner;
  Bash: apply/destroy/seed denied, merges and pushes that may reach main ask, writes to protected paths ask.
- Bypass permission mode: everything is denied.
Every deny and ask is written to .claude/stage-log.jsonl.

Command-text rules are best effort, not a security boundary (owner-accepted residual, SPEC-0001 §5).
"""

import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ASK_PATHS = [".claude/*", "CLAUDE.md", "REVIEW.md", "stages.yml", "appsec-baseline.lock", ".appsec-baseline/*"]
ARTIFACT = re.compile(r"^docs/specs/(?P<n>[0-9]{4})-[a-z0-9-]+/(?P<kind>INT|SPEC|PLAN|TRACE|THREAT)-(?P=n)\.md$")
STAGE_BRANCH = re.compile(r"^stage/(?P<n>[0-9]{4})-(?P<stage>intent|spec|plan|code)$")
STAGE_KIND = {"intent": "INT", "spec": "SPEC", "plan": "PLAN"}
APPLY = re.compile(r"\b(terraform|tofu)\b[^|;&]*\bapply\b|\bmake\b[^|;&]*\b(apply|destroy|seed)\b")
MERGE = re.compile(r"\bgh\s+pr\s+merge\b(?P<rest>[^|;&]*)")
API_MERGE = re.compile(r"\bgh\s+api\b[^|;&]*(/merges?\b|pulls/[0-9]+/merge)")
PUSH_MAIN = re.compile(r"\bgit\b[^|;&]*\bpush\b[^|;&]*(\bmain\b|refs/heads/main|:main\b)")
WRITE_OPS = re.compile(
    r"(>>?|\btee\b|\bsed\s+-i|\bcp\b|\bmv\b|\brm\b|\btouch\b|\bln\b|\binstall\b|\bchmod\b|\bperl\b"
    r"|python3?\s+-c|\bgit\s+(checkout|restore)\b)"
)
PROTECTED_IN_CMD = re.compile(r"(\.claude/|CLAUDE\.md|REVIEW\.md|stages\.yml|appsec-baseline\.lock|\.appsec-baseline/)")
TRACE_THREAT_IN_CMD = re.compile(r"(TRACE|THREAT)-[0-9]{4}\.md")
CONTROL = re.compile("[\\x00-\\x1f\\x7f]")


def root_dir(event) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()


def log(root: Path, event: dict, name: str, reason: str, detail: str) -> None:
    try:
        lock = root / "appsec-baseline.lock"
        rec = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": "WARN",
            "service": "hook",
            "version": lock.read_text().strip()[:40] if lock.exists() else "unknown",
            "event": name,
            "outcome": "denied" if name == "authz.denied" else "success",
            "reason": reason,
            "actor": CONTROL.sub(" ", str(event.get("agent_type") or "session"))[:60],
            "change": "",
            "stage": "",
            "request_id": CONTROL.sub(" ", str(event.get("session_id", "")))[:80],
            "detail": CONTROL.sub(" ", detail)[:200],
        }
        (root / ".claude").mkdir(exist_ok=True)
        with open(root / ".claude" / "stage-log.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def deny(root, event, reason, detail):
    log(root, event, "authz.denied", reason, detail)
    print(f"Blocked ({reason}): {detail}", file=sys.stderr)
    sys.exit(2)


def ask(root, event, reason, detail):
    log(root, event, "authz.ask", reason, detail)
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"{reason}: {detail}",
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def branch(root: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=False, timeout=10
    )
    return r.stdout.strip()


def plan_files(root: Path, change: str) -> list[str]:
    """Files listed in this repo's PLAN section, parsed with the locked appsec-baseline plan module."""
    sys.path.insert(0, str(root / ".appsec-baseline" / "stage"))
    from plan import steps  # noqa: PLC0415 - trusted checkout, imported only when needed

    plans = sorted((root / "docs" / "specs").glob(f"{change}-*/PLAN-{change}.md"))
    if not plans:
        return []
    return [f for s in steps(plans[0].read_text(), "dogs-app") for f in s["files"]]


def glob_match(path: str, entry: str) -> bool:
    entry = entry.rstrip("/") + ("/**" if entry.endswith("/") else "")
    parts = re.split(r"(\*\*|\*)", entry)
    rx = "".join(".*" if t == "**" else "[^/]*" if t == "*" else re.escape(t) for t in parts)
    return re.fullmatch(rx, path) is not None


def check_file(root: Path, event: dict, rel: str, subagent: bool) -> None:
    if rel.startswith("..") or os.path.isabs(rel):
        deny(root, event, "outside_repo", rel)
    m = ARTIFACT.match(rel)
    if subagent:
        if event.get("agent_type") != "author":
            deny(root, event, "subagent_read_only", f"{event.get('agent_type')} may not write {rel}")
        b = STAGE_BRANCH.match(branch(root))
        if not b:
            deny(root, event, "no_stage_branch", f"the author writes only on a stage/<NNNN>-<stage> branch ({rel})")
        n, stage = b["n"], b["stage"]
        if stage in STAGE_KIND:
            if not (m and m["n"] == n and m["kind"] == STAGE_KIND[stage]):
                deny(root, event, "author_scope", f"at the {stage} stage the author writes only {STAGE_KIND[stage]}-{n}.md")
            return
        protected = any(fnmatch.fnmatch(rel, p) for p in ASK_PATHS) or rel.startswith(".github/")
        if "/reviews/" in rel or (m and m["kind"] in ("TRACE", "THREAT")) or protected:
            deny(root, event, "author_scope", rel)
        if m and m["kind"] == "PLAN" and m["n"] == n:
            return  # the plan is updated in the same PR when the work departs from it
        if not any(glob_match(rel, f) for f in plan_files(root, n)):
            deny(root, event, "author_scope", f"{rel} is not listed in the dogs-app section of PLAN-{n}.md")
        return
    if m and m["kind"] in ("TRACE", "THREAT"):
        deny(root, event, "trace_threat", f"{rel} is written only by stage/write_artifact.py")
    if rel.startswith(".github/"):
        b = STAGE_BRANCH.match(branch(root))
        if not (b and b["stage"] == "code"):
            deny(root, event, "github_outside_code_stage", rel)
        return
    if any(fnmatch.fnmatch(rel, p) for p in ASK_PATHS):
        ask(root, event, "protected_path", rel)


def pr_base(root: Path, ref: str) -> str:
    args = ["gh", "pr", "view", *([ref] if ref else []), "--json", "baseRefName", "-q", ".baseRefName"]
    r = subprocess.run(args, cwd=root, capture_output=True, text=True, check=False, timeout=20)
    return r.stdout.strip() if r.returncode == 0 else ""


def check_bash(root: Path, event: dict, cmd: str) -> None:
    if APPLY.search(cmd):
        deny(root, event, "apply_denied", cmd[:120])
    if API_MERGE.search(cmd) or PUSH_MAIN.search(cmd):
        ask(root, event, "may_reach_main", cmd[:120])
    m = MERGE.search(cmd)
    if m:
        ref = next((t for t in m["rest"].split() if not t.startswith("-")), "")
        if ref and not re.fullmatch(r"[0-9]{1,7}|[A-Za-z0-9._/-]{1,120}", ref):
            ask(root, event, "merge_unknown_pr", cmd[:120])
        if pr_base(root, ref) not in ("", "main") and "--admin" not in cmd:
            return  # merge into a feature branch: autonomous by design (SR-031 as amended)
        ask(root, event, "merge_into_main", cmd[:120])
    if TRACE_THREAT_IN_CMD.search(cmd) and WRITE_OPS.search(cmd) and "write_artifact.py" not in cmd:
        deny(root, event, "trace_threat", cmd[:120])
    if PROTECTED_IN_CMD.search(cmd) and WRITE_OPS.search(cmd):
        ask(root, event, "protected_path_bash", cmd[:120])


def main() -> None:
    event = json.load(sys.stdin)
    if not isinstance(event, dict) or not isinstance(event.get("tool_input"), dict):
        print("Blocked (malformed): hook input", file=sys.stderr)
        sys.exit(2)
    root = root_dir(event)
    if event.get("permission_mode") == "bypassPermissions":
        deny(root, event, "bypass_mode", "the stage loop never runs in bypass mode")
    if event.get("agent_type") and not event.get("agent_id"):
        deny(root, event, "agent_contract", "agent_type without agent_id")
    subagent = bool(event.get("agent_id"))
    tool, ti = event.get("tool_name"), event["tool_input"]
    if tool == "Bash":
        if subagent:
            deny(root, event, "subagent_no_shell", str(event.get("agent_type")))
        check_bash(root, event, str(ti.get("command", "")))
        return
    path = ti.get("file_path") or ti.get("notebook_path")
    if not isinstance(path, str) or not path:
        deny(root, event, "malformed", "no file path")
    rel = os.path.relpath(os.path.realpath(os.path.join(root, path)), root)
    check_file(root, event, rel, subagent)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail closed
        print(f"Blocked: hook error ({e.__class__.__name__})", file=sys.stderr)
        sys.exit(2)
