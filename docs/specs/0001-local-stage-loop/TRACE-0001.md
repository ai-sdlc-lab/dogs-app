# TRACE-0001: security traceability

<!-- Written by the security-requirements-auditor. Do not edit by hand. -->

Requirements: appsec-baseline `requirements/security-requirements.md` (working tree; commit SHA not available to the auditor; SR-031 assessed with the amended text in SPEC-0001 §9, because the file still carries the old wording until the amendment lands)
Artifacts reviewed: SPEC-0001.md (stage: spec, round 3; §11 normative) with INT-0001.md and reviews/INT-0001-status.md as context (working tree; commit SHA not available to the auditor)

## Triggers
| Trigger | True? | Why |
|---|---|---|
| INPUT | true | The verifier, `classify.py`, `hash.py`, `validate.py`, `write_artifact.py` and the gate parse review reports, reviewer artifacts, file names, diffs and `/stage` arguments that come from PRs or agents (SPEC §2.1, §2.2, §2.5, M-05, M-15). |
| ENDPOINT | false | No HTTP endpoint or served page is added or changed; no change to the dogs-app API or UI (INT-0001 Visual: none). |
| WRITE | false | No caller creates, changes or deletes application data; the loop writes git artifacts only. |
| FILE | false | No file upload, storage or serving in the app; review reports are small git-tracked JSON files, not user file handling. |
| AUTHN | false | No change to how callers or operators are identified; the session keeps the owner's existing GitHub login (SPEC §4, owner decision 2026-10-28; issue #12 parked). |
| AUTHZ | true | SPEC §5 defines an authorisation matrix for owner, main session, subagents and CI, enforced by hook, permission rules and GitHub. |
| CRYPTO | true | SHA-256 over file contents binds reports to files (SPEC §2.2, §9 SR-021, M-05). |
| DATA | true | Artifacts, reports, exceptions, logs, prompts and transcripts are stored and transmitted; SPEC §6 inventories them (no personal data claimed). |
| LOG | true | SPEC §7 adds JSON Lines events from hook, gate, loop and verifier, plus job logs and summaries. |
| SECRET | true | CI uses `GITHUB_TOKEN`; the session holds the owner's login; federation rules, service accounts and variables are removed (SPEC §4, §8, M-10, M-28). |
| DEP | true | New scripts, a reusable workflow, pinned tools and the appsec-baseline lock (SPEC §2.1, §2.5, §2.6). |
| IAC | true | lab-admin `github.tf` changes (required checks, variables, labels, allowlist; SPEC §8). No AWS or IAM change. |
| CI | true | New `verify.yml`, `security.yml` changes, `tests` job, `security-gate`, `deploy.yml` job removed (SPEC §2.5-2.7, §8, M-07). |
| AI | true | The change adds the local agent loop, agent tools, models and gate (SPEC §1, §2.3, §11 M-17). |

