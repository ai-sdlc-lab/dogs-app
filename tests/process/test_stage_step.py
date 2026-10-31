import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import stage_step  # noqa: E402


def f(**over):
    return {"id": "AUD-001", "severity": "medium", "sr_ref": "SR-004", "file": "docs/x.md", "line": 3,
            "evidence": "Headers are missing from the error responses.", "recommendation": "Add them."} | over


def test_report_findings_maps_gate_statuses():
    doc = {"findings": [f(id="A-001", severity="low"), f(id="A-002", severity="high"), f(id="A-003", pre_existing=True),
                        f(id="A-004")]}
    st = {"A-001": {"status": "carried"}, "A-002": {"status": "escalate"}, "A-003": {"status": "deferred"},
          "A-004": {"status": "accepted-risk", "exception": "EXC-002"}}
    keep, errs = stage_step.report_findings(doc, st)
    got = {k["id"]: (k["status"], k.get("exception"), k.get("pre_existing")) for k in keep}
    assert got == {"A-001": ("carried", None, None), "A-002": ("open", None, None), "A-003": ("deferred", None, True),
                   "A-004": ("accepted-risk", "EXC-002", None)}
    assert errs == [] and "recommendation" not in keep[0]


def test_report_findings_refuses_unfixed_medium():
    keep, errs = stage_step.report_findings({"findings": [f()]}, {"AUD-001": {"status": "escalate"}})
    assert keep == [] and "still to fix" in errs[0]


def test_stage_prs_never_target_main():
    assert stage_step.base_ok("feature/0003-x", "0003")
    for base in ("main", "feature/0004-x", "stage/0003-spec", "feature/0003"):
        assert not stage_step.base_ok(base, "0003"), base


def test_models_come_from_agent_files():
    assert stage_step.model_of("author") == "claude-sonnet-5-5"
    assert stage_step.model_of("security-architect").startswith("claude-")


def test_bad_change_or_slug_rejected(capsys):
    assert stage_step.main(["start", "--change", "12", "--slug", "x-y", "--stage", "intent"]) == 1
    assert stage_step.main(["start", "--change", "0003", "--slug", "Bad;rm", "--stage", "intent"]) == 1
