# AgentForge system audit

Baseline is `origin/main` at `5a856bd` (PR #124). Evidence is from source and
the PR's CI unless explicitly marked as runtime evidence. This checkout is
Linux. Owner Windows, model endpoints, Docker and GPU inference require
separate evidence. This audit traces entry points and trust boundaries.

`Workspace → API auth/CSRF → prompt_intake → brain_planner → brain_store
→ brain_runner → skill_runner → domain adapter → model/tool → task_history
→ artifact_acceptance → Owner`

| ID | Severity | State | Evidence and impact | Repair and verification | Status |
|---|---|---|---|---|---|
| AF-01 | P1 | PARTIAL | `ai/prompt_intake.py:plan_request`, `core/brain_planner.py:_steps`, `research_report.py:run`. Research has one file and a fixed sequence. Unmatched prompts can lack an execution path. | Add an approved scoped tool loop. Test different tool sequences and result-driven decisions through API. | Open at baseline |
| AF-02 | P1 | PARTIAL | `gateway.py:safe_path/write_verified_report` use containment checks and exclusive publication. Concurrent parent replacement remains unverified. `run_terminal_recipe` runs one fixed diagnostic. `features/webapps/browser_qa.py` serves generated-app QA. | Retain narrow process/browser boundary. Add confined actions, race tests, cancellation and receipts before granting wider access. | Open |
| AF-03 | P1 | PARTIAL | `ai/model_health.py:inspect_goal_step`, `ops/discovery.py`, `ai/model_hub.py`. Catalog and configured route are visible. Inference and hardware fit require actual evidence. | Use opt-in probes and explicit routing rationale. Test missing resources and cloud denial. | Open |
| AF-04 | P1 | PARTIAL | `core/brain_runner.py:recover/retry_failed_step` and `core/brain_store.py` retain claims across restarts. No general intra-skill checkpoints or active cancellation were found on this path. | Verify crash points around effects, add cooperative cancellation and retain SHA binding. | Open |
| AF-05 | P2 | PARTIAL | `ai/workforce.py:inspect`, `core/skill_registry.py`, `core/skill_adapters/__init__.py`. Registry has trusted dispatch, Dashboard projects dependencies. Tool contracts and reverse workflow impact are incomplete. | Extend from canonical registries and validate metadata against handlers. | Open |
| AF-06 | P2 | PARTIAL | `api/auth.py`, `api/routes/goals.py:handle` enforce session, scoped grants, revision and approved SHA. `core/artifact_acceptance.py:decide` distinguishes review from execution. | Verify authorization failure paths and extend artifact revisions without weakening those checks. | Existing controls reusable |
| AF-07 | P1 | PARTIAL | `features/webapps/browser_qa.py`, `webapp_developer.py`, `features/websites/`, `dashboard/src/features/Workspace.jsx`. React source and separate QA entry points exist. Dynamic build/browser/revision loop needs live evidence. | Verify real sandbox stages and source changes against the same SHA. | Open |
| AF-08 | P1 | UNKNOWN | `integrations/comfyui.py`, `features/film_studio/`, `features/websites/image_studio.py`. Adapters and media processing exist. GPU/model availability and output quality are unverified here. | Run opt-in probe and media validation on compatible hardware. | Open |
| AF-09 | P2 | PARTIAL | `features/mattress_sales/`, `integrations/youtube_private.py`, `brain_scheduler.py`. Local business workflows exist. Credential-dependent integrations and live delivery are unverified. | Sandbox integration and preserve Owner gates. | Open |
| AF-10 | P2 | PARTIAL | `dashboard/src/App.jsx`, `features/Workspace.jsx`, Model Hub and Operations have separate lifecycle views. `.github/workflows/ci.yml` collects regression and browser evidence. | Expose execution receipts in existing views. Measure local browser/runtime separately. | Open |
| AF-11 | P3 | DUPLICATED | Legacy imports and feature/domain implementations coexist. Existing architecture tests enforce compatibility aliases. No dead-code deletion is justified from module names alone. | Preserve aliases until caller inventory and tests justify retirement. | Retained |

Existing detailed evidence and caveats are in [Core Runtime Audit](CORE_RUNTIME_AUDIT.md)
and [Core Runtime Final Report](CORE_RUNTIME_FINAL_REPORT.md). Broad cycle,
performance and production security certification remain open.

Xem [kết quả triển khai](FULL_IMPLEMENTATION_REPORT.md) và [trạng thái từng khoảng trống sau sửa](REMAINING_GAPS.md).
