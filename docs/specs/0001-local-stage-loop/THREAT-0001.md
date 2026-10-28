# THREAT-0001: threat model

<!-- Written by the security-architect reviewer. Do not edit by hand. Round 3 (spec stage, final). -->

Stage reviewed: spec (`SPEC-0001.md`, section 11 adopting M-01..M-30, with `INT-0001.md`). Requirements: `security-requirements.md`, SR-031 as amended in SPEC section 9.

Owner decisions taken as given, not re-raised: `reviews/INT-0001-status.md`; session uses the owner's GitHub identity and bypass (issue #12 parked); agents merge stage PRs into feature branches; only the merge to `main` needs the owner; EXC-001; self-attested reviews; public findings; owner-account MFA out of scope.

Round status: ARC-001..ARC-017 resolved in round 2; ARC-018..ARC-030 resolved in this round (SPEC section 11 carries M-18..M-30 with unchanged IDs, section 10 lists their named tests, 2.5 step 8 now cites the `tests` job). One new low finding (ARC-031) refines M-29; no new M-ID is needed.

## Scope and change summary
LLM review moves from GitHub Actions to the owner's local Claude Code session. The change adds or modifies:

- **Orchestrator:** main session (Opus 5.5) with shell, network, the owner's `gh`/git credentials. Runs `/stage`, commits, pushes `feature/*` and `stage/*`, merges stage PRs, opens the final PR to `main`.
- **Subagents:** author (Read, Grep, Glob, Write, Edit) and read-only reviewers; allow lists, pinned models, `maxTurns`; PreToolUse hook separates subagents by `agent_id`.
- **appsec-baseline:** `validate`, `gate`, `hash`, `structure`, `crosscheck`, `named_tests`, `plan_drift`, `classify`, `write_artifact`, `redact`; `review-report.schema.json`; `exceptions/sr-exceptions.yml`; reusable `verify.yml`. Local scripts run from `.appsec-baseline/` at the lock SHA.
- **dogs-app:** `stages.yml`, `appsec-baseline.lock`, `.claude/skills/stage`, agents, templates, reports under `docs/specs/<NNNN>-<slug>/reviews/`; CI jobs `verify`, `scanners`, `tests`, `security-gate`; reviewer jobs, `security-tester`, `author.yml` removed.
- **lab-admin:** required checks swapped to `ci`, `security/verify / verify`, `security-gate`; `ANTHROPIC_*` variables, labels and allowlist entries removed.
- **Unchanged:** app code, API, web, AWS resources, the AWS OIDC trust bound to environment `dev`.

## Assets
- A1: `main` and the deploy path (`deploy.yml` -> environment `dev` -> AWS role).
- A2: local guardrails (`.claude/settings.json`, hooks, agents, skill, `stages.yml`, lock, `.appsec-baseline/`).
- A3: integrity of review evidence (reports, `TRACE-`/`THREAT-`, `sr-exceptions.yml`).
- A4: the verifier and its scripts at the lock SHA.
- A5: owner credentials on the laptop (`gh` token, git credentials, `~/.aws` admin session, Claude login).
- A6: CI workflows and required checks.
- A7: confidentiality of everything agents read, because reports are public.

## Trust boundaries and data flows
| # | From -> To | Data | Crosses boundary |
|---|---|---|---|
| 1 | Repo content -> author and reviewer subagents | untrusted text | yes: data -> LLM |
| 2 | Subagent output -> `validate`/`gate` -> main session | findings JSON, artifact markdown | yes: LLM output -> privileged orchestrator |
| 3 | Main session -> local guardrail files | edits, Bash writes | yes: agent -> config effective at once |
| 4 | Main session -> GitHub as owner | pushes, PRs, merges | yes (identity accepted) |
| 5 | Main session -> AWS / Terraform via admin session | apply, aws | yes: laptop -> AWS |
| 6 | PR head -> `verify` (base `stages.yml` and lock) | reports, diff, workflows | yes: PR content -> CI |
| 7 | appsec-baseline `verify.yml` + scripts at lock SHA -> `verify` | code run in CI | yes: other repo |
| 8 | appsec-baseline `exceptions/` at lock SHA -> gate | accepted-risk records | yes: other repo |
| 9 | `tests` job (PR code) -> JUnit artifact -> `verify` | XML | yes: untrusted code output -> verifier |
| 10 | `verify` -> PR comment, log, summary | strings from reports | yes: untrusted text -> GitHub UI, runner log |
| 11 | Reports and artifacts -> public git | findings, quotes | yes: laptop -> public |
| 12 | lab-admin Terraform -> GitHub rulesets | required checks | yes: IaC -> org |
| 13 | `main` -> `deploy.yml` -> AWS OIDC | build, apply | existing; controls reduced (EXC-001) |
| 14 | Owner memory and user settings (`~/.claude/**`) -> main session | standing instructions | yes: outside repo and hook |

