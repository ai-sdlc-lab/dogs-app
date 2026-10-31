# THREAT-0002: threat model (security response headers, SR-004)

## Scope and change summary
Change 0002 adds three common headers to every response the app code produces (X-Content-Type-Options, Strict-Transport-Security, Referrer-Policy). It also adds an exact Content-Type with charset for text types, and CSP plus COOP on HTML responses only. The CSP image host is built from validated DOGS_BUCKET and AWS_REGION. The page gets an SR-003 check on image URLs (https on the S3 host pattern, text-only rendering). deploy.yml gains a ZAP gate on the SR-004 rules and a post-deploy smoke test of the real CSP. EXC-001 is narrowed. No new endpoint, data store, identity, IAM permission or AWS service. Out of the guarantee: Lambda platform-generated responses and S3 presigned image responses.

## Assets
- Integrity of what the browser executes and renders (CSP, nosniff, Content-Type).
- Private S3 bucket content, reachable only through 900 s presigned URLs.
- The function URL's HTTPS-only use by browsers (HSTS).
- Deploy pipeline integrity (OIDC role, deploy.yml, ZAP and smoke gates); no presigned URLs in logs.
- Availability and cost: unchanged (10 s timeout, 128 MB).

## Trust boundaries and data flows
| # | From → To | Data | Crosses boundary |
|---|---|---|---|
| 1 | Browser → Function URL / Lambda (app) | request path, headers (Host, Origin, X-Forwarded-*, Range, If-None-Match) | yes, untrusted input |
| 2 | App → Browser | body plus fixed security headers, CSP with image host | yes |
| 3 | Deployment settings (Terraform, Lambda env) → App | DOGS_BUCKET, AWS_REGION used to build the CSP host | yes, trusted but validated |
| 4 | App → S3 | list and presign | yes (unchanged) |
| 5 | Browser → S3 | image GET via presigned URL, allowed by CSP img-src | yes |
| 6 | API JSON → Page | breed and url strings rendered by the DOM code | yes, untrusted data |
| 7 | GitHub Actions → release container (ZAP) and deployed URL (smoke) | headers, report | yes |

## STRIDE per element
| Element | S | T | R | I | D | E | Notes |
|---|---|---|---|---|---|---|---|
| Header middleware / final-response point | n/a | mitigated: M-01, M-02, M-03 | n/a | mitigated: M-01 | mitigated: 500 and 304 paths covered | n/a | One app-wide point, set not append, applied after the last-resort 500 handler. Static handlers (304, 206, 416, 307) covered in 1.1 |
| Content-Type normalisation | n/a | mitigated: M-04 | n/a | n/a | n/a | n/a | The app's mapping wins over OS MIME tables, with a test that alters the table |
| CSP image-host builder | n/a | mitigated: M-05 | n/a | n/a | n/a | n/a | Fail closed on invalid settings. The host never comes from the request |
| Frontend renderer | n/a | mitigated: SR-003 test | n/a | n/a | n/a | n/a | Text-only rendering, https and S3 host check, CSP as a second layer, M-09 |
| Static files / StaticFiles | n/a | mitigated | n/a | n/a | n/a | n/a | 307, 206 and 416 are in the parametrised test |
| deploy.yml (ZAP gate, smoke test) | n/a | mitigated: M-07, M-08 | mitigated | mitigated: no presigned URLs in logs | n/a | mitigated: permissions {} kept | Pins and OIDC unchanged |
| S3 bucket / presigned URLs | n/a | n/a | n/a | n/a | n/a | n/a | Unchanged. The existing SR-006 and SR-022 gaps are tracked as D-9 and D-3 |

