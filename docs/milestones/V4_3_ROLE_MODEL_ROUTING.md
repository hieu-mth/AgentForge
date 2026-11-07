# V4.3 — bounded role/model routing

**Implemented:** separate reviewed Worker profiles for Architect, Developer
and Reviewer. All default to the existing local Ollama `local_primary` model,
so no extra server or framework is required. Change each worker's
`model_ref` explicitly to an enabled, known profile in
`config/models.toml` to configure another model.

`agentforge.ai.role_routing.pipeline_plan()` reports the exact role-to-model
plan and refuses more than 3 estimated calls. The V5 workflow still needs the
normal Goal SHA approval and an explicit model confirmation **for each step**.
No automatic fallback, retries, provider hopping or spending. Model pricing is
*not* verified; the planned call count is not a currency cost estimate.

Cloud usage is fail-closed for V5 roles unless the Owner deliberately sets
`AGENTFORGE_CLOUD_MODEL_CONSENT=YES` in the Control Center process and
explicitly selects an enabled cloud model profile (via the worker config or
`AGENTFORGE_MODEL_REF`). Credentials stay in environment variables.
Never infer cloud consent from a prompt, a goal or a successful local call.

No background agents, unsolicited cloud calls or general-purpose online search.