## STRIDE per element
| Element | S | T | R | I | D | E | Notes |
|---|---|---|---|---|---|---|---|
| Main session | n/a | mitigated: M-03, M-21, M-24 | accepted: acts as owner | accepted (GitHub); AWS mitigated M-04, M-27 | n/a | mitigated: M-17, M-08; memory autonomy M-29 (ARC-031) | most privileged element |
| Author subagent | n/a | mitigated: M-11, M-26 | n/a | mitigated: M-10, M-28 | n/a | mitigated: no shell | |
| Reviewer subagents | n/a | mitigated: read-only | n/a | mitigated: M-10, M-28 | n/a | mitigated: allow list | `sr_ref`/`status` set by gate: M-02, M-08 |
| Hook + settings | n/a | mitigated: M-03, M-21 | n/a | n/a | n/a | mitigated: M-26 | |
| Gate and `validate` | mitigated: schema, allow list | mitigated: M-20, M-22 | n/a | n/a | mitigated: 3 rounds, maxTurns | n/a | |
| Review reports | accepted: self-declared reviewer | mitigated: M-01, M-02, M-05, M-20 | accepted (self-attested) | accepted (public) | n/a | n/a | |
| CI verifier | mitigated: `pull_request`, lock on `main` | mitigated: M-18, M-19 (owner review of caller workflow is the control) | n/a | n/a | mitigated: 15 min, M-25 | mitigated: `permissions: {}` | |
| PR comment, log, summary | n/a | mitigated: M-14, M-30 | n/a | n/a | n/a | n/a | |
| `sr-exceptions.yml` | n/a | mitigated: M-12, M-23 | accepted | n/a | n/a | n/a | merge is owner-only |
| CODEOWNERS + rulesets | n/a | mitigated: M-19 | n/a | n/a | n/a | n/a | owner bypass accepted |
| lab-admin required checks | n/a | mitigated: M-16, M-18 ordering | n/a | n/a | n/a | n/a | |
| `deploy.yml` | n/a | mitigated: M-16 | n/a | n/a | n/a | n/a | ZAP gap accepted (EXC-001) |
| `/stage` arguments | n/a | mitigated: M-15 | n/a | n/a | n/a | n/a | |

