# INT-0001 review status

Reviewed by hand-run subagents (the stage loop doesn't exist yet), plus the old CI reviewers on the PR (API credits). Round 1: Opus 5.5. Round 2: intent-completeness on Haiku 4.5, requirements auditor on Sonnet 5.5.

| Finding | Status | Note |
|---|---|---|
| Round 1 IC-001..010, AUD-001..009 | fixed / owner-decided | owner decisions 2026-10-27: deploy gap until 0002 accepted; open findings may be public; Claude GitHub App uninstalled at clean-up; reviewers on smaller models; standing merge/apply permissions removed; account MFA out of scope |
| IC-201 push hook | no change | already listed under Out of scope |
| IC-202 multi-repo code stage | fixed | one PLAN section and one code PR per repo; plan drift per repo |
| IC-203 author model | fixed | author on Opus 5.5 for all stages |
| AUD-001 (round 2) exception expiry | carried → spec | record the deploy-gap exception in appsec-baseline `exceptions/` with SR-002/020/024, reason, calendar expiry |
| AUD-002 (round 2) model IDs, maxTurns | carried → spec | full model IDs, maxTurns, tool allow lists and enforcement per agent, with named tests |
| ARC-001 read-only not enforced (CI architect, high) | fixed | subagents: no shell/network tools, allow lists in agent definitions |
| ARC-002 session acts as owner with bypass (high) | fixed | merge, --admin, push to main, make apply denied in committed project settings |
| ARC-003 verifier runs from the PR it checks (high) | fixed | verifier + scripts run from appsec-baseline at a pinned commit |
| ARC-004 protected paths vs. stage loop (high) | fixed | .github/, .claude/, TRACE-/THREAT- writable by the main session only |
| ARC-005..010 (medium/low), ARC-011 (info) | carried → spec | pin changes, report parsing, empty-report manipulation, path classification edge cases, required-check ordering, redaction before commit |
| ARC-001 (re-run) main session could edit `.claude/` and remove its own denies (high) | fixed | no agent edits `.claude/` without per-edit owner approval |
| ARC-002 (re-run) command-pattern denies are bypassable; session uses the owner's login (high) | carried → spec (owner decision 2026-10-27) | goal stated in the intent; enforcement (separate GitHub identity) decided in the spec. Exposure reduced by the feature-branch pattern: stage PRs never touch `main` |

Branching changed 2026-10-27 (owner): one feature branch per change, stage PRs into it, one final PR to `main`. This PR replaces #8.

Verdict: allow (no open findings; two carried to the spec stage).
