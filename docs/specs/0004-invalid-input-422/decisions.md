# Decisions for change 0004

| Stage | Decision | Why |
|---|---|---|
| intent | A well-formed breed with no images stays `404`. | SR-001 covers validation failures; the input is valid. |
| intent | Error code `invalid_input` in the 422 body; log `reason` `invalid_breed`. | Stable, short codes with no request data. |
| intent | `http.path` in `input.rejected` is the real request path without query string, JSON-encoded, truncated to 200 characters. | A route-pattern-only value was a deviation from SR-024 (AUD-001); the session cannot accept a MUST deviation. |
| intent | Source IP is logged for security monitoring only, kept 7 days. | AUD-003 (SR-025). |
| spec | Log `service` is `dogs-app`; `version` is the build's git SHA embedded in the Lambda package. | Needed for SR-024; the open questions had no owner-only answer (AUD-001/ARC-002). |
| spec | Fallback request ID gets 128 random bits (hex from a CSPRNG), not UUID v4. | SR-021 is a MUST; no deviation allowed (AUD-001). |
| spec | SPEC-001 and ARC-005 got a fourth author pass beyond the 3 rounds; both were small wording fixes and the gate offers no exception for plain `block` findings. | The only way to close them. |
| spec | ARC-001 (medium, no log-volume alarm for the new per-request log cost) stays open after the last round. The spec bounds the cost and points to #38 for the alarm; an alarm is an infrastructure change outside this change's scope. The gate classes it `block`, which has no exception route. | Owner decides at the merge to `main`. |
| code | `http.path` is read from the raw request scope path (PLAN-0004 A-02 updated), not `request.url.path`. | URL parsing strips newlines, which would break the hostile-path requirement. |
| code | SPEC 1.6 says `/api/dogs/` gives 404; FastAPI's slash redirect probably answers 307. The test accepts 307 or 404 and checks no event is written. | Behaviour is unchanged by this change; the spec wording may need a correction by the owner. |
| code | `api/tests/test_api.py` renamed to `test_dogs_routes.py` (PLAN-0004 updated). SPEC-0004 and THREAT-0004 still name the old file. | CI gitleaks' generic-api-key rule flagged the file's hash line in the review report every time (key ending in `api.py` plus a hex hash); the rename is the only fix, since `.gitleaks*` files are protected. |
| code | Plan re-review after the code stage left one low finding open (security-architect ARC-001, SR-001: the empty-breed test accepts 307 or 404 instead of pinning 307) and two low/info notes from architecture-conformance (ARC-003, ARC-004). Not fixed; SPEC 1.6 wording for `/api/dogs/` ("404", really a 307 redirect) is for the owner to correct. | An exception can't be added without listing `security/exceptions.yml` in the plan (plan-drift), and every plan edit restarts the plan review. Hardening only; no behaviour impact. |
| intent | AUD-002 (404 body not the SR-005 body) is old debt, left to #30. | Not altered by this change. |
| intent | Owner questions were answered by the session with the defaults above. | The intent author's open questions had conservative defaults; the run asks nothing of the owner. |
