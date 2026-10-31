import json

import pytest
from conftest import hook

AUTHOR = "author"
REVIEWER = "security-architect"


def test_hook_blocks_author_other_stage_artifact_and_reviews(project):
    root = project("stage/0007-spec")
    assert hook(root, path="docs/specs/0007-demo/SPEC-0007.md", agent=AUTHOR) == "allow"
    for p in ("docs/specs/0007-demo/INT-0007.md", "docs/specs/0007-demo/PLAN-0007.md", "docs/specs/0007-demo/reviews/x.json"):
        assert hook(root, path=p, agent=AUTHOR) == "deny", p


def test_hook_blocks_author_code_file_not_in_plan(project):
    root = project("stage/0007-code")
    assert hook(root, path="api/app/main.py", agent=AUTHOR) == "allow"
    assert hook(root, path="api/tests/sub/test_a.py", agent=AUTHOR) == "allow"
    for p in ("Makefile", "infra/main.tf", "web/src/main.ts", "docs/specs/0007-demo/reviews/CODE-0007.x.json"):
        assert hook(root, path=p, agent=AUTHOR) == "deny", p


def test_hook_blocks_subagent_edit_github_and_trace_threat(project):
    root = project("stage/0007-code")
    for p in (".github/workflows/x.yml", ".claude/settings.json", "docs/specs/0007-demo/THREAT-0007.md"):
        assert hook(root, path=p, agent=AUTHOR) == "deny", p
    assert hook(root, path="api/app/main.py", agent=REVIEWER) == "deny"  # reviewers never write


def test_hook_denies_subagent_write_trace_threat(project):
    root = project("stage/0007-spec")
    for p in ("docs/specs/0007-demo/TRACE-0007.md", "docs/specs/0007-demo/THREAT-0007.md"):
        assert hook(root, path=p, agent=AUTHOR) == "deny"
        assert hook(root, path=p, agent=REVIEWER) == "deny"


def test_hook_denies_main_session_direct_trace_threat_write(project):
    root = project("stage/0007-spec")
    assert hook(root, tool="Bash", command="echo x > docs/specs/0007-demo/THREAT-0007.md") == "deny"
    assert hook(root, tool="Bash", command="python3 -I -B .appsec-baseline/stage/write_artifact.py o.json . docs/specs/0007-demo/THREAT-0007.md") != "deny"


def test_hook_denies_main_session_write_trace_threat(project):
    root = project("stage/0007-spec")
    assert hook(root, path="docs/specs/0007-demo/TRACE-0007.md") == "deny"


def test_hook_denies_main_session_github_edit_outside_code_stage(project):
    assert hook(project("stage/0007-spec"), path=".github/workflows/x.yml") == "deny"


def test_hook_allows_main_session_github_edit_on_code_stage(project):
    assert hook(project("stage/0007-code"), path=".github/workflows/x.yml") == "allow"


@pytest.mark.parametrize("p", [".claude/settings.json", "CLAUDE.md", "REVIEW.md", "stages.yml", "appsec-baseline.lock", ".appsec-baseline/x.py"])
def test_hook_asks_for_claude_dir_edit_in_main_session(project, p):
    assert hook(project(), path=p) == "ask"


def test_hook_asks_for_bash_write_to_claude_dir(project):
    root = project()
    for cmd in ("sed -i s/a/b/ .claude/settings.json", "echo {} > .claude/settings.json", "cp x stages.yml"):
        assert hook(root, tool="Bash", command=cmd) == "ask", cmd
    assert hook(root, tool="Bash", command="cat .claude/settings.json") == "allow"


@pytest.mark.parametrize(
    "cmd",
    ["gh pr merge 12 --merge", "gh pr merge --admin 3", "gh api -X PUT repos/o/r/pulls/3/merge", "git push origin HEAD:main", "git push origin main"],
)
def test_hook_asks_before_merge_into_main(project, cmd):
    # no reachable PR here, so the base can't be confirmed as a feature branch: the owner is asked
    assert hook(project(), tool="Bash", command=cmd) == "ask"


@pytest.mark.parametrize(
    "cmd",
    ["make apply", "make -C ../lab-admin apply", "terraform -chdir=infra apply", "cd infra && terraform apply -auto-approve", "make destroy", "make seed"],
)
def test_hook_asks_for_terraform_and_make_apply_variants(project, cmd):
    assert hook(project(), tool="Bash", command=cmd) in ("deny", "ask")


