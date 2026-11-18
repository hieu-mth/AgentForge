# AgentForge — cấu trúc hiện hành (CURRENT IMPLEMENTATION)

Ngày kiểm: 18/11/2026. Source of truth là Git `main` + CI, không phải milestone lịch sử.

| Vùng source | Trách nhiệm |
| --- | --- |
| `agentforge/api/` | HTTP loopback, login/session/CSRF, Owner routes, React asset serving |
| `agentforge/core/` | Task history, Owner-gated workflow, acceptance/report evidence, skill policy |
| `agentforge/ai/` | Model Hub, provider routing, worker configuration |
| `agentforge/features/film_studio/` | Film, character, motion, production, review, publishing ledger |
| `agentforge/features/media/` | Shared image/video jobs, ComfyUI image transport, media assets/render |
| `agentforge/integrations/` | Trusted external IO adapters; localhost ComfyUI and private YouTube |
| `agentforge/ops/`, `agentforge/storage/` | Readiness, backup/retention, local persistence |
| `dashboard/` | React Owner dashboard duy nhất; source JS trong `dashboard/src/` |
| `skills/`, `workers/`, `config/` | Static allowlists/model/task profile, đang tiếp tục loại manifest nghiệp vụ cũ |
| `tests/`, `scripts/` | Regression, Windows CI, read-only acceptance và source hygiene |

**Giai đoạn cleanup:** các package/alias `features/websites`, `features/webapps`, `features/growth`, `media.workflow` có thể còn dưới source trong quá trình dọn Đợt 3. Chúng không còn thuộc Owner API video-first được hỗ trợ. Không dùng các module đó để tạo tính năng mới.

## Luồng thực thi

`dashboard/` → `api/` → `core/` → `features/film_studio` và `features/media` → `ai/`, `integrations/`, `storage/`.

- `data/` và `workspace/` là Owner local data, không thuộc cleanup Git.
- `dashboard/dist/` và `dashboard/node_modules/` là build cache sinh ra, không commit.
- CLI hiện hành: `python -m agentforge`; Film planner: `python -m agentforge.features.film_studio.long_form`.

Chi tiết từng Python module đang tracked: [catalog](FILE_CATALOG.md). Quy trình chạy: [DEVELOPMENT](../DEVELOPMENT.md). Các giới hạn đã nghiệm thu: [PHASE2](../audits/PHASE2_BACKEND_ACCEPTANCE.md).
