# AgentForge — Final Pre-Runtime Acceptance (10/11/2026)

**Verdict:** \`CODE_CONTRACT_READY / OWNER_RUNTIME_PENDING / NOT_PRODUCTION_GO\`.

Đây là lần tự kiểm toán cuối trước khi Owner thực nghiệm trên PC Windows. Không chạy GPU, Docker, OAuth thật, không gọi model, đăng video hoặc sửa/xóa data và workspace của Owner. Báo cáo là **review kiến trúc/code + CI tests**, không phải chứng nhận an ninh/phim/website thương mại.

## Source and CI baseline

| Phạm vi | Bằng chứng |
| --- | --- |
| Code baseline | \`main\` tại \`4b87544eb273b81bbbc61d90524106dc8b45f942\` trước audit hardening |
| Tracked repo inventory | 539 blobs; 208 Python modules trong \`agentforge/\`; 31 trusted skill manifests; 110 files trong \`tests/\`; 35 dashboard files; 96 docs |
| Last Wave10 Windows CI | [#42747643999](https://github.com/hieu-mth/AgentForge/actions/runs/42747643999) — PASS, 929 Python unittest tests |
| CI workflow | \`.github/workflows/ci.yml\`: Python 3.13 Windows, wheel, docs links, import compat, Dashboard build + Edge smoke, NovaMart tests, Base V1 acceptance contracts |
| Hardening PR | CI source hygiene gate mới, private-upload post-flight SHA và regression, doc structure cleanup. Kết quả CI cần đối chiếu với **HEAD commit của PR hardening** trước merge |
| Local system | Owner Windows \`D:\AgentForge\`, Docker/ComfyUI/FFmpeg/YouTube credentials: **NOT ACCESSED / UNVERIFIED** |

**Phạm vi phương pháp:** kiểm kê toàn bộ 539 tracked paths và các test/CI contracts; rà thủ công những module trọng yếu (API auth/session, model routing, skill policy, Webapp/Website, Docker QA, Film Studio và Publishing); quét một số nhóm mã JS/Python để tìm shell dynamic execution, eval/XSS, file destructive paths và credential patterns. Không có static analyzer chứng minh mọi nhánh code, dependency vulnerability audit đầy đủ hoặc kiểm thử runtime model thực.

## Chấm điểm kỹ thuật — tương đối, chưa bao gồm chất lượng sản phẩm thực tế

| Trục | Điểm / 10 | Nhận xét |
| --- | --- | --- |
| Kiến trúc và module boundaries | **8.5** | Feature-first modular monolith, canonical API/core/integrations; giữ aliases tương thích |
| Owner/security gate thiết kế | **8.3** | Host/Origin/session/CSRF, immutable SHA, Owner grants, Docker no-network; vẫn phụ thuộc bảo mật Windows/Docker |
| Model Hub và config | **8.0** | Profile/route rõ, wired text; media/image config-only đúng trạng thái |
| AI Web Builder code | **7.8** | Revision/diff/rollback/export QA contracts; real model + app acceptance chưa có |
| Film Studio code | **7.7** | Comfy one-shot, 49f/12fps, clip provenance, FFmpeg assembly; visual consistency chỉ metadata |
| Publishing/Growth code | **7.7** | Local release ledger, private-only optional OAuth, manual cash & metrics; không phải monetized channel |
| CI, fixture contracts, docs | **8.5** | Windows CI nhiều layers, >900 Python tests; thiếu full dependency scan và generated source browser acceptance |
| **Code pre-runtime readiness** | **8.1** | Có thể bắt đầu Owner runtime theo checklist; **không** đồng nghĩa production-ready |

Đây là **đánh giá kỹ thuật có giới hạn theo bằng chứng hiện có**; điểm số không phải tỷ lệ thành công, benchmark hiệu năng hay cam kết bảo mật.

## Review findings và xử lý

| Severity | Issue | Status |
| --- | --- | --- |
| P1 — preventive | Repo GitHub đang **public**, \`.gitignore\` chỉ bảo vệ \`.env\`, \`data\`, \`workspace\` và voice model, thiếu guard cho weights/OAuth client/private key | **FIXED IN AUDIT PR**: ignore patterns + CI tracked-file/token hygiene |
| P1 — reliability | Sau private YouTube upload, source MP4 có thể thay đổi trong khi Google API đang đọc; cần rehash cuối trước khi công nhận receipt | **FIXED IN AUDIT PR**: post-flight \`inspect_render\`, ambiguous state nếu SHA sai |
| P2 — docs | \`docs/STATUS.md\` bị chèn các Wave ở trên heading H1 và Wave 8 dưới Wave 7; README mô tả YouTube vẫn hoàn toàn manual | **FIXED IN AUDIT PR** |
| P2 — git hygiene | [PR #35](https://github.com/hieu-mth/AgentForge/pull/35) vẫn **open, mergeable=false**, thay đổi code ở \`src/\`, \`ui/\` kiểu cấu trúc cũ; không phù hợp flat-root hiện tại | **DO NOT MERGE BLINDLY**. Chưa đóng/xóa; kiểm tra thủ công trước khi đóng |
| P2 — supply chain | GitHub Actions \`checkout@v4\`, \`setup-python@v5\`, \`setup-node@v4\` chưa SHA-pin; Python optional YouTube install, package SCA/SBOM không có gate riêng | **FOLLOW-UP**, không tự thay dependencies trong audit này |
| P1 — Owner acceptance | Không có bằng chứng trên PC về live Ollama/Anthropic, AI JSX revision thành công, Docker Chromium, GPU Wan 5B, long-form movie, OAuth thực và backup/restore | **BLOCKED UNTIL OWNER RUNTIME**, không thể giải quyết bằng mock |

**Không phát hiện secret cụ thể trong tên tracked file và các log Phase 1 đã kiểm tra bằng signature phổ biến.** Điều này **không đảm bảo** repo/Git history chưa bao giờ chứa secret; phải dùng secret scanning và Git history review riêng nếu có nghi vấn. Bất kỳ secret từng bị commit phải được revoke/rotate, không chỉ xóa file hiện tại.

## Gate status

| Gate | Code/CI | Owner PC |
| --- | --- | --- |
| G1. Python wheel, 31 Skill manifests, imports/compatibility | PASS theo Windows CI | Venv thực cần kiểm |
| G2. Dashboard/Vite build, React browser smoke Edge | PASS trên reference/dashboard | Login/hành động thật cần kiểm |
| G3. Owner approvals/session/CSRF, ops pause, local DB | PASS contract fixtures | Thử auth, quyền, pause/resume |
| G4. Model Hub config, one-shot inference | PASS contract | Local model/paid cloud inference + latency/billing PENDING |
| G5. AI React build/revise/rollback, sandbox | PASS fixtures | Real generated JSX/browser QA PENDING |
| G6. Backup/verify/staged restore | PASS fixtures | Dữ liệu backup+restore thật PENDING |
| G7. Film 5B ~4s one shot, 12GB VRAM | PASS fixtures | Comfy model/GPU/video actual PENDING |
| G8. 60–90s film continuity, TTS/SRT, master MP4 | PASS fixtures | Master 15+ source clips/audio quality PENDING |
| G9. YouTube private API and manual analytics/finance | PASS contract mock | OAuth/upload/account/bank reconciliation PENDING |
| G10. Public launch, production monitoring, monetization | NOT CLAIMED | NOT APPROVED |

**Final decision: NO PRODUCTION GO until Owner completes G2–G9 in scope.** The code is suitable for local staged runtime acceptance, not autonomous revenue, multi-tenant SaaS or public service.

## Owner next — safe staged acceptance (no automatic external actions)

~~~powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main

# Create venv first only if absent, preserving existing data
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard

# No model, no external process, no GPU
.\.venv\Scripts\python.exe -B -m agentforge.ops.base_acceptance
.\.venv\Scripts\python.exe scripts\check_source_hygiene.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agentforge_acceptance_windows.ps1 -RunContractTests

# Start limited local dashboard, enable external tools only when required
.\.venv\Scripts\python.exe -m agentforge --port 8780
~~~

Sau khi runtime cơ bản ổn, thực nghiệm đúng thứ tự: **login/goal/backups → real Web Builder/QA → 1 Comfy clip → 3-shot continuity → 15-shot master → private-only YouTube handoff**, mỗi chặng ghi SHA, kết quả và blocker. Không tự động chạy Google OAuth, Docker hoặc paid inference trong checklist read-only.

Tài liệu chi tiết: [Base V1](../base_v1/README.md), [Wave 6](../wave6/README.md), [Wave 7](../wave7/README.md), [Wave 8](../wave8/README.md), [Wave 9](../wave9/README.md), [Wave 10](../wave10/README.md). 