## Abuse cases
| ID | Attacker goal and steps | Impact |
|---|---|---|
| AC-01 | Inject headers or poison the CSP host: send hostile Host, X-Forwarded-Host, Origin, or CR/LF in the path or query | Mitigated by M-01 |
| AC-02 | Find a response without headers (500 from the S3 listing failing, 304, HEAD, 405, 307 redirect, 206, 416) and use it for sniffing or framing | Mitigated by M-03 |
| AC-03 | Cause duplicate or conflicting security headers, where the browser takes the weaker one or the first one | Mitigated by M-02 |
| AC-04 | Make a .js or .svg asset be served as another type through the host's MIME table, enabling sniff or type confusion | Mitigated by M-04 |
| AC-05 | Misconfigured, wildcard or dotted DOGS_BUCKET, or a wrong region, widens img-src to attacker hosts | Mitigated by M-05 (fail closed) and M-06 (smoke test) |
| AC-06 | Rely on ZAP passing while the real deployed CSP is wrong, because ZAP scans a kind container with a placeholder bucket | Mitigated by M-06. The spec states that ZAP proves presence only |
| AC-07 | Plant a breed or filename containing markup, or a javascript:/http: URL, in S3 keys so the page runs script or loads foreign images | Mitigated by SR-003 tests and M-09. CSP is the second layer |
| AC-08 | Later change adds an inline script or style, forcing unsafe-inline into the CSP | Mitigated by M-09 |
| AC-09 | Presigned URLs leak into workflow logs through the smoke test | Mitigated by M-08 |
| AC-10 | Cross-origin read of the API through a CORS preflight | Mitigated: no Access-Control-* headers, and a test covers it |

## Required mitigations
| ID (M-xx) | Mitigation | SR / named test | Plan step |
|---|---|---|---|
| M-01 | Header values are constants and never depend on request input | SR-004; test_headers_independent_of_request_input | to be mapped at the plan stage |
| M-02 | Each header appears exactly once, existing values are replaced, not appended | SR-004; test_security_headers, test_security_headers_replace_existing_values | plan |
| M-03 | One app-wide point on the final response, covering the 500 last-resort handler, 304, HEAD, 405, 307, 206 and 416 | SR-004; test_security_headers, test_security_headers_on_unhandled_error, test_not_modified_keeps_security_headers | plan |
| M-04 | Content-Type normalised to the exact values of 1.3 regardless of the runtime MIME table | SR-004; test_security_headers, test_content_type_exact_per_asset_type | plan |
| M-05 | The image host comes from validated bucket and region, equals the presigned host, CSP has no wildcard or unsafe source, fallback CSP when invalid | SR-004, SR-003; test_csp_has_no_unsafe_or_wildcard_sources, test_csp_falls_back_without_valid_bucket, test_csp_image_host_matches_presigned_url_host | plan |
| M-06 | The post-deploy smoke test checks the real CSP and fails on the fallback CSP or another host | SR-004; test_deploy_smoke_checks_security_headers | plan |
| M-07 | ZAP scans / and /api/health of a release container with the same web build, and the deploy stops on rules 10019, 10020, 10021, 10035, 10038, 10055 | SR-004; test_deploy_zap_gates_sr004_header_rules; zap-report evidence | plan |
| M-08 | Pins, permissions {} and minimal job permissions kept, and no presigned URLs in logs | SR-026, SR-027, SR-030; test_deploy_workflow_hardening_kept, test_deploy_logs_no_presigned_urls | plan |
| M-09 | No inline script or style, no event handlers, no eval, so the CSP needs no unsafe-* source | SR-004, SR-003; test_page_has_no_inline_code, test_breed_with_script_renders_as_text, test_frontend_rejects_non_https_or_foreign_image_urls | plan |

## Impact on the existing system
- No existing control is weakened. There is no IAM change, the bucket stays private, and CI permissions are unchanged. EXC-001 is narrowed, not widened.
- The attack surface shrinks: sniffing, framing and script injection are harder, and the page rejects foreign image URLs.
- The CSP could break the page if the host is wrong. The fail-closed fallback and the smoke test make this visible. Cost exposure is unchanged.
- Known gaps remain open and are not worsened: SR-005 (D-1), SR-006 (D-9), SR-022 TLS 1.2 (D-3), SR-007 and SR-024.

## Residual risk
- ZAP does not prove the real image host. The post-deploy smoke test does, and it runs after the deploy, so a bad CSP is detected after release, not before.
- Platform-generated responses and S3 image responses carry no app headers (accepted, INT item 9).
- Static header values are not reviewed against the Lambda adapter's header merging in production; the exact-once test runs on the test client only. The smoke test covers it on the deployed URL. Low risk.
- The open gaps D-1, D-3 and D-9 stay for the owner at the merge.
