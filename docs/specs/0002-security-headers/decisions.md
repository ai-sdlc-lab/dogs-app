# Decisions for change 0002 (session)

| # | Stage | Decision | Why |
|---|---|---|---|
| S-1 | spec | Stopped the fix rounds after round 2 for AUD-002 (SR-005 error body), AUD-003 (SR-006 timeouts/retries/503), AUD-004 (SR-022 S3 TLS-version deny). They stay `open` (high) for the owner at the merge to `main`. | The gaps are in existing code and infra; the owner-approved INT-0002 (item 7, item 8, out of scope) fixes bodies, status codes and infra as unchanged. A third round could only widen the intent, and the session may not ask the owner after the intent stage. |
| S-2 | spec | Accepted the author's added SR-003 frontend check (spec 1.6a): the page shows an image only for an `https:` URL on the expected S3 host. | Fixes AUD-001 (high). It is a small web change; with real data the page looks the same. An entry that fails the check is silently left out. |
| S-3 | spec | Accepted the author's choice to narrow EXC-001 (not remove it), expiry unchanged (2026-12-31); the ZAP gate stops the deploy only on the six SR-004 header rules (10019, 10020, 10021, 10035, 10038, 10055). | Other ZAP alerts (e.g. 10063 Permissions-Policy) would need headers SR-004 does not require. The edit to `security/exceptions.yml` happens at the code stage, not now. Owner to confirm at the merge. |
| S-4 | spec | Round 2 re-ran only the auditor and the architect; spec-completeness passed in round 1 and was not re-run. | Stage rule: a reviewer that passed is not run again. |
| S-5 | code | The three `.github/` workflow edits (ci.yml, security.yml, deploy.yml) were applied by the main session, not the author. | The author subagent's scope blocks `.github/` writes. The plan lists these files for the code stage; the edits are the author's text, verbatim, plus the review fixes below. |
| S-6 | code | Fixed IAC-001 (ZAP gate now fails closed: scan errors exit 1, each report must have a `site`) and IAC-002 (presigned URL masked in the log). | Workflow reviewer findings (medium, low). |
| S-7 | code | HSTS (ZAP rule 10035) and the real CSP are enforced by the post-deploy smoke test and by `test_security_headers`, not by ZAP: the kind scan is plain HTTP, so rule 10035 does not fire there. PLAN-0002 not changed for this note. | IAC-001 note. ZAP still gates the other five SR-004 rules. |
| S-8 | code | Two test-code corrections by the session in `tests/process/test_deploy.py`: the base-image regex ignores the literal `\n` of the `printf`; the presigned-URL test allows the `::add-mask::` echo and asserts it exists. | The tests were stricter than their intent; both changes keep the check (no new base image, no URL printed). |
| S-9 | code | `tflint` is not installed locally, so `make lint` was not run to the end; ruff, ruff format, tsc and terraform fmt passed. CI runs tflint. | Local tool missing; CI is the check. |

Author decisions D-1 to D-9 are in SPEC-0002.md ("Decisions made by the author").
