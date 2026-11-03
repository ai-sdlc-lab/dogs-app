# Decisions for change 0004

| Stage | Decision | Why |
|---|---|---|
| intent | A well-formed breed with no images stays `404`. | SR-001 covers validation failures; the input is valid. |
| intent | Error code `invalid_input` in the 422 body; log `reason` `invalid_breed`. | Stable, short codes with no request data. |
| intent | `http.path` in `input.rejected` is the real request path without query string, JSON-encoded, truncated to 200 characters. | A route-pattern-only value was a deviation from SR-024 (AUD-001); the session cannot accept a MUST deviation. |
| intent | Source IP is logged for security monitoring only, kept 7 days. | AUD-003 (SR-025). |
| intent | AUD-002 (404 body not the SR-005 body) is old debt, left to #30. | Not altered by this change. |
| intent | Owner questions were answered by the session with the defaults above. | The intent author's open questions had conservative defaults; the run asks nothing of the owner. |
