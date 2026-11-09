# V4.2 local Docker build sandbox

**Optional / fail-closed.** The Owner chooses to configure Docker Desktop in
Linux-container mode. AgentForge does not install Docker, pull images, install
npm packages on the host, run generated code natively or start a container
without separate Goal and process.run approvals.

## One-time preparation (manual Owner action)

On Windows PowerShell, from D:\AgentForge:

    docker build --file sandbox/webapp/Dockerfile --tag agentforge-webapp-qa:local templates/novamart
    docker image inspect agentforge-webapp-qa:local --format '{{.Id}}'

Copy the returned exact **sha256:<64 hex>** image ID, then configure in the
same PowerShell terminal running Control Center:

    $env:AGENTFORGE_SANDBOX_IMAGE = "sha256:<your actual image ID>"

The image contains locally preinstalled dependencies (React/Vite) and no user
project files. Building this image can use the network once under the
Owner's manual control; the later application QA container has **no network**.
Rebuild the image after Phase 1: Vite 7.3.7 / esbuild 0.28.1 are locked by
the reviewed reference package-lock.json and installed with npm ci. An old
cached image must not be reused after dependency changes.
Review npm dependency provenance before preparing the image. Upstream Node
image tag is not cryptographically pinned here; for production, replace it
with an Owner-reviewed digest. The application dependency lockfile is committed.

## Performing the isolated app test

Open a signed app proposal in Dashboard, choose **Lập Goal QA sandbox**,
review the plan SHA, grant **process.run** with external-run confirmation,
and execute. The workflow requires Control Center to be started with
--allow-external-tools. Without Docker or a valid pinned local Linux image,
the operation fails closed with SANDBOX_UNAVAILABLE.

The runner reads a verified application proposal, writes only its allowlisted
files into a temporary staging directory, mounts it read-only, copies it
inside a Docker container to tmpfs, and executes npm test then npm run build.

Isolation controls: local Docker daemon only; --pull never, network none,
readonly root, cap-drop ALL, no-new-privileges, uid 10001, 1 CPU, 1 GB memory,
64 processes, source readonly, tmpfs workspace, no shared host tokens/secrets,
and 150s deadline. Container output is discarded rather than persisted.
No preview server, external port, build output or package install survives.

**Not a formal security proof:** the trusted container image/daemon must be
maintained and patched by the Owner. Docker Linux container limitations and
Windows filesystem mount support must be accepted on real hardware.
On systems without proper isolation, keep using the source-only workflow.


## Wave 7 — QA Chromium offline (Owner tùy chọn)

Browser QA dùng image Docker riêng; bản V4.2 build-only cũ vẫn giữ nguyên. Từ root repo, với Docker Desktop Linux và BuildKit/buildx, Owner build thủ công **chỉ với hai context code tin cậy**, không chuyển toàn bộ data, workspace, `.env` vào Docker daemon:

```powershell
docker buildx build --load --build-context reference=./templates/novamart -f ./sandbox/webapp/Dockerfile.browser -t agentforge-webapp-browser:local ./sandbox/webapp
docker image inspect agentforge-webapp-browser:local --format '{{.Id}}'
$env:AGENTFORGE_BROWSER_QA_IMAGE = 'sha256:<ID thật từ dòng trước>'
```

Dockerfile chỉ COPY package manifest/lock từ named context `reference` và trusted `browser_runner.mjs` từ sandbox context. Build image lần đầu có thể tải Node base/Chromium/npm từ Internet, **chỉ do Owner chủ động**. Image phải pin bằng exact SHA được in ở máy trước khi mở Dashboard. Nếu Docker chưa hỗ trợ named BuildKit context, **không** thay bằng root context chứa Owner data; nâng cấp Docker/buildx hoặc tiếp tục QA build-only.

Start backend `python -m agentforge --port 8780 --allow-external-tools`, sau đó mở đúng signed React proposal, chọn **QA Chromium offline**, duyệt SHA Goal và riêng quyền `process.run` trước chạy. Runtime browser dùng `--pull never --network none`, readonly root và source, cap-drop ALL, UID 10001, bounded CPU/RAM/PIDs, timeout, không mount key/.env. Chromium dùng `--no-sandbox` bên trong container; Docker host/kernel và image supply-chain vẫn là ranh giới tin cậy, **không có bảo đảm tuyệt đối**.

QA chỉ smoke React render, button, mobile overflow, page console error, outbound blocking và 2 ảnh desktop/mobile lưu dưới `workspace/webapp-browser-qa`. `PASS_SMOKE_ONLY` không có nghĩa search/cart/checkout thành công hoặc website đã deploy; Owner cần mở ảnh và kiểm tra nghiệp vụ thủ công. ZIP export từ proposal đã inspect chứa source files + manifest và sha256, không chạy npm hay deploy. Không gửi ZIP chứa tài liệu riêng tư ra Internet.
