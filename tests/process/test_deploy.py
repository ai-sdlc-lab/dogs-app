"""Release pipeline checks for change 0002 (PLAN-0002 A-06 to A-11): structural checks of the workflows,
the Lambda limits and EXC-001. The behaviour itself is proven on the release (zap-report, smoke test)."""

import json
import re

import yaml
from conftest import ROOT, wf

RULES = ("10019", "10020", "10021", "10035", "10038", "10055")
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' https://${host}; "
    "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)
ECHOED = re.compile(r"""echo\s+("[^"]*"|'[^']*'|\S+)""")


def run_text(job):
    return "\n".join(st.get("run", "") for st in job["steps"])


def step(job, name):
    return next(st for st in job["steps"] if st.get("name", "").startswith(name))


def test_deploy_zap_gates_sr004_header_rules():
    jobs = wf("deploy.yml")["jobs"]
    dast = jobs["dast"]
    assert dast["needs"] == ["build"]
    assert set(jobs["deploy"]["needs"]) == {"build", "dast"}
    steps = dast["steps"]
    download = next(st for st in steps if st.get("uses", "").startswith("actions/download-artifact@"))
    assert download["with"]["name"] == "lambda-zip"

    # The scanned container serves the web build of the Lambda zip.
    text = run_text(dast)
    order = [
        "docker build -t dogs-api:ci api",
        "unzip -q build/lambda.zip 'web/*' -d \"$RUNNER_TEMP/rel\"",
        "printf 'FROM dogs-api:ci\\nCOPY . /srv/web\\n' | docker build -t dogs-api:ci -f - \"$RUNNER_TEMP/rel/web\"",
        "kind load docker-image dogs-api:ci",
    ]
    pos = [text.find(s) for s in order]
    assert -1 not in pos and pos == sorted(pos), pos

    scan = step(dast, "ZAP baseline")["run"]
    assert "zap-baseline.py -t http://127.0.0.1:8080/ -J zap-root.json" in scan
    assert "zap-baseline.py -t http://127.0.0.1:8080/api/health -J zap-health.json" in scan
    upload = next(st for st in steps if st.get("uses", "").startswith("actions/upload-artifact@"))
    assert upload["with"]["name"] == "zap-report" and upload["if"] == "always()"
    assert set(upload["with"]["path"].split()) == {"zap/zap-root.json", "zap/zap-health.json"}

    gate = step(dast, "ZAP gate")
    assert steps[-1] is gate and steps.index(upload) < steps.index(gate)  # report uploaded even on failure
    assert "if" not in gate and not gate.get("continue-on-error")
    assert "set -euo pipefail" in gate["run"] and "exit 1" in gate["run"]
    assert "zap/zap-root.json zap/zap-health.json" in gate["run"]
    assert 'IN("' + '", "'.join(RULES) + '")' in gate["run"]


def test_deploy_smoke_checks_security_headers():
    smoke = step(wf("deploy.yml")["jobs"]["deploy"], "Smoke test")["run"]
    assert "set -euo pipefail" in smoke
    assert "bucket=$(terraform -chdir=infra output -raw bucket)" in smoke
    assert 'host="${bucket}.s3.eu-north-1.amazonaws.com"' in smoke
    assert 'csp="' + CSP + '"' in smoke
    assert 'curl -fsS -D page.h -o page.html "$url"' in smoke
    assert 'curl -fsS -D health.h -o /dev/null "${url}api/health"' in smoke
    # Exactly one header line with exactly the value; fails naming the header.
    assert '[ "$v" = "$3" ] || { echo "::error::$1: header $2 missing, repeated or wrong"; exit 1; }' in smoke
    assert "for f in page.h health.h; do" in smoke
    for check in (
        'check "$f" X-Content-Type-Options nosniff',
        'check "$f" Strict-Transport-Security "max-age=31536000; includeSubDomains"',
        'check "$f" Referrer-Policy no-referrer',
        'check page.h Content-Security-Policy "$csp"',
        "check page.h Cross-Origin-Opener-Policy same-origin",
    ):
        assert check in smoke, check
    assert "img-src 'self';\" page.h" in smoke and "fallback CSP" in smoke
    assert "grep -qi '^access-control-' page.h health.h" in smoke
    assert '[ "$img_host" = "$host" ] || {' in smoke


