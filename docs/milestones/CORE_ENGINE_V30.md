# V3.0 — Core Engine migration

**Canonical Python modules:** `agentforge.core.brain_store`,
`agentforge.core.task_history`, `agentforge.core.skill_registry`,
`agentforge.core.skill_runner`, `agentforge.core.brain_planner`,
`agentforge.core.brain_runner`.

Every legacy `agentforge.<name>` path is now a **module alias**, not a copied
implementation. It resolves to the *same module object* as the canonical
path, so patching the old `brain_store.DB` or `skill_runner.invoke` continues
to affect execution tests and existing integrations.

Run `python -m agentforge.task_history` and
`python -m agentforge.skill_runner` as before. The compatibility CLI alias
calls the canonical `main()` function. Canonical modules use
`agentforge.paths.REPOSITORY_ROOT` rather than nested-file-based parent
indexes, preserving `data/company/*.sqlite3` and existing skill manifests.

**Safety:** No implicit task replay, approval bypass, model invocation,
new permissions, schema changes, moving SQLite files or deleting workspace.
Existing supervised execution is preserved. Full Windows CI is mandatory.
