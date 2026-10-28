"""Body for the final PR (feature branch -> main): what the owner must look at (SPEC-0001 M-19, M-23).

Lists every changed path the owner reviews (CODEOWNERS entries plus Makefile, tests/process/, scanner
configs), renames as delete + add, changes to the verifier pin or the security-gate job, and every
exception a review report used. The owner also checks `git diff --stat` on the same paths, because this
script is introduced by the same PR in change 0001.

Usage: python3 -I -B scripts/final_pr_body.py BASE_REF
"""

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRA = [".claude/*", ".github/*", "CLAUDE.md", "REVIEW.md", "stages.yml", "appsec-baseline.lock", "scripts/*", "Makefile", "tests/process/*"]  # plus CODEOWNERS
SCANNER_CONFIGS = [".gitleaks.toml", ".gitleaksignore", ".semgrepignore", "osv-scanner.toml", "trivy.yaml", "trivy.yml", ".trivyignore", ".trivyignore.yaml"]
REF = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_UNSAFE = re.compile(r"[`\x00-\x1f\x7f@<>\[\]]")


def inert(s) -> str:
    return _UNSAFE.sub("_", str(s))[:200]


def protected_patterns(root: Path = ROOT) -> list[str]:
    pats = list(EXTRA)
    try:
        for line in (root / ".github" / "CODEOWNERS").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                p = line.split()[0].lstrip("/")
                pats.append(p + "*" if p.endswith("/") else p)
    except OSError:
        pass
    return pats


def is_protected(path: str, pats: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in SCANNER_CONFIGS:
        return True
    return any(fnmatch.fnmatch(path, p.replace("**/", "*")) for p in pats)


def changed(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", "--no-renames", "-z", "--end-of-options", f"{base}...HEAD"],
        capture_output=True,
        check=True,
    ).stdout
    return [p.decode("utf-8", "replace") for p in out.split(b"\0") if p]


def body(paths: list[str], root: Path = ROOT, diff_text: str = "") -> str:
    pats = protected_patterns(root)
    prot = [p for p in paths if is_protected(p, pats)]
    lines = ["## Owner review: protected changes", ""]
    lines += [f"- `{inert(p)}`" for p in prot] or ["- none"]
    if "verify.yml@" in diff_text:
        lines += ["", "**A verifier pin (`verify.yml@<sha>`) changes in this PR.**"]
    if "security-gate" in diff_text:
        lines += ["", "**The `security-gate` job changes in this PR.**"]
    used = []
    for p in paths:
        if "/reviews/" in p and p.endswith(".json") and (root / p).is_file():
            try:
                doc = json.loads((root / p).read_text())
                for f in doc.get("findings", []):
                    if f.get("exception"):
                        used.append(f"{inert(f.get('exception'))}: {inert(doc.get('reviewer'))} {inert(f.get('id'))} ({inert(f.get('sr_ref'))})")
            except (ValueError, AttributeError, TypeError):
                used.append(f"malformed report: {inert(p)}")
    lines += ["", "## Exceptions used", ""] + ([f"- {u}" for u in sorted(set(used))] or ["- none"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2 or not REF.match(sys.argv[1]) or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    base = sys.argv[1]
    diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--end-of-options", f"{base}...HEAD", "--", ".github/"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    print(body(changed(base), diff_text=diff))
