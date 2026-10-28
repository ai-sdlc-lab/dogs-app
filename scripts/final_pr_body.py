"""Body for the final PR (feature branch -> main): what the owner must look at (SPEC-0001 M-19, M-23).

Lists every changed path under protected areas, changes to the verifier pin or the security-gate job,
and every exception a review report used. The owner also checks `git diff --stat` on the same paths,
because this script is introduced by the same PR in change 0001.

Usage: python3 -I -B scripts/final_pr_body.py BASE_REF
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTECTED = (".claude/", ".github/", "CODEOWNERS", "CLAUDE.md", "REVIEW.md", "stages.yml", "appsec-baseline.lock", "scripts/")


def changed(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", "-z", f"{base}...HEAD"], capture_output=True, check=True
    ).stdout
    return [p.decode() for p in out.split(b"\0") if p]


def body(paths: list[str], root: Path = ROOT, diff_text: str = "") -> str:
    prot = [p for p in paths if p.startswith(PROTECTED) or p in PROTECTED]
    lines = ["## Owner review: protected changes", ""]
    lines += [f"- `{p}`" for p in prot] or ["- none"]
    if "verify.yml@" in diff_text:
        lines += ["", "**The verifier pin (`verify.yml@<sha>`) changes in this PR.**"]
    if "security-gate" in diff_text:
        lines += ["", "**The `security-gate` job changes in this PR.**"]
    used = []
    for p in paths:
        if "/reviews/" in p and p.endswith(".json") and (root / p).is_file():
            try:
                doc = json.loads((root / p).read_text())
            except ValueError:
                continue
            used += [f"{f['exception']}: {doc['reviewer']} {f['id']} ({f['sr_ref']})" for f in doc.get("findings", []) if f.get("exception")]
    lines += ["", "## Exceptions used", ""] + ([f"- {u}" for u in sorted(set(used))] or ["- none"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    base = sys.argv[1]
    diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", f"{base}...HEAD", "--", ".github/workflows/security.yml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    print(body(changed(base), diff_text=diff))
