# AgentForge repository — current architecture

## Single owner frontend
`ui/dashboard/` is the React frontend and `/` redirects to
`/dashboard/`. The static Control Center HTML/CSS/JS assets were removed.
`src/agentforge/control_center_v1.py` remains the authenticated JSON
API and static React dist server.

## Canonical modules
- `src/agentforge/core/`: tasks, plan execution, policies, acceptance,
  public API serialization
- `src/agentforge/ai/` and `src/agentforge/model.py`: intake/model routing
- `src/agentforge/domains/`: website, webapp, media, growth
- `src/agentforge/storage/`: catalogs and retention
- `skills/`, `workers/`, `config/`: trusted worker contracts
- `examples/novamart/`: trusted marketplace template, NOT an Owner UI

Legacy import aliases are retained when tests/old callers depend on module
identity, monkeypatch behavior or stable CLI names. The read-only Python `dashboard_v0.py` monitor has now been retired and
its access-control coverage moved to the authenticated owner API.

`python -m agentforge` now launches the canonical Owner dashboard.
`python -m agentforge.workflow` still exposes the old LangGraph sample
for explicitly chosen legacy use.

## Protected data
Never recursively delete `data/`, `workspace/`, `.env`, user backups,
model weights or proposal histories. Generated source remains untrusted.
The safe cache utility `scripts/repo_hygiene.py` only considers bytecode
within `src/` and `tests/` and requires explicit confirmation to clean.

Historical notes in `docs/milestones/` should not be used as live setup
instructions. Use the main README and current audits/verification instead.