## Abuse cases
| ID | Attacker goal and steps | Impact |
|---|---|---|
| AB-01 | Injection edits `.claude/settings.json` via Bash or crashes the hook. Closed by M-03. | Guardrails off |
| AB-02 | Code PR without stage folder, or code report omitting changed files. Closed by M-01. | Unreviewed code passes |
| AB-03 | Injected session runs apply variants while the admin session is live. Closed by M-04, M-27. | Arbitrary AWS change |
| AB-04 | SR finding written as `carried` or `fixed`. Closed by M-02. | SR decision bypassed |
| AB-05 | Steered reviewer labels an SR violation `NEW`, low. Closed by M-08. | Lost owner decision |
| AB-06 | Session hand-copies architect output into `THREAT-0001.md`. Closed by M-05, M-24. | Doctored record |
| AB-07 | Injected author writes `reviews/`, other artifacts, `infra/`. Closed by M-11, M-26. | Forged evidence |
| AB-08 | Subagent reads credential or state files and quotes them publicly. Closed by M-10, M-28. | Credential disclosure |
| AB-09 | Stale or dirty `.appsec-baseline/`. Closed by M-09, M-22. | Reports under unused rules |
| AB-10 | PR tests forge JUnit. Residual equals a trivially passing test; M-07, M-25 limit blast radius. | Weak named-test proof |
| AB-11 | Markup, mentions, `::` or newlines in report strings reach comment, summary, log. Closed by M-14, M-30. | Phishing, log manipulation |
| AB-12 | Reviewer free text steers the main session. Closed by M-17, M-08. | Steered privileged session |
| AB-13 | Catch-all, long-lived or malformed exception. Closed by M-12, M-23. | Silent SR acceptance |
| AB-14 | `deploy` rewired without `needs: dast`. Closed by M-16. | Deploy without DAST |
| AB-15 | Slug with shell metacharacters. Closed by M-15. | Command injection |
| AB-16 | Final PR of 0001: base lacks `stages.yml`/lock. Closed by M-18 (bootstrap only while base lacks files). | Verifier loosened ad hoc |
| AB-17 | Auto/bypass permission mode makes `ask` rules not prompt. Closed by M-21. | Guardrails editable unattended |
| AB-18 | PR edits caller `security.yml` pin, `security-gate`, `stages.yml`, lock. Control: M-19 CODEOWNERS plus script-generated final-PR list; the real gate is the owner's review. | Forged green check |
| AB-19 | Blocking NEW finding ends as `carried`. Closed by M-20. | Undecided blocking finding committed |
| AB-20 | Lock check script inside the checked tree. Closed by M-22. | Altered gate with matching SHA |
| AB-21 | Hostile JUnit XML. Closed by M-25. | Verifier DoS or file read |
| AB-22 | Newline followed by `::` in report string. Closed by M-30. | Workflow-command injection |
| AB-23 | Subagent payload lacks `agent_id`. Closed by M-26. | Author limits lapse |
| AB-24 | Owner memory entry `temporary-merge-apply-autonomy` loaded into the main session. Control: M-29 plus SKILL.md; see ARC-031 for the verification gap. | Session believes it may merge or apply |
| AB-25 | New defect in `deploy.yml` auto-accepted by EXC-001. Closed by M-23. | Hidden SR violation |
| AB-26 | AWS credentials via env or later login. Closed by M-27. | M-04 bypassed |
| AB-27 | Main session writes `THREAT-`/`TRACE-` directly. Closed by M-24. | Unverifiable provenance |
| AB-28 | Reads of `*.tfstate`, `*.tfvars`, `.env*`. Closed by M-28. | Secret disclosure |

## Required mitigations
Plan step stays `PLAN-0001 (to assign)` until the plan stage; `crosscheck.py` (M-06) checks it. Mitigation text is normative in SPEC-0001 section 11; named tests are in section 10.