@pytest.mark.parametrize("raw", ["not json", "[]", '{"tool_name": "Write"}', '{"tool_name": "Write", "tool_input": {}}'])
def test_hook_fails_closed_on_malformed_input(project, raw):
    import subprocess
    import sys

    from conftest import HOOK

    root = project()
    r = subprocess.run([sys.executable, "-I", "-B", str(HOOK)], input=raw, text=True, capture_output=True, env={"CLAUDE_PROJECT_DIR": str(root)}, check=False)
    assert r.returncode == 2


def test_hook_agent_id_contract(project):
    """Payload shape per the Claude Code hooks reference: agent_id/agent_type present only inside subagents."""
    root = project("stage/0007-spec")
    main_session = hook(root, path="docs/specs/0007-demo/SPEC-0007.md")
    subagent = hook(root, path="docs/specs/0007-demo/INT-0007.md", agent=AUTHOR)
    assert main_session == "allow" and subagent == "deny"


def test_hook_denies_agent_type_without_agent_id(project):
    root = project("stage/0007-spec")
    assert hook(root, path="docs/specs/0007-demo/SPEC-0007.md", extra={"agent_type": AUTHOR}) == "deny"


def test_hook_denies_subagent_shell(project):
    assert hook(project(), tool="Bash", command="ls", agent=AUTHOR) == "deny"


def test_stage_refuses_unsafe_permission_mode(project):
    assert hook(project(), path="api/app/main.py", extra={"permission_mode": "bypassPermissions"}) == "deny"


def test_hook_logs_authz_events(project):
    root = project("stage/0007-spec")
    hook(root, path="docs/specs/0007-demo/TRACE-0007.md")
    hook(root, path="stages.yml")
    events = [json.loads(x)["event"] for x in (root / ".claude/stage-log.jsonl").read_text().splitlines()]
    assert events == ["authz.denied", "authz.ask"]


@pytest.mark.parametrize(
    "p", [".Claude/settings.json", "claude.md", "Stages.yml", ".GITHUB/workflows/x.yml", "docs/specs/0007-demo/trace-0007.md"]
)
def test_hook_case_variants_are_protected(project, p):
    assert hook(project("stage/0007-spec"), path=p) in ("ask", "deny")


@pytest.mark.parametrize("p", [".git/hooks/pre-commit", ".mcp.json", ".envrc", ".vscode/settings.json"])
def test_hook_asks_for_code_running_config(project, p):
    assert hook(project(), path=p) == "ask"


def test_hook_denies_ask_class_outside_default_mode(project):
    root = project()
    for mode in ("auto", "acceptEdits", "dontAsk"):
        assert hook(root, path="stages.yml", extra={"permission_mode": mode}) == "deny", mode
        assert hook(root, tool="Bash", command="gh pr merge 3", extra={"permission_mode": mode}) == "deny", mode


def test_hook_author_scope_comes_from_feature_branch_plan(project):
    root = project("stage/0007-code")
    plan = root / "docs/specs/0007-demo/PLAN-0007.md"
    plan.write_text(plan.read_text() + "| D-02 | `Makefile` | SR-002 | `test_y` |\n")  # edited in the working tree only
    assert hook(root, path="Makefile", agent=AUTHOR) == "deny"


def test_hook_redacts_secrets_in_prompts(project):
    import json

    root = project()
    hook(root, tool="Bash", command="GH_TOKEN=ghp_secretvalue gh pr merge 5")
    detail = json.loads((root / ".claude/stage-log.jsonl").read_text().splitlines()[-1])["detail"]
    assert "ghp_secretvalue" not in detail


def test_hook_main_session_writes_scratch_in_repo(project):
    """The skill keeps reviewer output in .stage-tmp/ (git-ignored), never outside the repo."""
    root = project()
    for mode in ("default", "acceptEdits"):
        assert hook(root, path=".stage-tmp/spec-security-requirements-auditor.json", extra={"permission_mode": mode}) == "allow"


