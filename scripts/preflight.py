"""Checks before every stage (SPEC-0001 §1.1, M-04, M-09, M-15, M-21, M-27). Fail closed.

Usage: python3 -I -B scripts/preflight.py [--slug SLUG] [--change NNNN]
Exit 0 ok, 1 refuse (each reason on stderr).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lock_check import problems

REQUIRED_ASK = ["Edit(/.claude/**)", "Edit(/CLAUDE.md)", "Edit(/stages.yml)", "Edit(/appsec-baseline.lock)", "Edit(/.appsec-baseline/**)", "Edit(/.git/**)", "Edit(/.mcp.json)"]
REQUIRED_DENY = ["Bash(make apply*)", "Bash(terraform apply*)", "Bash(aws *)", "Read(~/.aws/**)", "Read(~/.config/gh/**)", "Read(**/*.tfstate*)", "Edit(/docs/specs/**/THREAT-*.md)", "Edit(/docs/specs/**/TRACE-*.md)"]
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CHANGE = re.compile(r"^[0-9]{4}$")
LOGGED_OUT = re.compile(r"(?i)(expired|unable to locate credentials|could not be found|login|not authori[sz]ed|invalidclienttokenid|no credentials|sso)")
AWS_ENV = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE")


def slug_ok(slug: str) -> bool:
    return bool(SLUG.match(slug)) and 3 <= len(slug) <= 40 and slug.count("-") <= 4


def aws_problems(env=None, run=subprocess.run) -> list[str]:
    env = os.environ if env is None else env
    out = [f"{k} is set in the session environment" for k in AWS_ENV if env.get(k)]
    try:
        r = run(
            ["aws", "sts", "get-caller-identity", "--profile", "sdlc-lab-admin"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if r.returncode == 0:
            out.append("the sdlc-lab-admin AWS session is active: run `aws logout --profile sdlc-lab-admin`")
        elif not LOGGED_OUT.search(f"{r.stdout or ''} {r.stderr or ''}"):
            out.append("could not confirm the AWS session is logged out (unexpected aws error)")
    except FileNotFoundError:
        pass  # no AWS CLI, no AWS session
    except subprocess.TimeoutExpired:
        out.append("could not confirm the AWS session is logged out (timeout)")
    return out


def settings_problems(root: Path = ROOT) -> list[str]:
    try:
        s = json.loads((root / ".claude/settings.json").read_text())
    except (OSError, ValueError) as e:
        return [f".claude/settings.json unreadable: {e.__class__.__name__}"]
    out = []
    perms = s.get("permissions", {})
    if perms.get("disableBypassPermissionsMode") != "disable":
        out.append("bypass permission mode is not disabled in .claude/settings.json")
    pre = s.get("hooks", {}).get("PreToolUse", [])
    matchers = {m for h in pre for m in str(h.get("matcher", "")).split("|") if "protect-paths.py" in json.dumps(h)}
    if not {"Edit", "Write", "NotebookEdit", "Bash"} <= matchers:
        out.append("the protect-paths hook must match Edit, Write, NotebookEdit and Bash")
    for rule in REQUIRED_ASK:
        if rule not in perms.get("ask", []):
            out.append(f"missing ask rule {rule}")
    for rule in REQUIRED_DENY:
        if rule not in perms.get("deny", []):
            out.append(f"missing deny rule {rule}")
    return out


def hook_self_test(root: Path = ROOT, py: str = sys.executable) -> list[str]:
    """M-21: the hook must ask for a protected edit in default mode, deny it in auto mode, deny a subagent shell."""
    hook = root / ".claude/hooks/protect-paths.py"
    cases = [
        ({"tool_name": "Edit", "tool_input": {"file_path": "stages.yml"}, "permission_mode": "default"}, 0, '"ask"'),
        ({"tool_name": "Edit", "tool_input": {"file_path": "stages.yml"}, "permission_mode": "auto"}, 2, ""),
        ({"tool_name": "Bash", "tool_input": {"command": "ls"}, "agent_id": "x", "agent_type": "author"}, 2, ""),
    ]
    out = []
    for event, code, needle in cases:
        event = {"cwd": str(root), "session_id": "preflight", **event}
        r = subprocess.run(
            [py, "-I", "-B", str(hook)], input=json.dumps(event), text=True, capture_output=True, check=False,
            env={"CLAUDE_PROJECT_DIR": str(root), "PATH": os.environ.get("PATH", "")}, timeout=30,
        )
        if r.returncode != code or needle not in r.stdout:
            out.append(f"hook self-test failed for {event['tool_name']} in {event.get('permission_mode', 'subagent')} mode")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--slug")
    p.add_argument("--change")
    a = p.parse_args(argv)
    errs = []
    if a.slug is not None and not slug_ok(a.slug):
        errs.append(f"unsafe slug {a.slug[:60]!r}: lowercase words joined by '-', 3-40 characters, at most 5 words")
    if a.change is not None and not CHANGE.match(a.change):
        errs.append("change number must be 4 digits")
    errs += problems()
    errs += aws_problems()
    errs += settings_problems()
    errs += hook_self_test()
    for e in errs:
        print(f"preflight: {e}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
