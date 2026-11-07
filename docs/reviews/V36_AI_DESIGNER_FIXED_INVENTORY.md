# V3.6 — Fixed vs AI-designed website inventory

Scope: the default `website.draft` / `web.create` path, its Goal revision
workflow and its owner preview. This document does **not** claim that every
other AgentForge business skill is an unrestricted AI agent.

## Creative decisions no longer hard-coded

| Previous V3.5 behavior | V3.6 default behavior |
| --- | --- |
| Single fixed hero → intro → benefits → contact markup | Model supplies ordered list of 2–7 sections, 7 supported content families, editable labels and item counts; compiler generates the document |
| Five named palettes (forest/ocean/sand/plum/mono) | Model chooses any three validated six-digit HEX colors for background, surface and accent; compiler derives legible button/foreground colors |
| Three fixed hero layouts | Model chooses hero composition plus a different layout for each section; four hero options and four section variants as safe CSS primitives |
| Fixed system sans font | Model chooses among four local-safe font stacks (modern, editorial, rounded, technical) |
| Always 2–4 hard-coded highlight cards | Model chooses section types, names, order, up to seven sections, and 0–4 items per section according to its type |
| Decorative image always the same arrangement | Model chooses original offline CSS art type (orbit, geometry, gradient or minimal); owner-approved real images remain a separate workflow |
| Generic hard-coded site title | Model chooses SEO title, description, brand, hero headline, copy and CTA labels |
| Revisions composed from truncated text only | Revision consults the SHA-validated previous `site.json` design plus bounded visible text; asks AI to preserve unchanged portions and implement changes |
| Only index.html stored | Immutable proposal stores `index.html` and `site.json` (non-executable design spec). Both are covered by the existing SHA digest and Owner approval |

These decisions are model-driven: two valid models can choose substantially
different structures. The runtime does **not** silently swap one model's
design for a generic fixed theme or claim that a blank page is a success.

## Fixed on purpose; not safe to delete

- Trusted HTML/CSS compiler, escaped text nodes, checked color tokens,
  allowlisted local font stacks and composition primitives
- No model-provided HTML tags, CSS rules, JavaScript, external scripts,
  iframes, tracking, fetched resources or arbitrary shell calls
- HTML static quality validation, preview sandbox and restrictive CSP
- Explicit grants, Goal SHA approval, proposal SHA apply confirmation,
  immutable original source and validated model-call budgets
- Bounded section/item/text and total file sizes, no unlimited context or
  uncontrolled output tokens, no silent retry or automatic publication
- Real product photos and customer-specific contact information require
  Owner supplied/confirmed sources

These are safety and business rules, *not arbitrary design templates*.
A future **Advanced AI Developer** skill can use a separately isolated
workspace, test runner and per-action Owner permissions; it must not inherit
the ability to execute arbitrary generated code from this static website skill.

## Runtime contract

- Production calls `agentforge.model.generate_json(prompt, DESIGN_SCHEMA)`
  **once** after approval. The raw result must pass `validate_spec()` exactly.
- The compiler renders CSS from fixed property names and validated hex colors,
  enum composition values and bounded numeric corner radius, escaping all
  dynamic prose in HTML text/attribute contexts. The compiler itself does not
  call any model, browser, network endpoint or process.
- The signed `site.json` file contains versioned `agentforge.design.v1` typed data: validation does not interpret it
  as executable JavaScript/HTML, and revisions may use it only as *untrusted*
  context after verifying the original proposal SHA.
- A revision with the same visible design/copy is rejected; a metadata-only
  update is not misreported as a visible edit.
- Existing V3.4 and V3.5 proposals remain readable and revisable using their
  validated HTML text; new proposals include full design context.

## Acceptance and known limitations

CI tests validate schema, injection prevention, diverse output structures,
SHA and end-to-end fake-model Goal execution. They do not prove that the
owner's live local model has enough context to fill a complex design schema
or that it can create a visually excellent website. Test at least two
different briefs, a content revision, a visual revision, an unchanged
revision, and desktop/mobile preview on the owner's hardware.

Still fixed as implementation primitives: 7 section families, 4 hero variants,
4 section variants, 4 system font stacks and 4 abstract CSS art options (or no art).
These are *composable*, not open-ended component/code generation. The user
can request a carousel, checkout, custom forms or external integrations only
through a separate future app-development workflow with explicit capabilities
and sandboxing. AI-generated photorealistic images still need a separately
authorized local ComfyUI/asset pipeline.

Engineering references:
- Ollama structured outputs: https://docs.ollama.com/capabilities/structured-outputs
- OWASP XSS output encoding: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet
