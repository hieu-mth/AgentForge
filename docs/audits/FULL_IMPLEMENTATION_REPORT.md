# AgentForge full development status

**NO-GO for full AI Company or production acceptance.** The draft PR delivers
one adaptive workspace workflow, filesystem hardening and an owner-approved
model probe. The design reuses the authenticated Goal lifecycle and trusted
skill registry. The scope of the production program remains broader.

| Phase | Change | Local commit | Evidence |
|---|---|---|---|
| 0 | Trace and findings from post-PR #124 baseline | `c10e46b` | [System audit](FULL_SYSTEM_AUDIT.md) and [plan](FULL_DEVELOPMENT_PLAN.md) |
| 1 / 4 / 5 / 6 partial | `workspace.analyze` with scoped inventory, model-selected read/search twice, evidence-aware second call, citation-ID checks, SHA report and acceptance view | `9141e31` | `agentforge/workspace_agent.py`, `tests/test_workspace_agent.py` |
| 2 / 10 partial | POSIX no-follow dirfd traversal and exclusive publication with readback | `0d6e835` | `agentforge/gateway.py`, symlink replacement and filesystem regression tests |
| 3 partial | Revision-checked explicit Ollama probe, installed local model gate, timestamp and distinct UI status | `3ec6a85` | `agentforge/ops/runtime_certification.py`, `agentforge/api/routes/model_hub.py`, loopback and Owner HTTP tests |
| 11 / 13 partial | Separate QA pass and Owner runtime handoff | Draft PR documentation commit | [QA evidence](INDEPENDENT_QA_REPORT.md) and [Windows procedure](../verification/OWNER_RUNTIME_ACCEPTANCE.md) |

The workflow accepts a natural-language brief and explicit input directory.
It requests two typed choices between text search and line read. It then
generates one new report. The approved Goal constrains all operations to that
directory and one fixed output path. Only the local Ollama route is allowed
for this skill, with two 75-second action calls and one 90-second synthesis
call ceiling. The report records source line anchors and normalized text
hashes. Output publication is exclusive. Citation checks verify evidence IDs
and accepted structure. Owner still checks accuracy before acceptance.

## Verification

Linux Python 3.13.5 with the project media dependencies, Node v24.
The regression command was `python -m unittest discover -s tests -q`
using the project virtual environment. It ran 1,071 tests, 0 failures,
0 errors and 0 skips. Dashboard navigation ran 41 tests, NovaMart ran 7.
Both Vite builds passed. Dashboard build emitted a chunk-size warning.
Docs, source hygiene, compatibility scan, compile and diff checks passed.
Local Chromium smoke was blocked at launch. Windows CI is tracked on the PR.

Real operations verified on this host were scoped report create/readback,
the fixed Python diagnostic, and FFmpeg fixture encode/decode. HTTP and
SQLite integration use real components with fake inference/service boundaries.
Ollama, ComfyUI, and Docker were unavailable here.

## Security and products

Explicit consent, plan SHA and artifact acceptance rules are preserved.
POSIX path replacement probes protect the tested access paths. Windows
junction races, broad cancellation, dynamic permissions and general sandboxed
tools still need work. The model probe demonstrates completion for one fixed
prompt when run on a real Ollama endpoint. Routing continues to use configured
profiles and does not infer hardware fit or quality from that probe.

Research handoff and Markdown analysis have integration evidence. Live
website, generated React, image, video and external business acceptance
remain pending. See [remaining gaps](REMAINING_GAPS.md).

## Git

Branch `feat/agentforge-full-runtime`, target `main`, baseline `5a856bd`.
The draft PR preserves the same commit trees as the local commits listed
above. Follow GitHub CI and verify that the live Owner acceptance tests
apply to the final PR head before evaluating a merge.