PY = ".venv/bin/python3 -I -B"
SKILL_COMMANDS = [  # every command the stage skill runs, one per Bash call (keep in sync with SKILL.md)
    f"{PY} scripts/appsec_checkout.py",
    f"{PY} scripts/stage_step.py start --change 0007 --slug demo --stage spec",
    f"{PY} scripts/stage_step.py review --change 0007 --stage spec --round 1 security-architect=.stage-tmp/spec-security-architect.json"
    " spec-completeness=.stage-tmp/spec-spec-completeness.json",
    f"{PY} scripts/stage_step.py report --change 0007 --stage spec",
    f"{PY} scripts/stage_step.py ship --change 0007 --stage spec --title 'SPEC-0007: spec stage'",
    f"{PY} scripts/stage_step.py ship --change 0007 --stage code --title 'CODE-0007' --merge-red",
    f"{PY} scripts/stage_step.py final --change 0007 --title '0007: demo'",
    f"{PY} scripts/preflight.py --slug demo --change 0007",
    f"{PY} scripts/stage_log.py stage.start success change=0007 stage=spec",
    "git checkout -b feature/0007-demo main",
    "git checkout -b stage/0007-spec",
    "git diff --name-only feature/0007-demo...HEAD",
    "git diff feature/0007-demo...HEAD -- api/app/main.py",
    f"{PY} .appsec-baseline/stage/structure.py .claude/skills/stage/templates/SPEC.md docs/specs/0007-demo/SPEC-0007.md",
    f"{PY} .appsec-baseline/stage/validate.py output .stage-tmp/spec-security-architect.json",
    f"{PY} .appsec-baseline/gate/security_gate.py --repo dogs-app --exceptions security/exceptions.yml"
    " --reviewer security-architect=.stage-tmp/spec-security-architect.json",
    f"{PY} .appsec-baseline/stage/write_artifact.py .stage-tmp/spec-security-architect.json . docs/specs/0007-demo/THREAT-0007.md",
    f"{PY} .appsec-baseline/stage/hash.py docs/specs/0007-demo/SPEC-0007.md",
    f"{PY} .appsec-baseline/stage/crosscheck.py docs/specs/0007-demo/TRACE-0007.md docs/specs/0007-demo/THREAT-0007.md"
    " docs/specs/0007-demo/PLAN-0007.md",
    f"{PY} .appsec-baseline/stage/validate.py report docs/specs/0007-demo/reviews/SPEC-0007.security-architect.json",
    "make test",
    "git add -A",
    "git commit -m 'SPEC-0007: spec stage'",
    "git push -u origin stage/0007-spec",
    "git merge main",
    "gh pr create --base feature/0007-demo --title 'SPEC-0007' --body 'spec stage'",
    "gh pr checks --watch",
    "gh run view 123 --log-failed",
    'gh issue list --state open --search "security-finding: SR-005 in:title"',
    'gh issue create --title "security-finding: SR-005 error body format" --body-file .stage-tmp/issue-AUD-002.md',
    f"{PY} scripts/final_pr_body.py main > .stage-tmp/body.md",
    "gh pr create --base main --head feature/0007-demo --body-file .stage-tmp/body.md",
]
SESSION_WRITES = [
    ".stage-tmp/spec-security-architect.json",
    ".stage-tmp/issue-AUD-002.md",
    "security/exceptions.yml",
    "docs/specs/0007-demo/decisions.md",
    "docs/specs/0007-demo/reviews/SPEC-0007.security-architect.json",
]


@pytest.mark.parametrize("cmd", SKILL_COMMANDS)
def test_hook_allows_every_skill_command_in_accept_edits(project, cmd):
    """Dry run of the stage skill (2026-10-30): no command it uses may be blocked after the intent stage."""
    assert hook(project("stage/0007-spec"), tool="Bash", command=cmd, extra={"permission_mode": "acceptEdits"}) == "allow"


@pytest.mark.parametrize("path", SESSION_WRITES)
def test_hook_allows_every_session_write_in_accept_edits(project, path):
    assert hook(project("stage/0007-spec"), path=path, extra={"permission_mode": "acceptEdits"}) == "allow"


def test_hook_allows_author_stage_file_in_accept_edits(project):
    root = project("stage/0007-spec")
    assert hook(root, path="docs/specs/0007-demo/SPEC-0007.md", agent=AUTHOR, extra={"permission_mode": "acceptEdits"}) == "allow"