## Requirements
| SR | Level (MUST/SHOULD) | Status (covered / missing / N/A) | Where (artifact § or test) | Justification |
|---|---|---|---|---|
| SR-001 | MUST | covered | SPEC §2.2 limits tables (patterns, lengths, entry caps, 256 KiB), M-05 (artifact 256 KiB, UTF-8, control characters), M-15 (slug identical to §1.1); tests `test_report_schema_rejects_unknown_fields_and_oversize`, `test_report_schema_rejects_bad_paths_control_chars_and_long_strings`, `test_stage_rejects_unsafe_slug` | Schema has `additionalProperties: false`, per-field patterns and maximum lengths; reviewer output `artifact` is bounded; failures are logged as `input.rejected` (§7). HTTP 422 and 64 KiB body rules do not apply (no HTTP input). |
| SR-002 | MUST | covered | SPEC §2.1 (paths resolved and confined, argument-list subprocesses of fixed executables, `safe_load`), §2.6 (Semgrep on code PRs and on appsec-baseline PRs); tests `test_hash_rejects_path_outside_repo_and_symlink`, `test_classify_handles_nul_and_quoted_paths`; EXC-001 for the deploy gap (§1.8, §2.4, M-16) | Concrete rules and scanner evidence stated. The deploy gap is a documented, expiring exception (2026-12-31, scoped to `deploy.yml`). |
| SR-003 | MUST | covered | SPEC §1.7 (fenced code, backticks replaced, `@` neutralised, no links or images, 200-char cut), M-14, M-30; tests `test_comment_renders_untrusted_text_inert`, `test_comment_escapes_markup_and_mentions`, `test_security_review_no_comment_on_allow` | INPUT is true. Untrusted text in comments, summaries and log lines is rendered inert, with named tests. |
| SR-004 | MUST | N/A | - | ENDPOINT is false: no response is produced or changed. |
| SR-005 | MUST | N/A | - | ENDPOINT is false: no API error responses are added. Script errors fail closed (§7). |
| SR-006 | MUST | N/A | - | ENDPOINT and FILE are false: no application outbound calls. |
| SR-007 | MUST | N/A | - | WRITE, FILE and ENDPOINT are false: no function, write path or memory setting changes. Job timeouts are covered under SR-030. |
| SR-008 | MUST | N/A | - | FILE is false: no uploads. |
| SR-009 | MUST | N/A | - | FILE is false: no uploads. |
| SR-010 | MUST | N/A | - | FILE is false: no image handling. |
| SR-011 | MUST | N/A | - | FILE is false: no image handling. |
| SR-012 | MUST | N/A | - | FILE is false: no storage keys. |
| SR-013 | MUST | N/A | - | FILE is false: nothing is served from storage. |
| SR-014 | MUST | N/A | - | FILE is false: no uploads to scan. |
| SR-015 | MUST | N/A | - | FILE and WRITE are false: no user quota. |
| SR-016 | MUST | N/A | - | AUTHN is false: no change to user sign-in; no application passwords. |
| SR-017 | MUST | N/A | - | AUTHN is false; owner-account MFA is out of scope by owner decision (SPEC §9, INT-0001-status.md). |
| SR-018 | MUST | N/A | - | AUTHZ is true, but no bearer token is accepted or validated by code in this change; `GITHUB_TOKEN` is validated by GitHub. |
| SR-019 | MUST | N/A | - | AUTHN is false: no browser tokens or cookies. |
| SR-020 | MUST | covered | SPEC §5 matrix and default-deny hook rule, M-03, M-11, M-24, M-26; tests in §10: `test_hook_blocks_author_other_stage_artifact_and_reviews`, `test_hook_blocks_author_code_file_not_in_plan`, `test_hook_blocks_subagent_edit_github_and_trace_threat`, `test_hook_denies_main_session_direct_trace_threat_write`, `test_hook_denies_main_session_github_edit_outside_code_stage`, `test_hook_asks_for_claude_dir_edit_in_main_session`, `test_hook_asks_before_merge_into_main`, `test_settings_deny_apply_and_ask_protected_files`, `test_agents_have_no_shell_or_network_tools`, `test_verify_job_permissions_minimal` (CI column) | Every matrix cell has a mechanism and a named test. Server-side identity from a validated token and cross-user access do not apply (single owner, no per-user data). The session-holds-owner-login residual is an owner decision (SPEC §5, issue #12) and is not re-raised. |
| SR-021 | MUST | covered | SPEC §2.2, §9, §8 (BASELINE crypto inventory entry); tests `test_hash_rejects_path_outside_repo_and_symlink`, `test_workflow_pins_match_lock` | SHA-256 via `hash.py`; no SHA-1 object IDs, no custom crypto, no random values generated. |
| SR-022 | MUST | covered | SPEC §6 last paragraph | All connections made by scripts and workflows (GitHub API, git, `gh`) use HTTPS with certificate validation; no `http://`, `--insecure`, `verify=False`; Semgrep rules on code PRs. No S3 or endpoint change. |
| SR-023 | MUST | covered | SPEC §6 (GitHub-managed encryption at rest, algorithm unverified and recorded as a BASELINE known gap; laptop under FileVault; no new data store; no Terraform state change beyond `github.tf`), `redact.py`, gitleaks | No new data store is provisioned and CI artifacts carry no personal data. The AES-256 gap for GitHub-managed stores is declared as a documented lab gap; the BASELINE entry itself should be added with the other BASELINE edits in §8 during the plan. |
| SR-024 | MUST | covered | SPEC §7 (JSON Lines; `ts`, `level`, `service`, `version`, `event`, `outcome`, `reason`, `actor`, `change`, `stage`, `request_id`; `source_ip`, `http`, `resource` stated not applicable; event list incl. `authz.denied`, `input.rejected`; never-logged list incl. cookies, bodies, emails, names), M-14, M-30; tests `test_log_events_have_required_fields_and_no_secrets`, `test_logs_neutralise_workflow_commands`, `test_logs_neutralise_embedded_newlines` | Fields and never-logged list match SR-024 for non-HTTP events; control characters cannot forge entries. |
| SR-025 | MUST | covered | SPEC §6 data inventory table (purpose, storage, retention, personal data; includes content sent to the model provider and local session transcripts) | No personal data; no trackers; all stores listed with retention. |
| SR-026 | MUST | covered | SPEC §4, §6, §8, §9, M-10, M-28; tests `test_redaction_escalates`, `test_redact_private_key_block`, `test_settings_deny_reads_credential_paths`, `test_settings_deny_reads_state_and_key_files`; gitleaks on every PR | No new secrets; only `GITHUB_TOKEN`; Anthropic federation rules, service accounts, variables and App removed; redaction before write and any redaction escalates; credential-file read denies. |
| SR-027 | MUST | covered | SPEC §2.5 (lock SHA reachable from `main`, `uses:` ref = lock, actions SHA-pinned from BL-01, `pip --require-hashes`), §2.6 (scanners job on dogs-app code PRs and on appsec-baseline PRs incl. OSV-Scanner on the hashed lockfile; tool pins and SHA-256 kept), M-13; tests `test_workflow_pins_match_lock`, `test_security_yml_verify_uses_sha_pin`, `test_verifier_requirements_have_hashes` | Pins, hashes and scanning are specified for both repos. |
| SR-028 | MUST | N/A | - | IAC is true, but no IAM policy, role or trust policy is added or changed; the apply touches GitHub rulesets, variables, labels and allowlist only (SPEC §8). |
| SR-029 | MUST | N/A | - | IAC is true, but no S3 bucket, resource policy or AWS resource is added or changed. |
| SR-030 | MUST | covered | SPEC §2.5 (`pull_request`, workflow `permissions: {}`, job `contents: read` and `pull-requests: write`, `persist-credentials: false`, 15 min, env-only), §2.7 (`security-gate`: `permissions: {}`, 5 min, `always()`, fails on skipped or cancelled), M-07 (`tests` job: `contents: read`, 20 min), M-19 (CODEOWNERS); tests `test_verify_job_permissions_minimal` (all jobs have timeout at most 30), `test_security_gate_fails_on_skipped_need`, `test_codeowners_covers_protected_paths`, `test_workflow_pins_match_lock` | All new jobs have stated permissions and timeouts. The caller workflow being chosen by the PR head is a documented residual controlled by the owner's review of the final PR (M-19). |
| SR-031 | MUST | covered | SPEC §1.3, §2.3, §5, §9 (amended text), M-08, M-09, M-17, M-21, M-26, M-29; tests `test_agents_match_spec_table`, `test_agents_have_no_shell_or_network_tools`, `test_gate_escalates_any_sr_finding`, `test_gate_escalates_prompt_injection`, `test_hook_asks_before_merge_into_main`, `test_settings_disable_bypass_mode` | Allow lists, read-only reviewers, full model IDs, maxTurns, untrusted-input rule, schema-validated output, escalation of invalid output and injection. Against the amended text, merging into `main` needs the owner; the owner-login residual and self-attested reviews are owner decisions and are not re-raised. |

## Summary
Covered: 13 · Missing: 0 · N/A: 18

Round 2: AUD-001 to AUD-008 resolved. Round 3: no new findings.
