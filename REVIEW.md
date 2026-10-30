# Review passes

LLM reviewers only produce findings; a deterministic gate (`appsec-baseline/gate/security_gate.py`) decides allow / block / questions / escalate, and any finding against a security requirement is decided by the owner. Reviewers are read-only subagents in the local SDLC workflow, loaded from appsec-baseline at the locked commit.

| When | Check | Covers | Required |
|---|---|---|---|
| Each stage, locally | reviewers from `stages.yml` (intent-completeness, spec-completeness, architecture-conformance, security-requirements-auditor, security-architect, security-code-reviewer, workflow-iac-reviewer) | completeness, architecture fit, requirements traceability, threat model, code vs. SRs and mitigations, workflows/IaC | gate allows before the stage PR |
| Every PR | `build-and-test` | ruff, pytest, tsc + build, terraform fmt/validate, tflint, kind deploy + health | yes |
| Every PR | `stage gate` (`tests (workflow + app)` + `stage reviews / verify`) | review reports present, schema-valid, SHA-256 bound to the files, statuses and exceptions valid; template structure; cross-check; plan drift; named tests | yes |
| Every PR | `security scanners` | docs-only: gitleaks. Code: Semgrep CE (+ SR-022 rules), OSV-Scanner, gitleaks, Trivy, zizmor, actionlint | yes |
| `main`, before each deploy | ZAP baseline on the release build in kind | DAST; alerts don't stop the deploy until change 0002 (EXC-001) | deploy waits for it |
| Final PR to `main` | owner approval | the whole change, protected-path changes, exceptions used | only the owner merges |

No AI runs in CI. A PR comment appears only when the verifier fails; no finding, no comment.
