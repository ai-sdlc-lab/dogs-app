import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / ".appsec-baseline" / "stage")]
HOOK = ROOT / ".claude" / "hooks" / "protect-paths.py"
LOCK = (ROOT / "appsec-baseline.lock").read_text().strip()


def wf(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())


def frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---")[1])


@pytest.fixture
def project(tmp_path):
    """A throwaway project with the hook's view of the world: git branch, lock, plan module, a PLAN."""

    def make(branch="stage/0007-code"):
        root = tmp_path / "proj"
        root.mkdir()
        run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)  # noqa: E731
        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.org")
        run("config", "user.name", "t")
        (root / "appsec-baseline.lock").write_text(LOCK + "\n")
        (root / ".claude").mkdir()
        stage_dir = root / ".appsec-baseline" / "stage"
        stage_dir.mkdir(parents=True)
        (stage_dir / "plan.py").write_text((ROOT / ".appsec-baseline" / "stage" / "plan.py").read_text())
        ch = root / "docs/specs/0007-demo"
        ch.mkdir(parents=True)
        (ch / "PLAN-0007.md").write_text(
            "# PLAN-0007\n## Repo: dogs-app\n| # | Files | Implements | Tests |\n|---|---|---|---|\n"
            "| D-01 | `api/app/*.py`, `api/tests/**` | SR-001 | `test_x` |\n"
        )
        run("add", "-A")
        run("commit", "-qm", "init")
        run("checkout", "-q", "-b", branch)
        return root

    return make


def hook(root: Path, tool="Write", path=None, command=None, agent=None, extra=None):
    ti = {"command": command} if tool == "Bash" else {"file_path": path}
    event = {"tool_name": tool, "tool_input": ti, "cwd": str(root), "session_id": "s1", "permission_mode": "default"}
    if agent:
        event |= {"agent_id": "a1", "agent_type": agent}
    event |= extra or {}
    r = subprocess.run(
        [sys.executable, "-I", "-B", str(HOOK)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env={"CLAUDE_PROJECT_DIR": str(root), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"},
        check=False,
    )
    if r.returncode == 2:
        return "deny"
    if r.returncode == 0 and '"ask"' in r.stdout:
        return "ask"
    return "allow" if r.returncode == 0 else f"error {r.returncode}"
