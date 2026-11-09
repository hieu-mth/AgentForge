# ADR-001 — Cấu trúc AgentForge được chốt

**Quyết định: ĐÃ CHỐT (approved target)** · **Triển khai: M1 + M2 + M3 DONE, M4a Growth DONE; M4b–M4d và M5 CHƯA MIGRATE** · 09/11/2026

Chủ dự án đã chọn **flat-root Python package + dashboard riêng**, thay cho `src/agentforge/` và `ui/dashboard/` ban đầu. **M1 đã chuyển React sang `dashboard/`, M2 đã chuyển Python sang `agentforge/`.** `api/` đã được triển khai ở M3; `features/`, `integrations/`, `ops/` trong cây vẫn là đích M4–M5, **chưa được tạo đầy đủ**.

- **Code thực tế hôm nay:** [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md).
- **Từng file Python và frontend hiện có:** [FILE_CATALOG.md](FILE_CATALOG.md).
- **Thứ tự chuyển đổi an toàn:** [MIGRATION_PLAN.md](MIGRATION_PLAN.md).

## 1. Cây thư mục mục tiêu

~~~text
AgentForge/
├── agentforge/                     # Python package và backend duy nhất
│   ├── __init__.py                 # Khai báo package
│   ├── __main__.py                 # python -m agentforge
│   ├── paths.py                    # Quy tắc tìm root và chặn path không an toàn
│   ├── api/                        # HTTP boundary, không chứa nghiệp vụ
│   │   ├── server.py               # Loopback HTTP server, React dist
│   │   ├── auth.py                 # Session, CSRF, Host/Origin checks
│   │   └── routes/                 # Task, website, webapp, film, ops endpoints
│   ├── core/                       # Tasks, workflow, policy, approval, acceptance
│   ├── ai/                         # Model routing, worker config, prompt intake
│   ├── features/                   # Các nghiệp vụ sản phẩm (feature-first)
│   │   ├── websites/               # Website design, preview, revision
│   │   ├── webapps/                # React proposals, QA, source revision về sau
│   │   ├── film_studio/            # Film/project/cast/shot/motion/continuity/editing
│   │   ├── media/                  # Reusable video, audio, caption, assets, FFmpeg
│   │   ├── growth/                 # Campaign, analytics, reporting, handoff
│   │   └── research/               # Evidence, customer discovery, source review
│   ├── integrations/              # Cổng thay thế được: ComfyUI, Ollama, FFmpeg...
│   ├── ops/                       # Backup, diagnostics, schedules, safe pause
│   └── storage/                   # Persistence infrastructure, artifacts, retention
├── dashboard/                      # React + Vite, npm app duy nhất
│   ├── src/
│   │   ├── features/              # Screens/domain views
│   │   ├── components/            # Reusable presentation
│   │   ├── api.js                 # Client HTTP/CSRF
│   │   ├── App.jsx                # App shell
│   │   └── main.jsx               # React entrypoint
│   ├── tests/                      # UI unit/smoke tests
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   └── index.html
├── skills/                         # Skill contracts có allowlist và quyền
├── workers/                        # Role/worker declarations, model assignment
├── config/                         # models.toml và cấu hình Owner (không secrets)
├── templates/                      # Reviewed source templates (NovaMart thực sự được builder đọc)
├── examples/                       # Ví dụ dữ liệu minh họa (film/storyboard)
├── tests/                          # Python integration, security, regression
├── scripts/                        # Maintenance, acceptance, docs lint
├── docs/                           # Tài liệu hiện hành + audit lịch sử
├── sandbox/                        # Đặc tả isolation; không mặc định đã chạy thật
├── data/                           # SQLite, ledgers: dữ liệu Owner, gitignored
├── workspace/                      # Sản phẩm, phim, proposal: gitignored
├── .github/workflows/              # CI chạy trên Windows
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
~~~

**Giải thích:** `agentforge/` và `dashboard/` cùng nằm ở repository root. **Không có `src/` hoặc `ui/` trong cây mục tiêu**. Hai thư mục `data/` và `workspace/` tiếp tục ở root, không đổi đường dẫn lưu trữ. Chỉ tạo các file/thư mục tương lai khi thật sự có implementation; tên trong ví dụ là **trách nhiệm dự kiến**, không phải tuyên bố chúng đã tồn tại.

## 2. Trách nhiệm theo ranh giới