def test_deploy_logs_no_presigned_urls():
    jobs = wf("deploy.yml")["jobs"]
    for name in ("dast", "deploy"):
        text = run_text(jobs[name])
        assert "X-Amz-" not in text and "set -x" not in text, name
        for echoed in ECHOED.findall(text):
            for leak in ("$dogs", "$IMG_URL", ".url"):
                assert leak not in echoed, f"{name}: echo {echoed}"
        summary = [line.strip() for line in text.splitlines() if "GITHUB_STEP_SUMMARY" in line]
        assert summary in ([], ['echo "### Deployed: $url" >> "$GITHUB_STEP_SUMMARY"']), name
    smoke = step(jobs["deploy"], "Smoke test")["run"]
    assert all("dogs=$(curl" in line for line in smoke.splitlines() if "api/dogs" in line)
    assert "IMG_URL=$(jq -r '.[0].url' <<<\"$dogs\")" in smoke
    assert 'curl -fsS -o /dev/null "$IMG_URL" 2>/dev/null ||' in smoke
    assert 'echo "image host: $img_host"' in smoke


def test_deploy_workflow_hardening_kept():
    d = wf("deploy.yml")
    jobs = d["jobs"]
    assert d["permissions"] == {}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["dast"]["permissions"] == {"contents": "read"}
    assert jobs["deploy"]["permissions"] == {"contents": "read", "id-token": "write"}
    for name, job in jobs.items():
        assert job["timeout-minutes"] <= 30, name
        for st in job["steps"]:
            uses, run = st.get("uses", ""), st.get("run", "")
            if uses:
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", uses), uses
            if uses.startswith("actions/checkout@"):
                assert st["with"]["persist-credentials"] is False, name
            assert "${{" not in run, f"{name}: untrusted values only through env"
            assert run.count("curl -fsSLo") == run.count("sha256sum -c"), f"{name}: unverified download"
    assert re.fullmatch(r"ghcr\.io/zaproxy/zaproxy@sha256:[0-9a-f]{64}", jobs["dast"]["env"]["ZAP_IMAGE"])
    pins = [d["env"]["TERRAFORM_SHA256"], jobs["dast"]["env"]["KIND_SHA256"], jobs["dast"]["env"]["KUBECTL_SHA256"]]
    assert all(re.fullmatch(r"[0-9a-f]{64}", p) for p in pins)
    text = run_text(jobs["dast"])
    assert re.findall(r"\bFROM [^\s\\]+", text) == ["FROM dogs-api:ci"]  # no new base image
    assert all('"$ZAP_IMAGE"' in line for line in text.splitlines() if "docker run" in line)


def test_security_yml_runs_web_tests_into_junit():
    steps = wf("security.yml")["jobs"]["tests"]["steps"]
    node = [st for st in steps if st.get("uses", "").startswith("actions/setup-node@")]
    ci_web = wf("ci.yml")["jobs"]["web"]
    ci_node = next(st for st in ci_web["steps"] if st.get("uses", "").startswith("actions/setup-node@"))
    assert len(node) == 1 and node[0]["uses"] == ci_node["uses"] and node[0]["with"]["node-version"] == "24"
    web = next(st for st in steps if st.get("run") == "npm --prefix web test")
    assert web["if"] == "always()"
    merge = next(st for st in steps if st.get("name") == "Merge JUnit files")
    assert merge["if"] == "always()" and "web/junit-web.xml" in merge["run"]
    assert steps.index(node[0]) < steps.index(web) < steps.index(merge)
    assert not any("npm ci" in st.get("run", "") for st in steps)  # the tests need no dependency
    script = json.loads((ROOT / "web/package.json").read_text())["scripts"]["test"]
    assert script.startswith("node --test --test-reporter=junit --test-reporter-destination=junit-web.xml ")
    assert "npm ci && npm run build && npm test" in run_text(ci_web)


def test_lambda_limits_unchanged():
    tf = (ROOT / "infra/main.tf").read_text()
    block = tf.split('resource "aws_lambda_function" "api" {', 1)[1].split("\n}\n", 1)[0]
    assert re.search(r"^\s*timeout\s*=\s*10\s*$", block, re.MULTILINE)
    assert re.search(r"^\s*memory_size\s*=\s*128\s*$", block, re.MULTILINE)


def test_exc001_no_longer_covers_zap():
    entries = yaml.safe_load((ROOT / "security/exceptions.yml").read_text())
    exc = next(e for e in entries if e["id"] == "EXC-001")
    assert "zap" not in exc["reason"].lower()
    assert "security tester" in exc["reason"].lower()
    assert exc["sr"] == ["SR-002", "SR-020", "SR-024"]
    assert exc["paths"] == [".github/workflows/deploy.yml"]
    assert (exc["approved_by"], exc["approved"], exc["expires"]) == ("nkalexiou", "2026-10-27", "2026-12-31")
