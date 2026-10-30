# Decisions for change 0002 (session)

| # | Stage | Decision | Why |
|---|---|---|---|
| S-1 | spec | Stopped the fix rounds after round 2 for AUD-002 (SR-005 error body), AUD-003 (SR-006 timeouts/retries/503), AUD-004 (SR-022 S3 TLS-version deny). They stay `open` (high) for the owner at the merge to `main`. | The gaps are in existing code and infra; the owner-approved INT-0002 (item 7, item 8, out of scope) fixes bodies, status codes and infra as unchanged. A third round could only widen the intent, and the session may not ask the owner after the intent stage. |
| S-2 | spec | Accepted the author's added SR-003 frontend check (spec 1.6a): the page shows an image only for an `https:` URL on the expected S3 host. | Fixes AUD-001 (high). It is a small web change; with real data the page looks the same. An entry that fails the check is silently left out. |
| S-3 | spec | Accepted the author's choice to narrow EXC-001 (not remove it), expiry unchanged (2026-12-31); the ZAP gate stops the deploy only on the six SR-004 header rules (10019, 10020, 10021, 10035, 10038, 10055). | Other ZAP alerts (e.g. 10063 Permissions-Policy) would need headers SR-004 does not require. The edit to `security/exceptions.yml` happens at the code stage, not now. Owner to confirm at the merge. |
| S-4 | spec | Round 2 re-ran only the auditor and the architect; spec-completeness passed in round 1 and was not re-run. | Stage rule: a reviewer that passed is not run again. |

Author decisions D-1 to D-9 are in SPEC-0002.md ("Decisions made by the author").