| ID | Mitigation | SR / named test | Plan step |
|---|---|---|---|
| M-01 | Verifier computes changed files itself; code PR needs a code-stage report; `files` lists every changed non-docs file; workflow-iac report when `.github/` or `infra/` changed. | SR-031, SR-021 / `test_verify_fails_code_pr_without_stage_folder`, `test_verify_fails_on_changed_file_missing_from_report`, `test_verify_requires_workflow_iac_report_when_github_changed` | PLAN-0001 (to assign) |
| M-02 | `gate.py` sets status; SR findings only `accepted-risk` with a valid exception. | SR-031 / `test_verify_rejects_sr_finding_with_status_carried_or_fixed`, `test_gate_overrides_reviewer_status` | PLAN-0001 (to assign) |
| M-03 | Static `permissions.ask` for protected paths; fail-closed hook; Bash matcher; final PR lists protected changes. | SR-031 / `test_hook_fails_closed_on_malformed_input`, `test_hook_asks_for_bash_write_to_claude_dir`, `test_settings_ask_rules_cover_protected_paths` | PLAN-0001 (to assign) |
| M-04 | `/stage` refuses while the `sdlc-lab-admin` AWS session is live; deny rules for apply/destroy/seed variants. | SR-031, SR-028 / `test_stage_refuses_while_aws_admin_logged_in`, `test_hook_asks_for_terraform_and_make_apply_variants` | PLAN-0001 (to assign) |
| M-05 | `TRACE-`/`THREAT-` written by `write_artifact.py` from validated `artifact`; report records file hash; verifier checks. | SR-021, SR-031 / `test_verify_fails_on_edited_threat_file` | PLAN-0001 (to assign) |
| M-06 | `crosscheck.py` maps every `M-xx` and covered SR to a PLAN step with a named test. | SR-031 / `test_crosscheck_fails_on_threat_mitigation_without_task_and_test` | PLAN-0001 (to assign) |
| M-07 | Named tests in a separate read-only `tests` job; `verify` reads JUnit, runs no PR code. | SR-030 / `test_named_tests_fails_when_junit_missing`, `test_named_tests_fails_on_failed_test`, `test_verify_job_runs_no_pr_code` | PLAN-0001 (to assign) |
| M-08 | Gate escalates SR refs, blocking, high/critical, `needs_human`, prompt-injection, SR number in text with `NEW`. | SR-031 / `test_gate_escalates_new_blocking_finding`, `test_gate_escalates_sr_mentioned_in_text_with_new_ref` | PLAN-0001 (to assign) |
| M-09 | Lock/HEAD/clean check before each stage and gate; agents and scripts only from the checkout. | SR-027, SR-031 / `test_lock_check_fails_on_dirty_or_mismatched_checkout` | PLAN-0001 (to assign) |
| M-10 | Read denies for credential paths; `redact.py` covers PEM and netrc; any redaction escalates. | SR-026, SR-023 / `test_settings_deny_reads_credential_paths`, `test_redact_private_key_block`, `test_gate_escalates_on_redaction` | PLAN-0001 (to assign) |
| M-11 | Author write scope: current stage artifact; at code stage only files in this repo's PLAN section. | SR-031 / `test_hook_blocks_author_other_stage_artifact_and_reviews`, `test_hook_blocks_author_code_file_not_in_plan` | PLAN-0001 (to assign) |
| M-12 | `sr-exceptions.yml` schema-checked in CI and by the gate; malformed or expired = absent. | SR-031 / `test_exceptions_reject_over_180_days`, `test_exceptions_reject_missing_expiry`, `test_exceptions_reject_catch_all_glob`, `test_gate_ignores_malformed_exception` | PLAN-0001 (to assign) |
| M-13 | `verify.yml` pinned by SHA = lock; `--require-hashes`. | SR-027, SR-030 / `test_security_yml_verify_uses_sha_pin`, `test_verifier_requirements_have_hashes`, `test_workflow_pins_match_lock` | PLAN-0001 (to assign) |
| M-14 | Report strings stripped of markup, mentions, `::`, cut to 200; verifier touches only its own bot comments. | SR-030 / `test_comment_escapes_markup_and_mentions`, `test_logs_neutralise_workflow_commands`, `test_comment_cleanup_ignores_foreign_comments` | PLAN-0001 (to assign) |
| M-15 | `/stage` arguments validated; `classify.py` NUL-separated, submodule/typechange = code. | SR-001, SR-002 / `test_stage_rejects_unsafe_slug`, `test_classify_handles_nul_and_quoted_paths`, `test_classify_submodule_and_typechange_is_code` | PLAN-0001 (to assign) |
| M-16 | `deploy.yml` keeps `needs: [build, dast]`; EXC-001 scoped and expiring; new checks green before the swap apply. | SR-030 / `test_deploy_needs_dast`, `test_exc001_scoped_to_deploy_yml_and_expires`; manual | PLAN-0001 (to assign) |
| M-17 | `SKILL.md` untrusted-input rule; reviewer enum equals `stages.yml`. | SR-031 / `test_skill_states_untrusted_input_rule`, `test_review_schema_reviewer_enum_matches_stages_yml` | PLAN-0001 (to assign) |
| M-18 | Bootstrap only while base lacks `stages.yml`/lock; summary marked `BOOTSTRAP`; order: verify green, swap apply, merge. | SR-030 / `test_verify_bootstrap_only_when_base_lacks_files`, `test_verify_does_not_fall_back_when_base_has_files` | PLAN-0001 (to assign) |
| M-19 | CODEOWNERS adds `/stages.yml`, `/appsec-baseline.lock`, `/docs/specs/**/reviews/`; script-generated final-PR list of protected changes; owner review is the control for caller workflow. | SR-030, SR-031 / `test_codeowners_covers_protected_paths`, `test_final_pr_body_lists_protected_changes` | PLAN-0001 (to assign) |
| M-20 | Escalated NEW findings end fixed or `accepted-risk` via exception with `finding_id`; `carried` rejected on blocking/high/needs_human. | SR-031 / `test_verify_rejects_carried_blocking_or_high`, `test_gate_new_finding_accept_requires_exception` | PLAN-0001 (to assign) |
| M-21 | `disableBypassPermissionsMode`; start-up self-test that protected edit and merge into `main` prompt. | SR-031 / `test_settings_disable_bypass_mode`, `test_stage_refuses_unsafe_permission_mode` | PLAN-0001 (to assign) |
| M-22 | Lock check script in dogs-app; `--ignored` clean check; `python -I -B`. | SR-027 / `test_lock_check_detects_ignored_files`, `test_lock_check_script_outside_checkout` | PLAN-0001 (to assign) |
| M-23 | Exception uses listed in report, summary, final PR body; no top-level wildcards; new finding in covered file escalates once. | SR-031 / `test_verify_summary_lists_exceptions_used`, `test_exceptions_reject_top_level_wildcards` | PLAN-0001 (to assign) |
| M-24 | Hook denies main-session Write/Edit of `TRACE-`/`THREAT-`. | SR-031 / `test_hook_denies_main_session_write_trace_threat` | PLAN-0001 (to assign) |
| M-25 | JUnit parse: 5 MiB cap, no DOCTYPE/entity, fail closed. | SR-030 / `test_named_tests_rejects_doctype_and_oversize_junit` | PLAN-0001 (to assign) |
| M-26 | Contract test on recorded PreToolUse payloads; deny `agent_type` without `agent_id`; one manual run. | SR-031 / `test_hook_agent_id_contract`, `test_hook_denies_agent_type_without_agent_id` | PLAN-0001 (to assign) |
| M-27 | AWS preflight at every stage start; fails on AWS_* env credentials. | SR-031, SR-028 / `test_stage_preflight_rejects_aws_env_credentials` | PLAN-0001 (to assign) |
| M-28 | Read denies for tfstate, tfvars, .env*, pem, id_*; apply to Grep/Glob. | SR-026 / `test_settings_deny_reads_state_and_key_files` | PLAN-0001 (to assign) |
| M-29 | `SKILL.md` states memory/settings never override SR-031; owner memory entry on merge rules updated. Verification: see ARC-031. | SR-031 / `test_skill_states_untrusted_input_rule`; manual check of memory index | PLAN-0001 (to assign) |
| M-30 | CR/LF and control characters replaced by a space before log, summary, comment lines. | SR-024, SR-030 / `test_logs_neutralise_embedded_newlines` | PLAN-0001 (to assign) |

