"""Sandbox probe (lab-admin #23): run it from a Claude Code session in this repo, through the Bash tool.

Usage: .venv/bin/python3 -I -B scripts/sandbox_probe.py
Must fail: write to home, read credentials or another repo, reach a host off the allowlist, run docker.
Must work: what the stage loop needs (git over HTTPS, gh, make, the stage scripts, writes in the repo).
Exit 0 only if every line is as expected. Outside the sandbox the "must fail" lines fail the probe.
"""

import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()


def ok(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=300).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def reads(p: Path) -> bool:
    try:
        if p.is_dir():
            return any(True for _ in p.iterdir())  # listing is enough
        p.read_bytes()
        return True
    except OSError:
        return False


def writes(p: Path) -> bool:
    try:
        p.write_text("probe")
        p.unlink()
        return True
    except OSError:
        return False


def reaches(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=10)  # noqa: S310 (fixed https URLs)
        return True
    except Exception:
        return False


blocked = {
    "write ~/sandbox-probe": lambda: writes(HOME / "sandbox-probe"),
    "read ~/.aws": lambda: reads(HOME / ".aws"),
    "read ~/.ssh": lambda: reads(HOME / ".ssh"),
    "read ~/.zsh_history": lambda: reads(HOME / ".zsh_history"),
    "read ~/Documents": lambda: reads(HOME / "Documents"),
    "read another repo (..)": lambda: any(reads(p) for p in ROOT.parent.iterdir() if p != ROOT),
    "reach https://example.com": lambda: reaches("https://example.com"),
    "run docker": lambda: ok(["docker", "ps"]),
}
allowed = {
    "write .stage-tmp/": lambda: (ROOT / ".stage-tmp").mkdir(exist_ok=True) or writes(ROOT / ".stage-tmp/probe"),
    "git ls-remote origin (HTTPS)": lambda: ok(["git", "ls-remote", "--heads", "origin", "main"]),
    "gh pr list": lambda: ok(["gh", "pr", "list", "--limit", "1"]),
    "gh run list": lambda: ok(["gh", "run", "list", "--limit", "1"]),
    "reach pypi.org": lambda: reaches("https://pypi.org/simple/pip/"),
    "preflight.py": lambda: ok([sys.executable, "-I", "-B", "scripts/preflight.py"]),
    "git push --dry-run (HTTPS auth)": lambda: ok(["git", "push", "--dry-run", "origin", "HEAD:refs/heads/probe/sandbox"]),
    "ruff check api": lambda: ok(["ruff", "check", "api"]),
    "make test-process": lambda: ok(["make", "test-process"]),
}

bad = 0
for name, f in blocked.items():
    hit = f()
    bad += hit
    print(f"{'FAIL' if hit else 'ok  '} blocked: {name}")
for name, f in allowed.items():
    hit = f()
    bad += not hit
    print(f"{'ok  ' if hit else 'FAIL'} works:   {name}")
sys.exit(1 if bad else 0)
