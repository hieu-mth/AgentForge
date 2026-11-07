# V4.1 — Source-aware React application revisions

V4.0b created immutable marketplace React source proposals but could not
revise them without starting from scratch. V4.1 adds a **separate Goal**
for each change request, with exact source proposal ID, SHA-256 and full
Owner feedback.

## Workflow

1. Owner finishes a `webapp.create` Goal (or opens an older app proposal).
2. Task result → **Xem mã nguồn & yêu cầu sửa**.
3. The authenticated review endpoint validates the full signed proposal.
   Dashboard displays source files, original spec, source comparison and SHA.
4. Owner requests a revision (10–3000 characters). Control Center checks the
   exact SHA reviewed in this session, CSRF, workflow policy and model budget.
5. A new `webapp.revision` Goal is created, **not executed**. Owner approves
   plan digest and a one-call model grant before any inference.
6. The model receives previous verified app data, original prompt and feedback.
   It may change brand/hero copy/accent/category/product dataset but cannot
   author executable JSX, shell commands, dependencies or arbitrary code.
7. The model output is validated; a visibly identical spec is rejected.
   Immutable proposal includes signed `revision` provenance, new app source,
   and compare() returns changed fields and files.
8. Owner may inspect/apply the new SHA. It writes a **new project directory**
   and never overwrites the old version or runs npm.

## Boundaries and truthful limitations

- App **data** revisions only; `src/App.jsx`, state logic, CSS and template
  implementation remain trusted and unchanged. Requesting new app behavior
  such as account registration or checkout is **not implemented** in V4.1.
- Human review of the diff is mandatory. Model output is not automatically
  retried after a crash. SHA, grants and policy remain per Goal.
- The app source review route is authenticated/CSRF-gated; no executable
  browser preview of untrusted React code is exposed through Control Center.
- Only after the Owner separately approves applying source may they manually
  run `npm.cmd install`, `npm.cmd test`, `npm.cmd run build` and
  `npm.cmd run dev` in the generated project.
- Stale model/CI validation is not a replacement for acceptance testing
  with the actual local model and Windows development environment.

## Follow-up milestone V4.2

A genuinely flexible AI Developer that writes React/JSX and tests arbitrary
interactions requires sandbox isolation first. The sandbox must enforce
bounded filesystem/process/network, resource/time limits, no secrets and
separate Owner consent. Until then we keep the preview read-only and
unexecuted.
