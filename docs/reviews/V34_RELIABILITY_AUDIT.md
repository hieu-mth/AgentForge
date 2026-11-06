# AgentForge V3.4 — Reliability review and acceptance plan

## Scope and evidence

Source-level audit of the GitHub `main` tree (359 entries) and changes in this
branch. Reviewed the Python/React boundaries, 24 allowlisted skill manifests,
owner grants, S4 orchestration, AI model adapter, website builder/quality/preview,
and the Windows CI workflow. This is **not** an independently executed full
system acceptance test; live Ollama/Anthropic, hardware/browser and local data
remain on the owner's Windows machine.

## Priority findings

| Priority | Finding | Action/status |
| --- | --- | --- |
| P0 | `web.create` asked a small model to produce executable HTML/CSS and then rejected remote/active strings. Real owner runs repeatedly failed `BUILDER_INVALID_OUTPUT`, `HTML_UNSAFE_CONTENT`, `HTML_ACTIVE_CONTENT`. | **Fixed in branch:** request structured Vietnamese copy and compile it into fixed HTML/CSS. One model call, no auto retry or downgraded safety. Live model test still needed. |
| P0 | Successful website Goal's 'View result' opened a task with an empty JSON report rather than a visual proposal. | **Fixed in branch:** route to the existing SHA-verified, isolated proposal preview. |
| P1 | Many UI skill names remain raw English API identifiers. | **Fixed in branch:** Vietnamese labels for all 24 skill manifests, with a test that fails if a new skill has no label. |
| P1 | The older raw-HTML builder path remains exposed to injected `model_client` legacy integration/tests. | **Contained:** separate legacy branch still uses the original strict validation, no automatic model code execution; not the production `web.create` path. |
| P1 | AI copy can still invent claims; structured JSON is not a truth guarantee. | **Partially mitigated:** constrained prompting, bounded plain-text fields, no automatic commercial facts; human content review remains mandatory. |
| P1 | Contact details are unavailable unless provided by the owner. | **Mitigated:** only explicitly supplied and recognized VN mobile numbers become `tel:` links; otherwise clearly disclose missing contact info. |
| P2 | Placeholder visuals cannot represent real merchandise or professional photos. | **Open:** approved user-provided images are needed for true product authenticity and production-level visual evaluation. |
| P2 | AI model runtime, real browser output and Windows filesystem behavior have not been verified in this environment. | **Open:** owner Windows acceptance and CI. |

## What must remain true

- Only one `generate_json` call per approved `web.create` dispatch, with
  Ollama JSON schema (or compatible cloud JSON contract).
- No raw model HTML, inline JS, remote images, tracking or network access in the
  generated offline website.
- Generated strings are escaped for HTML text contexts only. The renderer does
  not place model text into CSS, script, or URL-bearing attributes. This follows
  OWASP output-encoding guidance.
- The existing `_validate_files` and C8C static quality gates still run before
  writing an immutable, SHA-bound proposal.
- Applying a proposal still requires separate owner SHA review and approval.
  No automatic write to `workspace/products`, no publish, spending or model
  retries on failure. No changes or deletions of `data/` or `workspace/`.
- The generic `SUCCEEDED` task status means the **draft proposal was prepared**,
  not that a public site has been deployed or externally verified.

## Windows verification

Run with the backend stopped, and confirm the working tree is clean before pull:

```powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m unittest tests.test_product_builder_raw_html tests.test_product_builder tests.test_product_quality tests.test_s1_runtime -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd ui\dashboard
npm.cmd run test:navigation
npm.cmd run build
npm.cmd run test:browser
cd ..\..
.\.venv\Scripts\python.exe -m agentforge.control_center_v1 --port 8780 --allow-external-tools
```

In the Dashboard, create a new website Goal on disposable data; approve its SHA
and only the needed model/proposal permissions. Check that the single model call
produces a draft proposal, `Xem kết quả công việc` opens its **visual preview**,
and apply occurs only after explicit separate SHA review. Test mobile viewport
and verify there are no remote requests. A model/schema error must fail
without a silent retry or a fabricated success.

Do not use a production customer website for initial acceptance. Only after
the actual owner test can this change be considered reliable end-to-end.

## External engineering references

- Ollama structured outputs (JSON schema):
  https://docs.ollama.com/capabilities/structured-outputs
- OWASP XSS Prevention Cheat Sheet (context-aware output encoding):
  https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet
