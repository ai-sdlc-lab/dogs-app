"""The local appsec-baseline checkout is exactly the locked commit, with nothing extra (SPEC-0001 M-09, M-22).

Lives in dogs-app (owner-protected), not in the tree it checks. Run as `python3 -I -B scripts/lock_check.py`.
Exit 0 ok, 1 mismatch (reason on stderr).
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT / ".appsec-baseline"
LOCK = re.compile(r"^[0-9a-f]{40}$")


def read_lock(root: Path = ROOT) -> str:
    lock = (root / "appsec-baseline.lock").read_text().strip()
    if not LOCK.match(lock):
        raise ValueError("appsec-baseline.lock is not a 40-hex commit SHA")
    return lock


def problems(checkout: Path = CHECKOUT, lock: str | None = None) -> list[str]:
    lock = lock or read_lock()
    if not (checkout / ".git").exists():
        return [f"{checkout} is not a git checkout (run scripts/appsec_checkout.py)"]

    def git(*args):
        return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, check=False)

    head = git("rev-parse", "HEAD").stdout.strip()
    out = []
    if head != lock:
        out.append(f"checkout is at {head[:12]}, lock is {lock[:12]}")
    dirty = git("status", "--porcelain", "--ignored").stdout.strip()
    if dirty:
        out.append("checkout has modified, untracked or ignored files: " + dirty.splitlines()[0][:80])
    return out


if __name__ == "__main__":
    try:
        errs = problems()
    except (OSError, ValueError) as e:
        errs = [str(e)]
    for e in errs:
        print(f"lock check: {e}", file=sys.stderr)
    sys.exit(1 if errs else 0)
