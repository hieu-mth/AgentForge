# AgentForge Film Studio — 12 GB VRAM motion pilot

Status: **ComfyUI adapter and safety contracts implemented; NO REAL VIDEO TESTED**.

This milestone adds an opt-in, *one-shot* dispatch of a 4-second text-to-video shot
to an Owner-installed local ComfyUI at **127.0.0.1:8188**. All video model weights,
ComfyUI workflows and nodes must be explicitly installed and reviewed by Owner.
No model is installed or downloaded automatically, no cloud calls and no
YouTube/automatic publishing are performed.

## 12 GB approach

Based on official ComfyUI documentation, Wan 2.2 TI2V 5B supports native
offloading and has an example fitting 8 GB VRAM. Therefore it is a plausible
first candidate for 12 GB, not proof of good performance. Use an official
ComfyUI API-format T2V graph and pinned Wan2.2 5B weights.

Initial guardrail profile: **640×352, 49 frames, 12 fps, batch size 1**,
approximately 4 seconds. Queue one shot at a time. A plan slot longer than
5 seconds cannot be submitted through this pilot. The original 2-hour example
has 8-second slots, so it is for *planning only*, not immediately eligible for
this smaller GPU pilot. This is intentional.

Avoid LTX-2.5 by default on this machine: its official ComfyUI docs
recommend **32+ GB VRAM**. Do not promise a working 2-hour film without an
actual hardware run and verified per-shot generation time, quality and costs.

Official references:
- https://docs.comfy.org/tutorials/video/wan/wan2_2
- https://comfy.org/hub/workflows/wan-2-2-5b-video-generation-f83ee3caa04e/
- https://docs.ltx.io/open-source-model/integration-tools/comfy-ui

## Installation by Owner

1. Install ComfyUI locally, keep it bound to localhost only.
2. Install the official Wan2.2 TI2V 5B weights and required encoder/VAE.
3. In ComfyUI, load official Wan2.2 5B **text-to-video** workflow.
4. Export the **API workflow** graph, not the UI workflow. Inspect its
   core node types, file references, and safe local settings. Do not execute
   downloaded scripts or custom nodes without review.
5. Wrap its API graph as documented below in a locally owned JSON file.
6. Start with a 4-second chapter/shot plan, and submit with explicit approval.
7. Inspect/verify the ComfyUI output yourself. The adapter does NOT import
   returned video, check motion quality, perform audio QA or attach clips to
   the long-form plan.

The trusted workflow wrapper is a JSON object with exactly these keys:

- \`format\`: \`agentforge.film.comfy.t2v.v1\`
- \`api\`: ComfyUI API prompt graph using only allowlisted standard core nodes
- \`positive_node\`: ID of the \`CLIPTextEncode\` node with \`inputs.text\`
- \`seed_node\`: ID of the \`KSampler\` node with \`inputs.seed\`
- \`size_node\`: ID of the core latent node with
  \`width=640, height=352, length=49, batch_size=1\`
- \`fps_node\`: ID of \`CreateVideo\` with \`fps=12\`
- \`output_node\`: ID of \`SaveVideo\` with \`filename_prefix\`

The node list is conservative. Official workflows may introduce additional
trusted nodes; future adaptation should review those deliberately rather
than bypassing the allowlist.

## Commands on Windows PowerShell

Run after \`git pull --ff-only origin main\` and installation of the existing
AgentForge package. No Docker is needed for the local, Owner-installed model.

\`\`\`powershell
cd D:\AgentForge
.\.venv\Scripts\python.exe -m agentforge.domains.media.motion_comfy health
.\.venv\Scripts\python.exe -m agentforge.domains.media.motion_comfy inspect-workflow --workflow D:\FilmWorkflows\wan5b-api-reviewed.json
\`\`\`

For the first pilot create a local 4-second film plan (chapter duration 4)
using the \`long_form\` CLI. The 2-hour example uses 8-second slots and is
**not** eligible for this pilot. Use the SHA values returned by the inspect
commands and make your own local \`shot-prompt.txt\`.

\`\`\`powershell
.\.venv\Scripts\python.exe -m agentforge.domains.media.motion_comfy submit --film-slug pilot --shot-id sh-00001 --plan-sha YOUR_FILM_PLAN_SHA --workflow D:\FilmWorkflows\wan5b-api-reviewed.json --workflow-sha YOUR_WORKFLOW_SHA --prompt-file D:\FilmWorkflows\shot-prompt.txt --seed 7 --confirm-gpu-run
.\.venv\Scripts\python.exe -m agentforge.domains.media.motion_comfy status --job-id RETURNED_JOB_ID
\`\`\`

This adapter does **not** have an automatic retry option. It writes an SQLite
\`SUBMITTING\` checkpoint *before* the HTTP GPU request; if the HTTP result is
ambiguous, it does not re-run or spend GPU again. A completed ComfyUI history
says **COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED**, never "film ready" or
"video accepted".
Provider-confirmed terminal success frees the one-active-GPU-shot quota for
another shot without auto-retrying the original shot. No user video, model source or YouTube credentials are
stored in Git.

## Current blocker before claiming Milestone 2 complete

Real machine with 12 GB VRAM: installed ComfyUI and trusted official model
graph, available VRAM, actual rendered MP4, decoded frame/video QA, verified
clip duration, cost/time measurement, and a successful 60–90-second original
motion pilot. Tests in CI use fixtures and mocks, not actual inference.
