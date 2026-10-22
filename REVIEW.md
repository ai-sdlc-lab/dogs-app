# Review passes

Every check below reports to the PR or release; a deterministic gate (`appsec-baseline/gate/security_gate.py`) decides allow / block / escalate. LLM reviewers only produce findings. All AI reviewers run from appsec-baseline's reusable workflow at the pinned commit, read-only.

| When | Check | Covers | Required |
|---|---|---|---|
| Every PR | `ci` | ruff, pytest, tsc + build, terraform fmt/validate, tflint, kind deploy + health | yes |
| Every PR | scanners (in `security-gate`) | Semgrep CE (code), OSV-Scanner (dependencies), gitleaks (secrets), Trivy (infra config), zizmor + actionlint (workflows) | yes |
| PR changing `docs/specs/` | `security/requirements` | security-requirements-auditor: every applicable SR covered in intent/spec/plan → traceability report | yes |
| PR changing `docs/specs/` | `security/threat-model` | security-architect: STRIDE, abuse cases, impact on the existing system; on plan PRs, mitigations → steps and tests | yes |
| PR changing `.github/` or `infra/` | workflow-iac-reviewer (in `security-gate`) | IAM, exposure, encryption, workflow hardening, supply chain | yes |
| `main`, before each deploy | security-tester | injection-input, authn-authz, secrets-pii-logging checklists over everything since the last deploy + ZAP baseline on the release build | deploy waits for it |
| Every PR touching protected paths | code-owner review | `.claude/`, `CLAUDE.md`, `REVIEW.md`, `.github/`, `infra/`, threat models, traceability | yes (ruleset) |

Reviewers whose scope has no changed files report "no files in scope" and pass without calling the model.
