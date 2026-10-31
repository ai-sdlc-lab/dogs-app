"""One call per step of the SDLC workflow, so the session makes few tool calls (2026-11-01).

Each subcommand runs a fixed sequence of the existing scripts and prints one short JSON result. The
session's history is re-read on every tool call, so fewer calls is the main saving. Merges only into
the change's feature branch, never into main.

  start  --change NNNN --slug S --stage STAGE              pre-flight, stage log, branches
  review --change NNNN --stage STAGE --round N R=FILE ...   validate reviewer outputs, gate (state in .stage-tmp/)
  report --change NNNN --stage STAGE                        one report per reviewer (deferred -> GitHub issue)
  ship   --change NNNN --stage STAGE --title T              commit, push, PR into the feature branch, CI, merge
  final  --change NNNN --title T                            final PR into main (never merged here)

Run as `.venv/bin/python3 -I -B scripts/stage_step.py ...`.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPSEC = ROOT / ".appsec-baseline"
TMP = ROOT / ".stage-tmp"
sys.path.insert(0, str(APPSEC / "stage"))
from common import STAGE_PREFIX, is_doc, load_yaml, sha256_file  # noqa: E402

PRODUCES = {("spec", "security-requirements-auditor"): "TRACE", ("spec", "security-architect"): "THREAT"}
CHANGE = re.compile(r"^[0-9]{4}$")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,4}$")
CI_WAIT = 540  # seconds; under the 10-minute tool limit. "pending" means: run ship again.


def run(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def py(script: str, *args: str) -> subprocess.CompletedProcess:
    return run(sys.executable, "-I", "-B", script, *args)


def out(result: dict) -> int:
    print(json.dumps(result, indent=1))
    return 0 if result.get("ok") else 1


def folder(change: str) -> Path:
    hits = sorted((ROOT / "docs" / "specs").glob(f"{change}-*"))
    if not hits:
        raise SystemExit(f"no folder docs/specs/{change}-*")
    return hits[0]


def feature(change: str, slug: str | None = None) -> str:
    return f"feature/{change}-{slug or folder(change).name[5:]}"


def model_of(reviewer: str) -> str:
    for p in (ROOT / ".claude/agents" / f"{reviewer}.md", APPSEC / "agents" / f"{reviewer}.md"):
        if p.is_file():
            m = re.search(r"^model:\s*(\S+)\s*$", p.read_text(), re.M)
            if m:
                return m.group(1)
    raise SystemExit(f"no agent file with a model for {reviewer}")


def state_path(change: str, stage: str) -> Path:
    return TMP / f"{change}-{stage}-state.json"


def load_state(change: str, stage: str) -> dict:
    p = state_path(change, stage)
    return json.loads(p.read_text()) if p.is_file() else {}


# --- start ---------------------------------------------------------------------------------------


def start(a) -> int:
    errs = []
    for script, args in (("scripts/appsec_checkout.py", ()), ("scripts/preflight.py", ("--slug", a.slug, "--change", a.change))):
        r = py(script, *args)
        if r.returncode:
            errs.append(f"{script}: {(r.stderr or r.stdout).strip()[-600:]}")
    if errs:
        return out({"ok": False, "errors": errs})
    py("scripts/stage_log.py", "stage.start", "success", f"change={a.change}", f"stage={a.stage}")
    feat, stage_branch = feature(a.change, a.slug), f"stage/{a.change}-{a.stage}"
    if a.stage == "intent" and run("git", "rev-parse", "--verify", "--quiet", feat).returncode:
        steps = [("git", "checkout", "main"), ("git", "pull", "--ff-only"), ("git", "checkout", "-b", feat)]
    else:
        steps = [("git", "checkout", feat), ("git", "pull", "--ff-only")]
    steps.append(("git", "checkout", "-B", stage_branch))
    for s in steps:
        r = run(*s)
        if r.returncode:
            return out({"ok": False, "errors": [f"{' '.join(s)}: {r.stderr.strip()[-300:]}"]})
    return out({"ok": True, "feature": feat, "branch": stage_branch})


# --- review --------------------------------------------------------------------------------------


def review(a) -> int:
    pairs = [x.partition("=")[::2] for x in a.outputs]
    errs, redactions = [], 0
    for name, path in pairs:
        r = py(".appsec-baseline/stage/validate.py", "output", path)
        last = (r.stdout.strip().splitlines() or ["0"])[-1]
        redactions += int(last) if last.isdigit() else 0
        if r.returncode:
            errs.append(f"{name}: {r.stderr.strip()[-400:]}")
    gate_args = ["--repo", "dogs-app", "--exceptions", "security/exceptions.yml", "--redactions", str(redactions)]
    for name, path in pairs:
        gate_args += ["--reviewer", f"{name}={path}"]
    r = py(".appsec-baseline/gate/security_gate.py", *gate_args)
    try:
        g = json.loads(r.stdout)
    except ValueError:
        return out({"ok": False, "errors": errs + [f"gate output unreadable: {r.stderr.strip()[-300:]}"]})
    state = load_state(a.change, a.stage)
    for name, path in pairs:
        state[name] = {
            "round": a.round,
            "output": path,
            "statuses": {k.split("/", 1)[1]: v for k, v in g["statuses"].items() if k.startswith(name + "/")},
        }
    TMP.mkdir(exist_ok=True)
    state_path(a.change, a.stage).write_text(json.dumps(state, indent=1))
    to_fix, deferred = [], []
    for name, path in pairs:
        try:
            doc = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        for f in doc.get("findings", []):
            st = state[name]["statuses"].get(f["id"], {}).get("status")
            item = {"reviewer": name, "id": f["id"], "severity": f["severity"], "sr": f["sr_ref"], "file": f["file"],
                    "line": f["line"], "status": st, "recommendation": str(f.get("recommendation", ""))[:300]}
            (deferred if st == "deferred" else to_fix if st in ("escalate", "block", "questions") else []).append(item)
    return out({"ok": g["decision"] == "allow" and not errs, "decision": g["decision"], "errors": errs,
                "to_fix": to_fix, "deferred": deferred,
                "other": [x for x in g["escalate"] if not any(x.startswith(n + " ") for n, _ in pairs)][:10]})


# --- report --------------------------------------------------------------------------------------


def report_findings(doc: dict, statuses: dict) -> tuple[list[dict], list[str]]:
    """Report findings from a reviewer's last output and the gate's statuses. Pure; issues added later."""
    keep, errs = [], []
    for f in doc.get("findings", []):
        st = statuses.get(f["id"], {})
        status = st.get("status")
        if status in ("escalate", "block", "questions"):
            if f["severity"] in ("high", "critical"):
                status = "open"
            else:
                errs.append(f"{f['id']} [{f['severity']}] is still to fix: fix it or add an exception, then review again")
                continue
        r = {k: f[k] for k in ("id", "severity", "sr_ref", "file", "line", "evidence")} | {"status": status}
        for k in ("blocking", "needs_human", "pre_existing"):
            if k in f:
                r[k] = f[k]
        if st.get("exception"):
            r["exception"] = st["exception"]
        keep.append(r)
    return keep, errs


def code_scope(change: str, regex: str) -> list[str]:
    paths = run("git", "diff", "--name-only", f"{feature(change)}...HEAD").stdout.split()
    paths += run("git", "diff", "--name-only", "HEAD").stdout.split() + run("git", "ls-files", "--others", "--exclude-standard").stdout.split()
    return sorted({p for p in paths if not is_doc(p) and re.match(regex, p) and (ROOT / p).is_file()})


def issue_for(f: dict, change: str, reviewer: str) -> int | None:
    title = f"security-finding: {f['sr_ref']} "
    r = run("gh", "issue", "list", "--state", "open", "--search", f"{title.strip()} in:title", "--json", "number,title")
    for i in json.loads(r.stdout or "[]"):
        if i["title"].startswith(title):
            return i["number"]
    TMP.mkdir(exist_ok=True)
    body = TMP / f"issue-{f['id']}.md"
    body.write_text(
        f"Old debt found by `{reviewer}` in change {change} (finding {f['id']}, severity **{f['severity']}**), in existing "
        f"code the change didn't alter, so it was deferred instead of blocking.\n\n- **Requirement:** {f['sr_ref']}\n"
        f"- **Evidence:** {f['evidence']}\n- **Where recorded:** `{f['file']}` line {f['line']}\n"
    )
    r = run("gh", "issue", "create", "--title", title + re.sub(r"\s+", " ", f["evidence"])[:70], "--body-file", str(body))
    m = re.search(r"/issues/([0-9]+)", r.stdout)
    return int(m.group(1)) if m else None


def report(a) -> int:
    state = load_state(a.change, a.stage)
    if not state:
        return out({"ok": False, "errors": ["no review state: run review first"]})
    ch, lock = folder(a.change), (ROOT / "appsec-baseline.lock").read_text().strip()
    rel = ch.relative_to(ROOT).as_posix()
    conditional = load_yaml(ROOT / "stages.yml")["stages"]["code"].get("conditional", {})
    written, errs = [], []
    for rev, s in state.items():
        doc = json.loads(Path(s["output"]).read_text())
        findings, e = report_findings(doc, s["statuses"])
        errs += [f"{rev} {x}" for x in e]
        for f in findings:
            if f["status"] == "deferred":
                f["issue"] = issue_for(f, a.change, rev)
                if not f["issue"]:
                    errs.append(f"{rev} {f['id']}: could not find or open its GitHub issue")
        if a.stage == "code":
            scope = code_scope(a.change, conditional.get(rev, r"^"))
        else:
            scope = [f"{rel}/{STAGE_PREFIX[a.stage]}-{a.change}.md"]
        produced = {}
        if (a.stage, rev) in PRODUCES:
            p = f"{rel}/{PRODUCES[(a.stage, rev)]}-{a.change}.md"
            produced[p] = sha256_file(ROOT / p)
        doc = {"reviewer": rev, "stage": a.stage, "change": a.change, "model": model_of(rev), "round": s["round"],
               "appsec_sha": lock, "files": {p: sha256_file(ROOT / p) for p in scope}, "produced": produced,
               "verdict": "open" if any(f["status"] == "open" for f in findings) else "allow", "findings": findings}
        path = ch / "reviews" / f"{STAGE_PREFIX[a.stage]}-{a.change}.{rev}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(doc, indent=1) + "\n")
        r = py(".appsec-baseline/stage/validate.py", "report", str(path))
        if r.returncode:
            errs.append(f"{path.name}: {r.stderr.strip()[-300:]}")
        written.append(path.relative_to(ROOT).as_posix())
    return out({"ok": not errs, "written": written, "errors": errs,
                "open": [f"{p}" for p in written if json.loads((ROOT / p).read_text())["verdict"] == "open"]})


# --- ship / final --------------------------------------------------------------------------------


def base_ok(base: str, change: str) -> bool:
    """Stage PRs go only into the change's feature branch; never main."""
    return base.startswith(f"feature/{change}-") and base != "main"


