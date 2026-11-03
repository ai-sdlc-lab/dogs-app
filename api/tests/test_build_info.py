"""The Lambda zip carries the git SHA as build info (change 0004, PLAN-0004 A-04, M-11)."""

import json
import re
import subprocess  # noqa: S404
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*cmd):
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout  # noqa: S603


def test_build_zip_contains_build_info(tmp_path):
    target = tmp_path / "nested" / "build_info.json"
    run("make", "build-info", f"BUILD_INFO={target}")
    sha = run("git", "rev-parse", "HEAD").strip()  # noqa: S607
    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    assert json.loads(target.read_text()) == {"sha": sha}

    # `make build` writes it into build/lambda/app after the app is copied and before the zip is made
    lines = run("make", "-n", "build").splitlines()  # noqa: S607
    copy = next(i for i, line in enumerate(lines) if "cp -R api/app" in line)
    info = next(i for i, line in enumerate(lines) if "build-info" in line)
    zipped = next(i for i, line in enumerate(lines) if "zip -qr" in line)
    assert copy < info < zipped
