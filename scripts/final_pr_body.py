"""Body for the final PR (feature branch -> main): what the owner must look at (SPEC-0001 M-19, M-23).

First what the owner decides at this merge: open high/critical findings, exceptions the agents added to
security/exceptions.yml, and the session's decisions (docs/specs/<NNNN>-<slug>/decisions.md). Then every changed path the owner reviews (CODEOWNERS entries plus Makefile, tests/process/, scanner
configs), renames as delete + add, changes to the verifier pin or the stage-gate job, and every
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
EXTRA = [".claude/*", ".github/*", "CLAUDE.md", "REVIEW.md", "stages.yml", "appsec-baseline.lock", "scripts/*", "Makefile", "tests/process/*", ".mcp.json", ".envrc", ".vscode/*", ".git/*"]  # plus CODEOWNERS
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


EXCEPTIONS = "security/exceptions.yml"


def exception_ids(text: str) -> set[str]:
    return set(re.findall(r"^- id: (EXC-[0-9]{3})\s*$", text, re.M))


def decide_first(paths: list[str], root: Path, base_exceptions: str) -> list[str]:
    open_items = []
    for p in paths:
        if "/reviews/" in p and p.endswith(".json") and (root / p).is_file():
            try:
                doc = json.loads((root / p).read_text())
                open_items += [
                    f"{inert(doc.get('reviewer'))} {inert(f.get('id'))} [{inert(f.get('severity'))}] {inert(f.get('sr_ref'))} "
                    f"{inert(f.get('file'))}: {inert(f.get('evidence', ''))}"
                    for f in doc.get("findings", [])
                    if f.get("status") == "open"
                ]
            except (ValueError, AttributeError, TypeError):
                open_items.append(f"malformed report: {inert(p)}")
    lines = ["## Decide at this merge", "", "**Open findings (high/critical, not fixed in 3 rounds)**", ""]
    lines += [f"- {x}" for x in open_items] or ["- none"]
    ex = root / EXCEPTIONS
    new = sorted(exception_ids(ex.read_text()) - exception_ids(base_exceptions)) if ex.is_file() else []
    lines += ["", f"**Exceptions added in this PR (`{EXCEPTIONS}`)**", ""]
    if new:
        blocks = ex.read_text().split("\n- ")
        for b in blocks:
            if any(re.match(rf"(- )?id: {i}\s", b) for i in new):
                lines += [f"- {inert(' '.join(b.split()))}"]
    else:
        lines += ["- none"]
    lines += ["", "**Decisions the session took without asking**", ""]
    dec = [p for p in paths if re.fullmatch(r"docs/specs/[0-9]{4}-[a-z0-9-]+/decisions\.md", p) and (root / p).is_file()]
    for p in dec:
        lines += [f"- {inert(x.strip())}" for x in (root / p).read_text().splitlines()[:100] if x.strip() and not x.startswith("#")]
    if not dec:
        lines += ["- none recorded"]
    return lines + [""]


def body(paths: list[str], root: Path = ROOT, diff_text: str = "", base_exceptions: str = "") -> str:
    pats = protected_patterns(root)
    prot = [p for p in paths if is_protected(p, pats)]
    lines = decide_first(paths, root, base_exceptions) + ["## Owner review: protected changes", ""]
    lines += [f"- `{inert(p)}`" for p in prot] or ["- none"]
    if "verify.yml@" in diff_text:
        lines += ["", "**A verifier pin (`verify.yml@<sha>`) changes in this PR.**"]
    if "stage-gate" in diff_text:
        lines += ["", "**The `stage-gate` job changes in this PR.**"]
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
    old = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{base}:{EXCEPTIONS}"], capture_output=True, text=True, check=False
    ).stdout
    print(body(changed(base), diff_text=diff, base_exceptions=old))
