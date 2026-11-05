# V2.9 — Canonical local paths and AI registries

- `agentforge.paths` owns repository-root, `data/`, `workspace/`, `workers/` and UI paths. It never creates directories on import.
- Canonical model and worker registries now live in `agentforge.ai.model_registry` and `agentforge.ai.worker_registry`.
- Old `agentforge.model_registry`, `agentforge.worker_registry` import paths remain working as compatibility wrappers.
- No schema migrations, user data moves or changes to Ollama configuration. The shared root is the same as the old `Path(__file__).parents[2]` when code was at the package root.
- Tests verify callable identity, configured worker/model loading and root equivalence on Windows.

The model execution client remains `agentforge.model` for now, because it has external hooks and tests. Move it only after compatibility tests for provider routing, monkeypatching, and model policy are ready.
