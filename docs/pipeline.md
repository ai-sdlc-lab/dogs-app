# How the pipeline works

A plain-language guide to the automation around dogs-app: what runs, when, with which credentials, and why it is built this way.

## The SDLC workflow (change 0001)

How every change is built. Start a session in this repo with `claude --plugin-dir .appsec-baseline --permission-mode acceptEdits` and say `/stage <idea>`. Models: the session and the author on Sonnet, reviewers on Sonnet or Haiku (Opus was overkill: 52% of the change 0002 run; usage history in lab-admin `docs/USAGE.md`). Permissions: `git`, `gh`, `python3` and `make` are allowed; `gh api`, `gh repo delete|edit`, `gh secret`, `gh variable`, `gh auth`, `gh workflow`, apply/destroy and `aws` are denied; the hook denies merges and pushes into `main` and protected-file edits; the steps are in `.claude/skills/stage/SKILL.md`.

- One feature branch per change (`feature/<NNNN>-<slug>`). Agents work there autonomously: each stage (one md file, or the code) is a PR from `stage/<NNNN>-<stage>` into the feature branch, merged by the session once the stage's checks pass. The owner is asked only for product facts the agents can't know and for decisions on security-requirement findings.
- **The only human gate is the merge to `main`**, which deploys: one PR from the feature branch to `main` after implementation and validation, with required checks and the owner's approval. Agents never merge into `main`.
- All LLM work (authoring and reviews) runs as subagents in the owner's local Claude Code session. **CI makes no LLM calls**: it runs scripts and scanners only.
- Security findings are fixed by the agents (up to 3 rounds). Still open after that: a low or medium one gets an exception in this repo's `security/exceptions.yml` (`approved_by: agent`, at most 90 days); a high or critical one stays open and blocks only the merge to `main`. The final PR lists open findings, new exceptions and the session's decisions (`decisions.md`) first: the owner decides at that merge. After the intent stage the session never asks the owner anything. Exceptions are per repository; appsec-baseline holds only the requirements and the exception format.
- PR comments only for findings that need the owner (issue #9); passing results stay in logs and `reviews/`. No comment = nothing to report. Findings on `main`: one GitHub issue per finding (label `security-finding`).
- Old code is not assessed up front: stage 4 reviews the changed lines against all applicable SRs. A gap a reviewer finds in existing code the change doesn't alter is old debt: it goes to a GitHub issue (`security-finding: <SR> …`) and never blocks the change; the final PR lists it.

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
| 4 code | code + tests (`plan.md` updated if the work departs from it) | lint, tests, build, kind deploy | CI `build-and-test` |
| | | named tests exist and pass; changed files are in the plan | scripts |
| | | mitigations and SRs implemented; changed lines vs all applicable SRs (when a path outside `docs/`, `.github/`, `infra/` changed) | LLM: security code reviewer |
| | | workflows / IaC (when changed) | LLM: workflow/IaC reviewer + zizmor, actionlint, Trivy |
| | | code and dependencies | Semgrep, OSV-Scanner, gitleaks |
| | | a report per required reviewer, matching the files (hash) | script (CI verifier) |
| 5 release | deployed build | running app | ZAP baseline in kind on `/` and `/api/health` (the container serves the Lambda zip's web build) |
| | | any alert from the SR-004 header rules (10019, 10020, 10021, 10035, 10038, 10055) stops the deploy; other alerts stay in the `zap-report` artifact | script (change 0002) |
| | | smoke test: app, exact SR-004 headers, and the CSP image host equal to the presigned URL host | script |
| 6 finding | GitHub issue → new `intent.md` | back to stage 1 | |

Docs-only PRs run gitleaks + the verifier only. Implementation starts only when every plan review passes.

### Which reviewer runs when

| Stage | Reviewers | Runs | Gets |
|---|---|---|---|
| intent | intent-completeness (Haiku), requirements auditor (Sonnet) | always | the whole artifact |
| spec | spec-completeness (Haiku), requirements auditor, security architect (Sonnet) | always | the whole artifact + INT |
| plan | architecture-conformance, security architect (Sonnet) | always | the whole artifact + earlier artifacts |
| code | security code reviewer (Sonnet) | a changed path outside `docs/`, `.github/`, `infra/` | the diff of those paths + PLAN, TRACE, THREAT |
| code | workflow/IaC reviewer (Sonnet) | a changed path under `.github/` or `infra/` | the diff of those paths |

Rounds: round 1 runs every reviewer that applies. From round 2 only the reviewers with open findings run again, with their findings and what changed since their last run; a reviewer that passed keeps its pass. A reviewer runs again anyway when a fix adds a path it now applies to. Trade-off (owner decision 2026-10-30): a fix made for one reviewer is not re-checked by the others. The rules live in `stages.yml` (`conditional`: reviewer → path regex) and the CI verifier enforces them.

## CI (no AI)

| Workflow | Starts when | Jobs |
|---|---|---|
| `ci.yml` | every PR | api (ruff, pytest), web (build), infra (fmt, validate, tflint), kind deploy + health |
| `security.yml` | every PR | `tests (workflow + app)` (SDLC workflow and app tests, one JUnit file), `stage reviews / verify` (appsec-baseline `verify.yml` at the lock SHA: reports, hashes, statuses, exceptions, structure, cross-check, plan drift, named tests), `security scanners` (docs-only diff: gitleaks; code diff: Semgrep incl. SR-022 rules, OSV-Scanner, gitleaks, Trivy, zizmor, actionlint), `stage gate` (tests + verify) |
| `deploy.yml` | merge to `main` | build → ZAP baseline in kind on `/` and `/api/health` (any alert from the SR-004 header rules stops the deploy) → deploy to AWS (OIDC, environment `dev`) → smoke test of the app and its SR-004 headers and CSP image host. No LLM security tester in deploy (exception EXC-001, expires 2026-12-31) |

Required on `main`, one check per purpose: `build-and-test` (quality), `stage gate` (the change went through the SDLC workflow), `security scanners` (security).

## Re-enabling the CI reviewers

The CI LLM reviewers were switched off in change 0001; appsec-baseline keeps `security-review.yml` (dormant) as the comparison arm. To run them again:

1. In `security.yml`, re-add caller jobs `requirements`, `threat-model`, `workflow-iac` (`uses: ai-sdlc-lab/appsec-baseline/.github/workflows/security-review.yml@main`, `permissions: contents: read, id-token: write, pull-requests: write`, inputs `reviewer`, `model`, `anthropic_*`) and add them to `stage-gate` `needs`; in `deploy.yml`, re-add `security-tester` before `deploy`.
2. In lab-admin `github.tf`: re-add the required checks `security/requirements / review` and `security/threat-model / review`, and the repo variables `REVIEWER_MODEL`, `ARCHITECT_MODEL`, `TESTER_MODEL` and `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_WORKSPACE_ID`, `ANTHROPIC_REVIEW_RULE_ID`, `ANTHROPIC_REVIEW_SERVICE_ACCOUNT_ID`. Add `anthropics/claude-code-action@*` to the Actions allowlist only if that action is used again.
3. In the Anthropic Console: re-create the reviewer federation rule (`job_workflow_ref` = appsec-baseline `security-review.yml@refs/heads/main`, org 343500886) and its service account; buy API credits.
