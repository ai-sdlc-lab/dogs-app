"""Check out appsec-baseline at the locked commit into .appsec-baseline/ (git-ignored), then verify it.

The stage loop loads its security agents (`claude --plugin-dir .appsec-baseline`) and runs its
scripts only from this checkout (SPEC-0001 M-09). Run as `python3 -I -B scripts/appsec_checkout.py`.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lock_check import CHECKOUT, problems, read_lock

REMOTE = "https://github.com/ai-sdlc-lab/appsec-baseline.git"


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True)


def main() -> int:
    lock = read_lock()
    if not (CHECKOUT / ".git").exists():
        git("clone", "--quiet", "--no-checkout", REMOTE, str(CHECKOUT))
    git("-C", str(CHECKOUT), "fetch", "--quiet", "origin", "main")
    git("-C", str(CHECKOUT), "checkout", "--quiet", "--detach", lock)
    git("-C", str(CHECKOUT), "clean", "-fdxq")  # drop caches so the clean check holds
    errs = problems(CHECKOUT, lock)
    for e in errs:
        print(f"appsec checkout: {e}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