def checks(pr: str) -> list[dict]:
    r = run("gh", "pr", "checks", pr, "--json", "name,bucket,link")
    return json.loads(r.stdout or "[]")


def ship(a) -> int:
    feat, branch = feature(a.change), f"stage/{a.change}-{a.stage}"
    if run("git", "branch", "--show-current").stdout.strip() != branch:
        return out({"ok": False, "errors": [f"not on {branch}"]})
    run("git", "add", "-A")
    if run("git", "diff", "--cached", "--quiet").returncode:
        r = run("git", "commit", "-m", a.title)
        if r.returncode:
            return out({"ok": False, "errors": [r.stderr.strip()[-300:]]})
    r = run("git", "push", "-u", "origin", branch)
    if r.returncode:
        return out({"ok": False, "errors": [r.stderr.strip()[-300:]]})
    pr = run("gh", "pr", "view", branch, "--json", "number,baseRefName")
    if pr.returncode:
        r = run("gh", "pr", "create", "--base", feat, "--head", branch, "--title", a.title,
                "--body", f"Stage {a.stage} of change {a.change}.")
        if r.returncode:
            return out({"ok": False, "errors": [r.stderr.strip()[-300:]]})
        pr = run("gh", "pr", "view", branch, "--json", "number,baseRefName")
    info = json.loads(pr.stdout)
    if not base_ok(info["baseRefName"], a.change):
        return out({"ok": False, "errors": [f"PR base is {info['baseRefName']}: stage PRs go only into {feat}"]})
    num, deadline = str(info["number"]), time.time() + CI_WAIT
    time.sleep(20)  # let the checks register
    while True:
        cs = checks(num)
        if cs and not any(c["bucket"] == "pending" for c in cs):
            break
        if time.time() > deadline:
            return out({"ok": False, "pr": num, "pending": True, "errors": ["CI still running: run ship again"]})
        time.sleep(20)
    failed = [c for c in cs if c["bucket"] == "fail"]
    if failed and not a.merge_red:
        logs = []
        for c in failed[:3]:
            m = re.search(r"/runs/([0-9]+)", c.get("link", ""))
            if m:
                lines = run("gh", "run", "view", m.group(1), "--log-failed").stdout.splitlines()
                logs.append({c["name"]: [x[-200:] for x in lines if re.search(r"FAIL|Error|error|assert", x)][-15:]})
        return out({"ok": False, "pr": num, "failed": [c["name"] for c in failed], "logs": logs})
    r = run("gh", "pr", "merge", num, "--merge", "--delete-branch")
    if r.returncode:
        return out({"ok": False, "pr": num, "errors": [r.stderr.strip()[-300:]]})
    run("git", "checkout", feat)
    run("git", "pull", "--ff-only")
    py("scripts/stage_log.py", "pr.merged", "success", f"change={a.change}", f"stage={a.stage}")
    return out({"ok": True, "pr": num, "merged_into": feat, "merged_red": [c["name"] for c in failed]})


