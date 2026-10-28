import json
import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).with_name("protect-paths.py")
ROOT = HOOK.parents[2]


def run(path):
    event = {"tool_name": "Write", "cwd": str(ROOT), "tool_input": {"file_path": path}}
    env = os.environ | {"CLAUDE_PROJECT_DIR": str(ROOT)}
    return subprocess.run([str(HOOK)], input=json.dumps(event), text=True, env=env, capture_output=True).returncode


@pytest.mark.parametrize(
    "path",
    ["CLAUDE.md", "REVIEW.md", ".claude/settings.json", ".github/workflows/deploy.yml",
     "docs/specs/0001-x/THREAT-0001.md", "docs/specs/0001-x/TRACE-0001.md",
     "docs/../.github/x.yml", "../lab-admin/aws.tf", str(ROOT / "CLAUDE.md")],
)
def test_blocks_protected_paths(path):
    assert run(path) == 2


@pytest.mark.parametrize("path", ["docs/specs/0001-x/SPEC-0001.md", "docs/specs/0001-x/INT-0001.md", "api/app/main.py", "web/src/main.ts"])
def test_allows_normal_paths(path):
    assert run(path) == 0
