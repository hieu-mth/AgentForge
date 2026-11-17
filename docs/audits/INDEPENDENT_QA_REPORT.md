# Independent QA evidence

This was a separate adversarial test pass after implementation, performed in
the same Linux workspace. It uses actual files, loopback HTTP and SQLite.
Model outputs and the Ollama HTTP service in integration tests are fixtures.
It does not certify the implementation on Owner Windows.

| E2E | Evidence and result | Verification |
|---|---|---|
| 01 Environment | `python -m agentforge.ops.runtime_certification --run-ffmpeg --confirm-local-exec` detected Python/Node and returned unavailable for Ollama, ComfyUI and Docker. | REAL_RUNTIME_VERIFIED for these observations |
| 02 Filesystem | `tests/test_workspace_agent.py` uses actual source files and a created report. Standalone disposable write/read produced SHA `fc3f48568695c0e104f7099bbe8fc93f8abad62de53bbff95a7d4a77f35e51f1`. Edit/diff scenario is open. | REAL_RUNTIME_VERIFIED for read and create, PARTIAL |
| 03 Terminal | `gateway.run_terminal_recipe('python-version', 'test')` in a temporary scope returned exit 0, stdout `Python 3.13.5` and empty stderr. | REAL_RUNTIME_VERIFIED for the diagnostic |
| 04 Browser | `AGENTFORGE_BROWSER_EXECUTABLE=/usr/bin/chromium npm run test:browser` was attempted. Chromium exited with `socket() failed: Operation not permitted`. | BLOCKED local browser |
| 05 Research | `tests/test_research_report.py` verifies real report and API handoff with model, search and source fixtures. | INTEGRATION_VERIFIED, live BLOCKED |
| 06 Agent Loop | `tests/test_workspace_agent.py` checks that the second model request contains observed evidence, and runs the selected read against a second file before synthesis. | INTEGRATION_VERIFIED, live Ollama BLOCKED |
| 07 Routing | `tests/test_model_hub.py`, `tests/test_wave5_runtime_certification.py`, `tests/test_control_center_v1.py` exercise config and consent, revision checks, and remote alias denial. Hardware-fit routing remains open. | INTEGRATION_VERIFIED for listed controls |
| 08 Website | NovaMart test and build passed. Generated React live browser and revision acceptance need Docker/browser. | UNIT_VERIFIED and STATIC_VERIFIED, full flow BLOCKED |
| 09 Image/Video | ComfyUI unavailable. FFmpeg fixture encoded and decoded both audio and video. Fixture SHA `d0065801d79ed2d239efcc839f8536aad05e05421fee033ee617308d4944e88e`. | REAL_RUNTIME_VERIFIED for FFmpeg, GPU generation BLOCKED |
| 10 Security | Parent symlink swaps before read and publication fail on POSIX. Invalid tool arguments, duplicate decisions and invented references produce no artifact. Missing Owner, CSRF and probe permission are rejected. | INTEGRATION_VERIFIED in this environment; Windows race and full threat suite open |
| 11 Recovery | Existing recovery tests exercised by Python regression. A restart inside the new tool loop has no internal resume path. | PARTIAL |
| 12 Acceptance | The loop integration verifies SHA, reads the file and records an Owner decision with fixture credentials. Full reject/revise/accept and actual Owner acceptance remain open. | INTEGRATION_VERIFIED for handoff |

The source evidence lives in the referenced test modules. The Linux runtime
probes used disposable files and did not issue cloud calls. Product latency,
concurrent capacity and inference quality are **NOT_MEASURED**.