| Khu vực | Làm gì | Không được làm |
| --- | --- | --- |
| `agentforge/api/` | Decode request, session/CSRF, response, routes, serve build `dashboard/dist` | Viết nghiệp vụ tạo phim/site, trực tiếp duyệt QA |
| `agentforge/core/` | Task lifecycle, permission/approval, workflow, artifact acceptance | Import ngược feature cụ thể, gọi provider không qua adapter |
| `agentforge/ai/` | Đọc model config, route role, prompt intake và model invocation policies | Tự ý truy cập tài khoản YouTube hoặc chạy source AI |
| `agentforge/features/` | Các use case sản phẩm và quy tắc nghiệp vụ | Tự tạo HTTP server riêng cho từng feature |
| `agentforge/integrations/` | Local/cloud API client thay thế được, decode kết quả, timeout, retries có giới hạn | Quyết định sản phẩm được `ACCEPTED`, công khai nội dung |
| `agentforge/ops/` | Diagnostics, backup, scheduler, emergency pause | Xóa Owner data/restore không có phê duyệt |
| `agentforge/storage/` | SQLite shared infra, artifact receipt, safe paths, retention | Ôm hết query chuyên ngành nếu query chỉ thuộc một feature |
| `dashboard/` | UX React và các yêu cầu tới API | Đọc SQLite trực tiếp hoặc tự quyết định quyền/QA |
| `skills/`, `workers/` | Hợp đồng task, capability, định danh role | Chứa credentials hoặc script tùy ý chạy tự động |
| `config/` | Cấu hình đọc được/review được | API keys, private user files |
| `tests/`, `scripts/` | Regression, maintenance, read-only checks | Chạy generated code trên Windows host |
| `templates/` | Reviewed, pinned source scaffolds mà runtime builder phụ thuộc | Dùng nội dung chưa kiểm duyệt hoặc xóa template khi còn dependency |
| `examples/` | Dữ liệu mẫu film/storyboard phục vụ thử nghiệm | Nhầm file JSON mẫu với sản phẩm đã render/ACCEPTED |

## 3. Quy tắc tổ chức file

1. **Feature-first:** mỗi file có một trách nhiệm. `features/film_studio/` giữ kịch bản, shot, continuity và orchestration; HTTP ComfyUI sẽ nằm trong `integrations/comfyui.py` (khi được tách thật).
2. **Không tạo folder trống để đủ sơ đồ.** Ví dụ `integrations/youtube.py` mới là **planned**, vì repo hiện chưa có OAuth/publish.
3. **Python package không chứa npm app.** React độc lập ở `dashboard/`, nhưng backend có thể tiếp tục phục vụ bundle đã build qua cùng cổng localhost.
4. **Tên file nói rõ mục đích:** ưu tiên `motion.py`, `shot_jobs.py`, `acceptance.py` thay cho tên có hậu tố `v15`, `v24`; chỉ đổi khi việc migrate thực sự được kiểm thử.
5. **Core không import feature.** Feature gọi core/AI/integrations/storage. Adapter không biết HTTP session của Dashboard.
6. **Không xây microservices.** Backend vẫn là một modular monolith; GPU dài hạn có thể chạy worker process riêng và lưu checkpoint SQLite.
7. **Không có folder `legacy/` mặc định.** Các đường import cũ phải duy trì ở đường cũ trong thời gian chuyển; di chuyển alias vào `legacy/` không tự bảo vệ compatibility.

## 4. Luồng xử lý chuẩn

~~~text
React dashboard/
      |
      v
agentforge/api/ (localhost, session, CSRF)
      |
      v
agentforge/features/<domain>/ ----> agentforge/core/ (policy/approval/state)
      |                                    |
      +----> agentforge/ai/                 +----> agentforge/storage/
      |
      +----> agentforge/integrations/ ----> approved external/local tools
~~~

Ví dụ Film Studio: script & character bible ở `features/film_studio/`; ComfyUI request thực hiện trong `integrations/`; job ledger/checkpoint lưu local; Owner quyết định review/acceptance ở core. **ComfyUI history success không phải video QA PASS.**

## 5. Hợp đồng không được phá

- `python -m agentforge --port 8780`, URL `/dashboard/`, `/api/*`, Owner login, CSRF và API contracts vẫn hoạt động.
- Dữ liệu hiện hữu ở `data/`, `workspace/`; source SHA và proposal IDs không thay đổi chỉ vì đổi đường code.
- Giữ backward-compatible imports/CLI khi còn callers. Không xóa alias theo cảm tính.
- Chỉ được thực thi source AI chưa tin cậy khi có sandbox thật được kiểm chứng; Docker không bắt buộc cho phát triển thông thường.
- Phân biệt **được test bằng mock** với **đã chạy thực tế** trên GPU 12 GB hoặc browser/YouTube.

## 6. Quyết định này không đồng nghĩa chuyển code xong

| Hạng mục | Tình trạng tại ngày chốt |
| --- | --- |
| Cây đích `agentforge/` + `dashboard/` | **APPROVED, đang migrate từng bước** |
| Đổi `src/agentforge/` thành `agentforge/` | **M2 DONE** — package discovery, data/workspace paths, imports/CLI regression |
| Đổi `ui/dashboard/` thành `dashboard/` | **M1 DONE** — code/frontend, Python path, npm/CI, URL regression |
| Refactor `control_center_v1.py` thành API routes | **M3 DONE** — canonical `api/server.py` + owner security contract tests; facade giữ import/CLI cũ |
| Đổi `domains/` thành `features/` | **NOT STARTED** |
| Tách integrations, ops, research, Film Studio | **NOT STARTED** |

Bắt đầu migration theo [MIGRATION_PLAN.md](MIGRATION_PLAN.md), không thực hiện một lần tất cả. Hướng dẫn cài đặt trong root README vẫn dùng cấu trúc **đang chạy** cho tới khi các bước chuyển thực sự được merge.