def final(a) -> int:
    feat = feature(a.change)
    for s in (("git", "checkout", feat), ("git", "pull", "--ff-only")):
        r = run(*s)
        if r.returncode:
            return out({"ok": False, "errors": [r.stderr.strip()[-300:]]})
    body = py("scripts/final_pr_body.py", "main")
    if body.returncode:
        return out({"ok": False, "errors": [body.stderr.strip()[-300:]]})
    TMP.mkdir(exist_ok=True)
    (TMP / "body.md").write_text(body.stdout)
    r = run("gh", "pr", "create", "--base", "main", "--head", feat, "--title", a.title, "--body-file", str(TMP / "body.md"))
    return out({"ok": r.returncode == 0, "pr": r.stdout.strip(), "errors": [r.stderr.strip()[-300:]] if r.returncode else []})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("start", "review", "report", "ship", "final"):
        s = sub.add_parser(name)
        s.add_argument("--change", required=True)
        if name != "final":
            s.add_argument("--stage", required=True, choices=list(STAGE_PREFIX))
    sub.choices["start"].add_argument("--slug", required=True)
    sub.choices["review"].add_argument("--round", type=int, required=True, choices=[1, 2, 3])
    sub.choices["review"].add_argument("outputs", nargs="+", metavar="REVIEWER=FILE")
    for name in ("ship", "final"):
        sub.choices[name].add_argument("--title", required=True)
    sub.choices["ship"].add_argument("--merge-red", action="store_true", help="after the last fix round: merge anyway")
    a = p.parse_args(argv)
    if not CHANGE.match(a.change) or (getattr(a, "slug", None) and not SLUG.match(a.slug)):
        return out({"ok": False, "errors": ["bad change number or slug"]})
    return {"start": start, "review": review, "report": report, "ship": ship, "final": final}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
