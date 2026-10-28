# How the pipeline works

A plain-language guide to the automation around dogs-app: what runs, when, with which credentials, and why it is built this way.

## The stage loop (change 0001)

How every change is built. Start a session in this repo with `claude --plugin-dir .appsec-baseline` and say `/stage intent <idea>`; the steps are in `.claude/skills/stage/SKILL.md`.

- One feature branch per change (`feature/<NNNN>-<slug>`). Agents work there autonomously: each stage (one md file, or the code) is a PR from `stage/<NNNN>-<stage>` into the feature branch, merged by the session once the stage's checks pass. The owner is asked only for product facts the agents can't know and for decisions on security-requirement findings.
- **The only human gate is the merge to `main`**, which deploys: one PR from the feature branch to `main` after implementation and validation, with required checks and the owner's approval. Agents never merge into `main`.
- All LLM work (authoring and reviews) runs as subagents in the owner's local Claude Code session. **CI makes no LLM calls**: it runs scripts and scanners only.
- Any finding against a security requirement (all SRs are MUST) **escalates to the owner**: fix it, or accept it as an exception (reason, expiry) in appsec-baseline. Agents never decide.
- PR comments only for findings that need the owner (issue #9); passing results stay in logs and `reviews/`. No comment = nothing to report. Findings on `main`: one GitHub issue per finding (label `security-finding`).
- Old code is not assessed up front: stage 4 checks every touched file against all applicable SRs, so gaps surface when their code changes.

| Stage | Produces | Evaluated | How |
|---|---|---|---|
| 1 intent | `intent.md` | template structure | script |
| | | completeness: who is affected, functional and visual change, data, success criteria, out of scope | LLM: intent-completeness |
| | | which SRs apply | LLM: requirements auditor |
| | | no secrets | gitleaks |
| 2 spec | `spec.md` | template structure; complete and testable, no open questions | script; LLM: spec-completeness |
| | `TRACE-<NNNN>.md` | each applicable SR → how it is met → test | LLM: requirements auditor |
| | `THREAT-<NNNN>.md` | each threat → mitigation → test | LLM: security architect |
| 3 plan | `plan.md` (files, order, tasks, named tests) | template structure | script |
| | | fits `architecture.md` + ADRs | LLM: architecture-conformance |
| | | every SR and mitigation has a task and a named test | script (ID cross-check) + LLM: security architect |
| 4 code | code + tests (`plan.md` updated if the work departs from it) | lint, tests, build, kind deploy | CI `ci` |
| | | named tests exist and pass; changed files are in the plan | scripts |
| | | mitigations and SRs implemented; touched files vs all applicable SRs | LLM: security code reviewer |
| | | workflows / IaC (when changed) | LLM: workflow/IaC reviewer + zizmor, actionlint, Trivy |
| | | code and dependencies | Semgrep, OSV-Scanner, gitleaks |
| | | a report per required reviewer, matching the files (hash) | script (CI verifier) |
| 5 release | deployed build | running app | ZAP baseline in kind |
| | | ZAP alerts mapped to SRs; any alert without an exception stops the deploy and opens an issue | script |
| | | smoke test | script |
| 6 finding | GitHub issue → new `intent.md` | back to stage 1 | |

Docs-only PRs run gitleaks + the verifier only. Implementation starts only when every plan review passes.

## CI (no AI)

| Workflow | Starts when | Jobs |
|---|---|---|
| `ci.yml` | every PR | api (ruff, pytest), web (build), infra (fmt, validate, tflint), kind deploy + health |
| `security.yml` | every PR | `tests` (stage-loop tests, JUnit), `security/verify` (appsec-baseline `verify.yml` at the lock SHA: reports, hashes, statuses, exceptions, structure, cross-check, plan drift, named tests), `scanners` (docs-only diff: gitleaks; code diff: Semgrep incl. SR-022 rules, OSV-Scanner, gitleaks, Trivy, zizmor, actionlint), `security-gate` (all of them) |
| `deploy.yml` | merge to `main` | build → ZAP baseline in kind → deploy to AWS (OIDC, environment `dev`). ZAP alerts don't stop the deploy until change 0002 (exception EXC-001, expires 2026-12-31) |

Required on `main`: `ci`, `security/verify / verify`, `security-gate`.

## Re-enabling the CI reviewers

The CI LLM reviewers were switched off in change 0001; appsec-baseline keeps `security-review.yml` (dormant) as the comparison arm. To run them again:

1. In `security.yml`, re-add caller jobs `requirements`, `threat-model`, `workflow-iac` (`uses: ai-sdlc-lab/appsec-baseline/.github/workflows/security-review.yml@main`, `permissions: contents: read, id-token: write, pull-requests: write`, inputs `reviewer`, `model`, `anthropic_*`) and add them to `security-gate` `needs`; in `deploy.yml`, re-add `security-tester` before `deploy`.
2. In lab-admin `github.tf`: re-add the required checks `security/requirements / review` and `security/threat-model / review`, and the repo variables `REVIEWER_MODEL`, `ARCHITECT_MODEL`, `TESTER_MODEL` and `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_WORKSPACE_ID`, `ANTHROPIC_REVIEW_RULE_ID`, `ANTHROPIC_REVIEW_SERVICE_ACCOUNT_ID`. Add `anthropics/claude-code-action@*` to the Actions allowlist only if that action is used again.
3. In the Anthropic Console: re-create the reviewer federation rule (`job_workflow_ref` = appsec-baseline `security-review.yml@refs/heads/main`, org 343500886) and its service account; buy API credits.