## Impact on the existing system
- **Weakened control, compensated:** project `Edit` denies and the Edit/Write-only hook are replaced by `ask` rules, a fail-closed hook, a Bash matcher (M-03), permission-mode self-test (M-21) and an `agent_id` contract test (M-26).
- **Verifier is the core control:** completeness (M-01, M-02, M-05, M-20), supply chain (M-13, M-22) and parsing (M-14, M-25, M-30) are covered. It still runs from workflow files chosen by the PR head; CODEOWNERS review at the owner's final merge is the control (M-19). Rulesets cover `main` only, so stage PR checks are advisory and the final PR re-verifies the whole diff.
- **Identity:** GitHub actions as the owner accepted; AWS reach handled by logout and env check (M-04, M-27).
- **Reduced attack surface:** `author.yml`, federation rules, service accounts, Claude App, `id-token: write` in `security.yml`, `ANTHROPIC_*` go.
- **Detection reduced:** no deploy-time tester; ZAP alerts do not stop deploys until 0002 (EXC-001).
- **Public exposure:** accepted; credential leakage handled by M-10, M-28.
- **Cost:** no CI API calls; `verify` capped at 15 minutes.

## Residual risk
- Accepted by the owner: owner login and bypass in the session; command-pattern rules do not stop `gh api` merges or `git push origin HEAD:main`; control is trust plus issue #12.
- Accepted: reviews are self-attested; a steered session can write a report and recompute hashes.
- Accepted: no stop on ZAP alerts until 0002 (EXC-001, expires 2026-12-31); open findings public.
- Remaining: workflow files in a PR are chosen by the PR; the owner's final-PR review of `.github/`, `stages.yml`, lock and exception list is the last gate. Forged JUnit pass equals a trivially passing test. Permission-mode and sandbox behaviour are best effort until the M-21 self-test passes on the owner's setup.
