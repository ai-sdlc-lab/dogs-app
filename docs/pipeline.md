# How the pipeline works

A plain-language guide to the automation around dogs-app: what runs, when, with which credentials, and why it is built this way.

## Vocabulary

| Term | Meaning here |
|---|---|
| **Workflow** | A YAML file under `.github/workflows/` that GitHub Actions runs when something happens (a PR is opened, code is merged, an issue is labelled). |
| **Job** | One unit of work inside a workflow, run on a fresh GitHub machine (a *runner*). Each job reports a **check** (green/red) on the PR or commit. |
| **Reusable workflow** | A workflow that never starts on its own; other workflows *call* it, like a function. Ours lives in appsec-baseline and is called at a fixed commit. |
| **Required check** | A check the ruleset demands before a PR can merge. Checks belong to a specific **commit**: the newest commit of a PR must have them all green. |
| **`GITHUB_TOKEN`** | The short-lived token GitHub gives every job. By GitHub's design, anything it does (a commit, a label, a comment) **does not start other workflows**, which prevents endless loops. |
| **Claude GitHub App token** | The token `claude-code-action` gets for the Claude app (`claude[bot]`). Its actions *do* start workflows. |
| **OIDC token** | A signed "who am I" token GitHub issues to a job. AWS and Anthropic exchange it for short-lived credentials if it matches their rules. Nothing secret is stored anywhere. |

## The workflow files

| File | Starts when | What it does | Uses AI | Credentials |
|---|---|---|---|---|
| dogs-app `ci.yml` | every PR | ruff, pytest, TypeScript build, Terraform checks, kind deploy + health check | no | `GITHUB_TOKEN` (read) |
| dogs-app `security.yml` | every PR | calls the AppSec reviewer 3× (requirements auditor, security architect, workflow/IaC reviewer; each skips if nothing in its scope changed), runs 6 scanners, then `security-gate` | yes | `GITHUB_TOKEN`; Anthropic **rule A** |
| dogs-app `deploy.yml` | merge to `main` | build → ZAP scan of the release in kind → calls the AppSec reviewer as **security tester** → deploy to AWS if the gate allows | yes | Anthropic **rule A**; AWS role (environment `dev`) |
| dogs-app `author.yml` | a maintainer labels an issue `feature` / `spec` / `plan` / `implement` | the author agent writes the next artifact on a branch and opens a PR as `claude[bot]` | yes | Claude App token; Anthropic **rule B** |
| appsec-baseline `security-review.yml` | never by itself; called by `security.yml` and `deploy.yml` | runs **one** reviewer agent read-only, applies the gate, redacts credentials, posts the report | yes | whatever the caller grants |
| appsec-baseline `ci.yml` | PRs to appsec-baseline | tests the gate and the redaction | no | `GITHUB_TOKEN` (read) |

### Pull request

```
PR opened/updated
 ├─ ci.yml ─────────────────────────────────────────────► check: ci
 └─ security.yml
     ├─ security/requirements ─┐
     ├─ security/threat-model ─┤ each calls appsec-baseline security-review.yml@<pinned commit>
     ├─ security/workflow-iac ─┘   → agent (read-only) → redact → gate → PR comment
     ├─ scanners: Semgrep, OSV-Scanner, gitleaks, Trivy, zizmor, actionlint → gate
     └─ security-gate (all of the above green?) ──────────► check: security-gate
Merge needs: required checks green + 1 approval by the code owner (you), or your own PR via bypass.
```

### Merge to main

```
push to main → deploy.yml
  build ──────────────────────────────┐
  dast: ZAP baseline on the release ──┤
  security-tester (appsec reviewer) ──┴─► deploy (environment dev, OIDC → AWS) → smoke test
```

### A feature, end to end (Mode A)

```
issue (form) ─ you add label `feature` ─► author writes intent.md ─► PR ─► reviews ─► you merge
             ─ you add label `spec`    ─► author writes spec.md   ─► PR ─► reviews ─► you merge
             ─ you add label `plan`    ─► author writes plan.md   ─► PR ─► reviews ─► you merge
             ─ you add label `implement` ► author writes code      ─► PR ─► reviews ─► you merge ─► deploy
```

## The two Anthropic rules

Anthropic gives a Claude token only to jobs whose GitHub-signed identity matches a rule:

| Rule | Matches | Used by |
|---|---|---|
| **A, reviewers** | dogs-app repository ID **and** `job_workflow_sha` = the pinned commit of appsec-baseline's `security-review.yml` | requirements auditor, security architect, workflow/IaC reviewer, security tester (four agents, one workflow file) |
| **B, author** | dogs-app repository ID, `main`, event `issues`, `workflow_ref` = dogs-app `author.yml` on `main` | the author agent |

A PR can't satisfy either rule with modified code: rule A needs AppSec's file at the pinned commit (which lives in another repository), and rule B needs the workflow as it is on `main` (changing it requires a merge, which requires your review).

## Design choices

**Reviewer reports are PR comments, not commits.** The reviewers could commit `threat-model.md` to the PR branch, but a commit made with `GITHUB_TOKEN` starts no workflows. That reviewer commit would become the PR's newest commit, and it would have no `ci` or `security-gate` checks; GitHub would wait for them forever and the PR could never merge. Committing with the Claude App token would instead re-run every check, including the reviewers, in a loop. So reports are posted as a PR comment (updated in place) and kept as a workflow artifact.

**Stages advance by your label, not automatically on merge.** Merging does start workflows, so automatic advancement is technically possible. The blocker is the author tool: `claude-code-action` documents that it creates a new branch when started from an **issue**, but not what it does when started from a push to `main`, and a wrong guess could try to commit to `main`. The issue label is the documented path, and it keeps a human decision between stages (Mode A). Automatic advancement is a Mode B item.

## What is public, and how credentials are protected

dogs-app and appsec-baseline are public: anyone can read workflow logs, PR comments and artifacts.

| Credential | Where it exists | Protection |
|---|---|---|
| AWS role credentials | deploy job only, 1 hour | masked in logs; passed through the job environment, never printed or uploaded |
| GitHub OIDC tokens | inside jobs, ~5 minutes | masked; single-use at Anthropic |
| Anthropic tokens | inside the AI step, ≤ 10 minutes | handled by `claude-code-action`; never written to our outputs |
| Claude App token | author job only | passed only to `gh pr create` via the environment |
| Reviewer output (could be manipulated into quoting a secret) | becomes a PR comment and artifact | `redact.py` removes credential patterns first (tested); **any redaction escalates to a human** |
| Your `gh` login and `aws login` session | your laptop only | never in a repository; ATK-15/ATK-16 in the playbook |
