import json
import subprocess
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import final_pr_body
import lock_check
import preflight
import stage_log


def _git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout.strip()


def _checkout(tmp_path):
    co = tmp_path / "co"
    co.mkdir()
    _git(co, "init", "-q")
    _git(co, "config", "user.email", "t@example.org")
    _git(co, "config", "user.name", "t")
    (co / "a.txt").write_text("a")
    _git(co, "add", "-A")
    _git(co, "commit", "-qm", "x")
    return co, _git(co, "rev-parse", "HEAD")


def test_lock_check_fails_on_dirty_or_mismatched_checkout(tmp_path):
    co, sha = _checkout(tmp_path)
    assert lock_check.problems(co, sha) == []
    assert lock_check.problems(co, "0" * 40)
    (co / "a.txt").write_text("changed")
    assert lock_check.problems(co, sha)


def test_lock_check_detects_ignored_files(tmp_path):
    co, sha = _checkout(tmp_path)
    (co / ".gitignore").write_text("*.pyc\n")
    _git(co, "add", ".gitignore")
    _git(co, "commit", "-qm", "ignore")
    sha = _git(co, "rev-parse", "HEAD")
    (co / "gate.cpython.pyc").write_text("planted")
    assert lock_check.problems(co, sha)


def test_lock_check_script_outside_checkout():
    assert lock_check.CHECKOUT not in lock_check.Path(lock_check.__file__).resolve().parents


def test_appsec_checkout_at_lock_sha():
    assert lock_check.problems() == []  # the test run's .appsec-baseline/ is at the lock and clean


def test_stage_refuses_while_aws_admin_logged_in():
    ok = lambda *a, **k: SimpleNamespace(returncode=0)  # noqa: E731
    assert any("aws logout" in e for e in preflight.aws_problems(env={}, run=ok))
    gone = lambda *a, **k: SimpleNamespace(returncode=255)  # noqa: E731
    assert preflight.aws_problems(env={}, run=gone) == []


def test_stage_preflight_rejects_aws_env_credentials():
    gone = lambda *a, **k: SimpleNamespace(returncode=255)  # noqa: E731
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        assert preflight.aws_problems(env={k: "x"}, run=gone)


def test_stage_rejects_unsafe_slug():
    assert preflight.slug_ok("local-stage-loop")
    for bad in ("x;curl evil", "Upper", "a--b", "ab", "a-b-c-d-e-f", "-lead", "a" * 41, "$(id)"):
        assert not preflight.slug_ok(bad), bad


def test_stage_log_retention_30_days(tmp_path):
    log = tmp_path / "l.jsonl"
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat().replace("+00:00", "Z")
    log.write_text(json.dumps({"ts": old}) + "\nnot json\n")
    stage_log.write("stage.start", "success", log=log, change="0007")
    assert stage_log.prune(log) == 2 and len(log.read_text().splitlines()) == 1


def test_log_events_have_required_fields_and_no_secrets(tmp_path):
    rec = stage_log.write("authz.denied", "denied", log=tmp_path / "l.jsonl", detail="a\n::add-mask::x")
    assert all(k in rec for k in stage_log.REQUIRED) and "\n" not in rec["detail"] and not rec["detail"].startswith("::")


def test_final_pr_body_lists_protected_changes(tmp_path):
    rep = tmp_path / "docs/specs/0007-x/reviews"
    rep.mkdir(parents=True)
    (rep / "CODE-0007.security-code-reviewer.json").write_text(
        json.dumps({"reviewer": "security-code-reviewer", "findings": [{"id": "SCR-001", "sr_ref": "SR-004", "exception": "EXC-002"}]})
    )
    paths = [".github/workflows/security.yml", "api/app/main.py", "stages.yml", "docs/specs/0007-x/reviews/CODE-0007.security-code-reviewer.json"]
    body = final_pr_body.body(paths, root=tmp_path, diff_text="uses: x/verify.yml@abc")
    assert "`.github/workflows/security.yml`" in body and "`stages.yml`" in body and "api/app/main.py" not in body
    assert "EXC-002: security-code-reviewer SCR-001 (SR-004)" in body and "verifier pin" in body
