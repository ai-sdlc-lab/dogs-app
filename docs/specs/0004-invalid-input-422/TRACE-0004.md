# TRACE-0004: security traceability

Requirements: appsec-baseline `requirements/security-requirements.md` @ `pinned commit in .appsec-baseline (sha not available to the auditor)`
Artifacts reviewed: SPEC-0004.md @ `working tree of stage/0004-spec, round 3` (with INT-0004.md and decisions.md as context)

## Triggers
| Trigger | True? | Why |
|---|---|---|
| INPUT | true | The `breed` path value of `GET /api/dogs/{breed}` is external input and is validated (SPEC §1.1, §2). |
| ENDPOINT | true | The response of `GET /api/dogs/{breed}` changes to a 422 for invalid input (SPEC §1.2). |
| WRITE | false | No endpoint creates, changes or deletes data (SPEC §2, §5). |
| FILE | false | No file is accepted, stored or transformed (SPEC §9 last row). |
| AUTHN | false | The API is public and anonymous. `actor` is always `anonymous` (SPEC §4). |
| AUTHZ | false | No roles or per-caller data (SPEC §5). |
| CRYPTO | true | The fallback request ID is 128 random bits from a CSPRNG (SPEC §1.4). |
| DATA | true | The source IP address is logged and kept for 7 days (SPEC §6). |
| LOG | true | The new `input.rejected` event is added (SPEC §7.2). |
| SECRET | false | No credential or key is used (SPEC §9, SR-026 row). |
| DEP | false | No dependency, tool or image is added or changed (SPEC §9, SR-027 row). |
| IAC | false | No infrastructure or IAM change (SPEC §6, §3). |
| CI | false | No workflow change. The build embeds build info through `make build` only (SPEC §8 M-11). |
| AI | false | No agent or LLM behaviour changes (SPEC §9, SR-031 row). |

## Requirements
| SR | Level | Status (covered / missing / N/A) | Where (artifact § and named test) | Justification |
|---|---|---|---|---|
| SR-001 | MUST | covered | SPEC §1.1, §1.2, §1.5, §2, §8 M-01; `test_dogs_by_breed_rejects_malformed_breed`, `test_dogs_by_breed_accepts_boundary_breeds` | Breed is 1 to 40 characters of `a-z0-9-`, whole-value match, valid UTF-8, control characters rejected. There is no body, number or enum input. Failure gives 422 with the SR-005 body and `input.rejected`. |
| SR-002 | MUST | covered | SPEC §1.2, §1.2a, §9; `test_dogs_by_breed_rejects_without_s3_call`, `test_listing_skips_key_with_trailing_newline` | S3 prefix is the fixed `dogs/` plus the validated breed. Returned keys are re-checked with the same whole-value rule. No interpreter is applied to request data. |
| SR-003 | MUST | covered | SPEC §1.3, §9; `test_rejected_body_has_no_request_data` | The 422 body comes from the JSON serialiser and holds two fixed keys. No frontend change. |
| SR-004 | MUST | covered | SPEC §7.1, §9; `test_security_headers` (422 case) | Exact four header values on the 422. No CORS headers. |
| SR-005 | MUST | covered (change scope) | SPEC §1.2 to §1.5, §9; `test_rejected_body_has_no_request_data`, `test_framework_validation_error_uses_invalid_input_body`, `test_rejected_still_422_when_log_write_fails` | The validation failure uses the fixed body with no internal detail and fails closed. The last-resort handler, the SR-005 body for other 4xx and 500, and `error.unhandled` stay with #30 (old debt, see AUD-002). |
| SR-006 | MUST | covered | SPEC §9; `test_s3_client_timeouts_configured`, `test_s3_client_retries_configured` | No outbound call is added. Current values: connect 3 s, read 5 s, 2 retries, 8 s deadline. |
| SR-007 | MUST | covered | SPEC §3, §9 | Timeout 10 s, memory 128 MB, no write or heavy work. Reserved concurrency is a documented lab exception. |
| SR-008 | MUST | N/A | FILE is false | No upload. |
| SR-009 | MUST | N/A | FILE is false | No upload. |
| SR-010 | MUST | N/A | FILE is false | No image processing. |
| SR-011 | MUST | N/A | FILE is false | No image processing. |
| SR-012 | MUST | N/A | FILE is false | No new storage keys. |
| SR-013 | MUST | N/A | FILE is false | Serving is unchanged. |
| SR-014 | MUST | N/A | FILE is false | No upload. |
| SR-015 | MUST | N/A | FILE and WRITE are false | No writes. |
| SR-016 | MUST | N/A | AUTHN is false | No authentication. |
| SR-017 | MUST | N/A | AUTHN is false | No accounts. |
| SR-018 | MUST | N/A | AUTHN and AUTHZ are false | No tokens. |
| SR-019 | MUST | N/A | AUTHN is false | No tokens or cookies. |
| SR-020 | MUST | N/A | AUTHZ and WRITE are false | Public read-only endpoints (SPEC §5). |
| SR-021 | MUST | covered | SPEC §1.4, §9; `test_generated_request_id_is_128_bit_hex` | The fallback ID has 128 random bits from a CSPRNG, 32 hex characters. The 503 test is updated to match. |
| SR-022 | MUST | covered | SPEC §9 | No new listener or connection. HSTS is kept in the 422 headers. |
| SR-023 | MUST | covered | SPEC §6, §9 | Log events go to the existing CloudWatch log group, encrypted at rest with the AWS-managed default. This is the documented lab exception. |
| SR-024 | MUST | covered | SPEC §7.2, §7.3, §7.3b, §8 M-03, M-06, M-07, M-11, §9; `test_rejected_logs_input_rejected_event`, `test_rejected_log_is_single_line_json_for_hostile_path`, `test_rejected_log_path_truncated_to_200`, `test_rejected_log_path_has_no_query_string`, `test_rejected_log_source_ip_from_context_not_xff`, `test_rejected_log_version_from_build_info` | JSON Lines with all mandatory fields and exact values. The path has no query string and is capped at 200 characters. The IP comes from the context. The never-logged list is stated. The 7-day retention is the lab exception. Other mandatory events belong to #38. |
| SR-025 | MUST | covered | SPEC §6, §9 | The data inventory gives purpose, storage and retention for the source IP and the path. No third parties. |
| SR-026 | MUST | N/A | SECRET, CI and IAC are false | No secret is used. |
| SR-027 | MUST | N/A | DEP and CI are false | No dependency change. |
| SR-028 | MUST | N/A | IAC is false | No IAM change. |
| SR-029 | MUST | N/A | IAC is false | No resource change. |
| SR-030 | MUST | N/A | CI is false | No workflow change. |
| SR-031 | MUST | N/A | AI and CI are false | No agent behaviour changes. The spec still treats logged paths as data (SPEC §7.3b). |

## Summary
Covered: 12 · Missing: 0 · N/A: 19
