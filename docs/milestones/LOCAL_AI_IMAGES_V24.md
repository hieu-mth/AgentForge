# AgentForge V2.4 — Local AI Image Studio (optional ComfyUI)

The original Product Builder uses a language model to produce HTML/CSS/SVG, which is **not a photorealistic image generator**. This extension adds a separate, explicitly owner-approved **local image generation adapter** against ComfyUI.

It does **not** bundle ComfyUI, diffusion checkpoints, model licenses or GPU drivers; those must be installed/approved on the owner's computer. No auto-install/download, hosted image API or secret collection is included.

## Preconditions

1. AgentForge is updated to the V2.4 commit.
2. Optional dependencies are installed with \`python -m pip install -e ".[media]"\` in the project venv.
3. Owner separately starts ComfyUI listening **only** at \`127.0.0.1:8188\`. Do **not** expose ComfyUI to the public network.
4. ComfyUI must have an owner-trusted checkpoint with a simple flat name ending \`.safetensors\` or \`.ckpt\`. This first adapter supports a fixed, standard CheckpointLoaderSimple + CLIPTextEncode + KSampler + VAEDecode + SaveImage graph; custom workflows/nodes are intentionally unavailable. Checkpoint architecture and GPU memory must be compatible. This is not a universal model adapter.
5. Create a website proposal via Prompt-first and **apply** the owner-approved website locally. An applied \`workspace/products/SLUG/index.html\` is required before creating its images.

## Owner flow — all through Dashboard

Restart AgentForge Control Center with \`--allow-external-tools\` after authentication. This switch only enables the possibility to approve external-capable actions; it does not automatically launch image generation.

- Open **Projects & Files → AI Image Studio**.
- Click **Kiểm tra ComfyUI / checkpoints**. \`UNAVAILABLE\` or \`NO_CHECKPOINT\` is a real blocker, not an automatic fallback.
- Select an applied project, installed checkpoint and describe one image. Confirm local GPU generation. One job is submitted to \`POST http://127.0.0.1:8188/prompt\` with the fixed graph, no shell and no cloud.
- When ComfyUI finishes, click **Nhận ảnh khi xong**. AgentForge queries \`GET /history/{prompt_id}\`, validates the one expected \`SaveImage\` output, downloads bounded PNG from \`GET /view\` on localhost, checks raster dimensions and digest, and stores an immutable filename in \`workspace/products/SLUG/assets/\`.
- **Open the actual PNG on Windows and inspect it.** Image could be unattractive, incorrect, misleading, contain trademarks or depict nonexistent products. No heuristic image verification is semantic approval.
- Click **Gắn ảnh vào web**, review exact image and current website SHA, confirm. AgentForge backs up the previous \`index.html\` in \`.backups/JOB_ID-index.html\`, inserts a labeled AI illustration figure at the start of \`<main>\`, runs existing static safety checks and writes only this local website file. No public deployment.
- Inspect the local website in a browser again, including mobile. If the layout is poor, use the existing website revision workflow instead of automatically regenerating/replacing images.

## Safety & recovery

- **No automatic retry.** A crash during a ComfyUI POST may already have caused generation; the ledger remains \`SUBMITTING\` to require manual investigation. After image import claim it remains \`COLLECTING\` on uncertain errors. An interrupted HTML attachment remains \`ATTACHING\`; backup may exist and must be manually inspected. These states are not automatically resumed.
- **Owner review is mandatory twice:** before GPU submission and before SHA-bound attachment; ComfyUI output images are never published automatically.
- No remote destination is accepted. Server address is hard-coded loopback; paths, checkpoint names and image filenames are validated. No arbitrary ComfyUI JSON or custom graph nodes are accepted from prompt or HTTP API.
- The generated image is clearly labeled as AI illustration, **not a photograph of an actual mattress for sale**. Owner must confirm rights/marketing accuracy before use in customer-facing ads.
- Filename/dimension/size checks are necessary but not proof of harmless content.
- Provider bills, GPU power consumption, legal use of model weights and customer conversion remain unverified.
- SQLite ledger: \`data/company/image_studio_v24.sqlite3\`; assets: \`workspace/products/SLUG/assets/\`. Both are gitignored. **Do not use the cache-cleaner to delete these business records.**

## Technical entrypoints

- \`src/agentforge/image_studio_v24.py\` — fixed ComfyUI adapter, job ledger and SHA-bound attach.
- \`src/agentforge/control_center_v1.py\` — authenticated owner-only explicit actions with CSRF.
- \`src/agentforge/control_center_static/app.js\` — Image Studio UI.
- \`tests/test_image_studio_v24.py\` — mocked ComfyUI graph, no-retry, output validation and asset attach tests.

All real model-generation acceptance must occur on the owner's machine with its actual checkpoint and GPU. Windows CI tests mock HTTP; they cannot establish visual/photorealistic quality.
