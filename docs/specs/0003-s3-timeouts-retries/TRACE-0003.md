# TRACE-0003: security traceability

Requirements: appsec-baseline `requirements/security-requirements.md` @ `pinned commit in .appsec-baseline (sha not available to the auditor)`
Artifacts reviewed: SPEC-0003.md @ `working tree of stage/0003-spec, round 3` (with INT-0003.md and decisions.md as context)

## Triggers
| Trigger | True? | Why |
|---|---|---|
| INPUT | true | The existing `breed` path parameter is still accepted. Its handling is unchanged (SPEC §1.5, §2). |
| ENDPOINT | true | `GET /api/dogs` and `GET /api/dogs/{breed}` change their failure behaviour (503). |
| WRITE | false | No endpoint creates, changes or deletes data (SPEC §2). |
| FILE | false | The change accepts, stores and transforms no files. Presigned image URLs are built as before, with no change to how they are served (SPEC §1, §6). |
| AUTHN | false | The endpoints stay public and anonymous (SPEC §4). |
| AUTHZ | false | Visitors only; the data does not differ by caller (SPEC §5). |
| CRYPTO | true | A fallback `request_id` is a random UUID from a CSPRNG (SPEC §1.4). It is a correlation ID, not a token or secret. |
| DATA | false | No personal or sensitive data (SPEC §6). |
| LOG | false | The change adds no logging (SPEC §7). |
| SECRET | false | No credential is added. The existing execution role is reused (SPEC §4). |
| DEP | false | No dependency, tool or image is added or updated. |
| IAC | false | No infrastructure or IAM change. The function timeout stays 10 s as before (SPEC §3). |
| CI | false | No workflow change. |
| AI | false | The feature has no LLM or agent behaviour. |

## Requirements
| SR | Level | Status (covered / missing / N/A) | Where (artifact § and named test) | Justification |
|---|---|---|---|---|
| SR-001 | MUST | covered | SPEC §2 (`breed` pattern `^[a-z0-9-]{1,40}$`), §1.5, §8; `test_malformed_breed_404_without_s3_call` | No new input. The one existing input keeps its pattern and 40-character limit. The existing 404 (instead of 422) for a malformed breed is unchanged old behaviour. INT round 2 dropped it as out of scope. |
| SR-002 | MUST | covered | SPEC §8, §1.4; `test_503_ignores_request_id_header` | S3 keys come from the validated breed and the fixed prefix. The 503 path takes no request data. |
| SR-003 | MUST | covered | SPEC §1.4, §8; `test_dogs_s3_failure_returns_503` | The 503 body comes from the JSON serialiser. No frontend change. |
| SR-004 | MUST | covered | SPEC §1.6, §8; `test_503_has_security_headers` | The 503 carries the four required headers with exact values. |
| SR-005 | MUST | covered (change scope) | SPEC §1.4, §1.5, §7, §8; `test_s3_failure_body_has_no_detail`, `test_s3_failure_midway_returns_503`, `test_non_s3_error_not_503` | The 503 uses the fixed body `{"error","request_id"}` with no internal detail, and the operation fails closed with no partial list. Old gap D-1 of change 0002 (body format for 4xx/500, `error.unhandled`) is not altered by this change. |
| SR-006 | MUST | covered | SPEC §1.1 to §1.4, §3, §8; `test_s3_client_timeouts_configured`, `test_s3_client_retries_configured`, `test_at_most_three_attempts`, `test_dogs_s3_failure_returns_503`, `test_s3_hang_returns_503_before_function_timeout`, `test_abandoned_attempt_releases_resources` | Connect 3 s, read 5 s, 2 retries (3 attempts) with backoff, idempotent calls only. The 8 s total is below the 10 s function timeout. S3 failure gives 503 with no fallback, and abandoned attempts release resources. |
| SR-007 | MUST | covered | SPEC §3, §8; `test_s3_overall_deadline_is_8s` | Function timeout stays 10 s with a margin of at least 2 s. No write or heavy endpoint is added. Reserved concurrency is a documented lab exception. |
| SR-008 | MUST | N/A | FILE is false | No upload. |
| SR-009 | MUST | N/A | FILE is false | No upload. |
| SR-010 | MUST | N/A | FILE is false | No image processing. |
| SR-011 | MUST | N/A | FILE is false | No image processing. |
| SR-012 | MUST | N/A | FILE is false | No new storage keys. |
| SR-013 | MUST | N/A | FILE is false | Image serving is not changed. |
| SR-014 | MUST | N/A | FILE is false | No upload. |
| SR-015 | MUST | N/A | FILE and WRITE are false | No writes. |
| SR-016 | MUST | N/A | AUTHN is false | No authentication change. |
| SR-017 | MUST | N/A | AUTHN is false | No authentication change. |
| SR-018 | MUST | N/A | AUTHN and AUTHZ are false | No tokens. |
| SR-019 | MUST | N/A | AUTHN is false | No tokens or cookies. |
| SR-020 | MUST | N/A | AUTHZ and WRITE are false | Public read-only endpoints; the SPEC §5 matrix is unchanged. |
| SR-021 | MUST | covered | SPEC §1.4, §8; `test_503_request_id_generated_when_missing` | The fallback ID is a UUID v4 from a CSPRNG. It is a non-secret correlation ID, so it needs no crypto inventory entry. |
| SR-022 | MUST | covered | SPEC §8 | The S3 endpoint stays https with certificate validation on. This change disables nothing. |
| SR-023 | MUST | N/A | IAC, FILE and DATA are false | No store is changed. |
| SR-024 | MUST | N/A (accepted risk) | SPEC §7, §10 M-08; decisions.md spec stage row | The INPUT trigger is old and unaltered, and this change adds no logging. The lack of an S3-failure log record is a documented accepted risk with a detection route (operator alarm) and a follow-up suggested. This closes round-2 AUD-001. |
| SR-025 | MUST | N/A | DATA is false | No personal data (SPEC §6). |
| SR-026 | MUST | N/A | SECRET, CI and IAC are false | No secrets. |
| SR-027 | MUST | N/A | DEP and CI are false | No dependency change. |
| SR-028 | MUST | N/A | IAC is false | No IAM change. |
| SR-029 | MUST | N/A | IAC is false | No resource change. |
| SR-030 | MUST | N/A | CI is false | No workflow change. |
| SR-031 | MUST | N/A | AI and CI are false | The feature has no agent behaviour. |

## Summary
Covered: 9 · Missing: 0 · N/A: 22
