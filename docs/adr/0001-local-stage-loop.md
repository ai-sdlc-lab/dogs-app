# ADR-0001: LLM authoring and review in the local session; CI deterministic

Status: accepted (2026-10-28, change 0001). Context and details: `docs/specs/0001-local-stage-loop/`.

## Decision
Every change runs through intent → spec → plan → code on a feature branch. Authoring and all LLM reviews run as subagents in the owner's Claude Code session (subscription). CI makes no AI calls: appsec-baseline's verifier checks the committed review reports (SHA-256 bound to the reviewed files), scripts check structure, cross-references, plan drift and named tests, scanners run on the paths they cover. Agents merge stage PRs into the feature branch; only the owner merges into `main`.

## Why
- CI reviewers on API credits cost money per run and ran at the wrong time (requirements checked on code, threats at deploy).
- Requirements and threats are decided at spec and plan; code and release only verify.
- Security findings against a requirement are decided by the owner, never by an agent's severity.

## Trade-offs
- Reviews are self-attested: CI proves a report matches the files, not that it was honestly run (playbook ATK-18). The owner's approval of the merge to `main` is the gate.
- The session acts with the owner's GitHub identity (separate identity parked: issue #12).
- Workflow files in a PR are chosen by the PR; the owner reviews protected-path changes at the final merge.

## Alternatives rejected
CI reviewers on API credits (kept dormant as a comparison arm; `docs/pipeline.md` → "Re-enabling the CI reviewers"); CI with a subscription token (long-lived secret); local open-weight models.
