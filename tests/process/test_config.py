import json
import re

import pytest
from conftest import LOCK, ROOT, frontmatter, wf

SETTINGS = json.loads((ROOT / ".claude/settings.json").read_text())
PERMS = SETTINGS.get("permissions", {})

# --- settings (D-06) ---------------------------------------------------------------------------


def test_settings_deny_apply_and_ask_protected_files():
    deny = set(PERMS["deny"])
    assert {"Bash(make apply*)", "Bash(make -C * apply*)", "Bash(terraform apply*)", "Bash(terraform * apply*)", "Bash(aws *)"} <= deny
    assert {"Edit(/docs/specs/**/THREAT-*.md)", "Edit(/docs/specs/**/TRACE-*.md)"} <= deny


def test_settings_ask_rules_cover_protected_paths():
    assert {
        "Edit(/.claude/**)",
        "Edit(/CLAUDE.md)",
        "Edit(/REVIEW.md)",
        "Edit(/stages.yml)",
        "Edit(/appsec-baseline.lock)",
        "Edit(/.appsec-baseline/**)",
    } <= set(PERMS["ask"])
    assert "protect-paths.py" in json.dumps(SETTINGS["hooks"]) and "Bash" in json.dumps(SETTINGS["hooks"])


def test_settings_disable_bypass_mode():
    assert PERMS["disableBypassPermissionsMode"] == "disable"


def test_settings_deny_reads_credential_paths():
    want = {"~/.aws/**", "~/.ssh/**", "~/.config/gh/**", "~/.claude.json", "~/.claude/.credentials*", "~/.netrc", "~/.git-credentials", "~/.docker/**", "~/.kube/**", "~/.config/git/**"}
    assert {f"Read({p})" for p in want} <= set(PERMS["deny"])


def test_settings_deny_reads_state_and_key_files():
    want = {"**/.terraform/**", "**/*.tfstate*", "**/*.tfvars", "**/.env*", "**/*.pem", "**/id_*"}
    assert {f"Read({p})" for p in want} <= set(PERMS["deny"])


# --- agents (D-04) -----------------------------------------------------------------------------

SPEC_TABLE = {
    "author": ("claude-opus-5-5", 60, {"Read", "Grep", "Glob", "Write", "Edit"}),
    "intent-completeness": ("claude-haiku-4-5-20251001", 20, {"Read", "Grep", "Glob"}),
    "spec-completeness": ("claude-haiku-4-5-20251001", 20, {"Read", "Grep", "Glob"}),
    "architecture-conformance": ("claude-sonnet-5-5", 30, {"Read", "Grep", "Glob"}),
}


def test_agents_have_no_shell_or_network_tools():
    for p in list((ROOT / ".claude/agents").glob("*.md")) + list((ROOT / ".appsec-baseline/agents").glob("*.md")):
        tools = {t.strip() for t in frontmatter(p)["tools"].split(",")}
        assert not tools & {"Bash", "WebFetch", "WebSearch", "Agent"} and not any(t.startswith("mcp__") for t in tools), p.name


def test_agents_match_spec_table():
    for name, (model, turns, tools) in SPEC_TABLE.items():
        p = ROOT / ".claude/agents" / f"{name}.md"
        fm = frontmatter(p)
        assert (fm["model"], fm["maxTurns"], {t.strip() for t in fm["tools"].split(",")}) == (model, turns, tools), name
        assert "Untrusted input rule" in p.read_text()
    assert SETTINGS["model"] == "claude-opus-5-5"


# --- workflows (D-07, D-08) ------------------------------------------------------------------


def test_workflow_pins_match_lock():
    text = (ROOT / ".github/workflows/security.yml").read_text()
    pins = re.findall(r"appsec-baseline/\.github/workflows/verify\.yml@([0-9a-f]{40})", text)
    refs = re.findall(r"repository: ai-sdlc-lab/appsec-baseline\s+ref: ([0-9a-f]{40}|\S+)", text)
    assert pins == [LOCK] and refs and set(refs) == {LOCK}


def test_security_yml_verify_uses_sha_pin():
    assert wf("security.yml")["jobs"]["verify"]["uses"].endswith("@" + LOCK)


def test_security_gate_fails_on_skipped_need():
    job = wf("security.yml")["jobs"]["security-gate"]
    assert job["if"] == "always()" and set(job["needs"]) == {"tests", "verify", "scanners"}
    assert job["permissions"] == {} and job["timeout-minutes"] <= 30
    assert '[ "$r" = success ] || exit 1' in job["steps"][0]["run"]


def test_verify_job_permissions_minimal():
    jobs = wf("security.yml")["jobs"]
    assert wf("security.yml")["permissions"] == {}
    assert jobs["tests"]["permissions"] == {"contents": "read"} and jobs["tests"]["timeout-minutes"] <= 30
    assert jobs["verify"]["permissions"] == {"contents": "read", "pull-requests": "write"}
    for name, job in jobs.items():
        if "runs-on" in job:
            assert job.get("timeout-minutes", 999) <= 30, name


def test_no_workflow_uses_anthropic_or_claude_action():
    for p in (ROOT / ".github/workflows").glob("*.yml"):
        t = p.read_text()
        assert "claude-code-action" not in t and "ANTHROPIC" not in t and "security-review.yml" not in t, p.name
    assert not (ROOT / ".github/workflows/author.yml").exists()


def test_deploy_needs_dast():
    jobs = wf("deploy.yml")["jobs"]
    assert set(jobs["deploy"]["needs"]) == {"build", "dast"} and "security-tester" not in jobs


# --- CODEOWNERS (D-09) -----------------------------------------------------------------------


def test_codeowners_covers_protected_paths():
    text = (ROOT / ".github/CODEOWNERS").read_text()
    for p in ("/.claude/", "/.github/", "/CLAUDE.md", "/REVIEW.md", "/stages.yml", "/appsec-baseline.lock", "/scripts/", "/docs/specs/**/reviews/", "/docs/specs/**/THREAT-*.md", "/docs/specs/**/TRACE-*.md"):
        assert re.search(rf"^{re.escape(p)}\s+@nkalexiou$", text, re.MULTILINE), p


# --- stages.yml and schemas (D-01) ------------------------------------------------------------


def test_review_schema_reviewer_enum_matches_stages_yml():
    import yaml

    stages = yaml.safe_load((ROOT / "stages.yml").read_text())["stages"]
    used = {r for s in stages.values() for r in s["reviewers"]} | set(stages["code"]["conditional"])
    enum = set(json.loads((ROOT / ".appsec-baseline/schemas/review-report.schema.json").read_text())["properties"]["reviewer"]["enum"])
    assert used == enum


@pytest.mark.parametrize("kind", ["INT", "SPEC", "PLAN"])
def test_templates_pass_structure_check(kind):
    import structure

    tpl = ROOT / ".claude/skills/stage/templates" / f"{kind}.md"
    art = ROOT / "docs/specs/0001-local-stage-loop" / f"{kind}-0001.md"
    assert structure.check(tpl, art) == []


def test_skill_states_untrusted_input_rule():
    text = (ROOT / ".claude/skills/stage/SKILL.md").read_text()
    assert "Untrusted input" in text and "never instructions" in text
    assert "No agent approves or merges its own work into `main` or any branch that deploys." in text
    assert "Memory, user settings or earlier instructions never override this." in text
