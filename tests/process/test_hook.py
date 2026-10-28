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
