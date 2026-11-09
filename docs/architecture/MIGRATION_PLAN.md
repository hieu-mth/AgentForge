# Kế hoạch chuyển AgentForge về flat-root architecture

**Trạng thái: M1 + M2 + M3 ĐÃ TRIỂN KHAI; M4a Growth + M4b Websites + M4c Webapps feature-first ĐÃ CHUYỂN, M4d và M5 CHƯA THỰC THI.** Cấu trúc đã chốt tại [ADR-001](TARGET_STRUCTURE.md). Các dòng 'trước' ở bảng rủi ro là baseline trước migration, không phải đường dẫn hiện đang chạy.

## Các rủi ro đã thấy trong source

| Khu vực | Hiện tại | Cần xử lý khi di chuyển |
| --- | --- | --- |
| Python packaging | `pyproject.toml` có `[tool.setuptools.packages.find] where=["src"]` | Đổi thành flat layout có **include đúng `agentforge*`**, kiểm tra wheel/editable install |
| Python root | `src/agentforge/paths.py` dùng `Path(__file__).resolve().parents[2]` | Sau move root package lên một cấp, phải tìm root đúng mà không tạo dữ liệu ở path mới |
| Các CLI lịch sử | Nhiều module dùng `Path(__file__).resolve().parents[2]` hoặc import alias | Audit toàn bộ, thay bằng helper `paths.py` ở các bước nhỏ; bảo toàn CLI |
| React serve | `control_center_v1.py` tính `ui/dashboard/dist` tương đối theo vị trí code | Đổi đường dẫn sang `dashboard/dist` và giữ URL `/dashboard/` |
| Vite/npm | UI đang ở `ui/dashboard/` | Cập nhật `vite.config.js`, package scripts, Node tests, browsers và CI |
| CI/hygiene | `.github/workflows/ci.yml`, `.gitignore`, `scripts/repo_hygiene.py` có prefix cũ | Điều chỉnh rồi kiểm tra không đụng dữ liệu Owner |
| Kiến trúc runtime | `src/agentforge/architecture.py` có `LAYOUT` và `GENERATED_DIRS` cũ | Cập nhật **sau** khi layout thật chuyển, không đổi snapshot sớm |
| Internal callers | Các import `agentforge.product_builder`, `brain_runner`, ... | Chỉ xóa wrapper khi đã migrate mọi caller và test module identity/monkeypatch |
| Product generation | NovaMart là scaffold có dependency thật | Đã chuyển `examples/novamart/` → `templates/novamart/`, cập nhật Builder/Toolchain, CI và sandbox; **không xóa** hoặc thay đổi SHA các proposal cũ |
| User data | `data/`, `workspace/`, `.env` được gitignore | Không copy/migrate/reset SQLite; tuyệt đối không `git clean -fdx` |

## Các bước triển khai được đề xuất

### M0 — Baseline và inventory

- Ghi rõ commit SHA, `git status --short`, cấu hình Python/Node, baseline Windows CI.
- Lập grep/import map: source, tests, PowerShell scripts, CI, docs, Vite, `Path(__file__).parents`.
- Đo thời gian build/test và thống kê các file alias, CLI được dùng; đánh dấu không chắc chắn là **UNVERIFIED**.

**Exit gate:** Không có dữ liệu Owner bị chạm; có danh sách path consumers và test baseline.

### M1 — Di chuyển frontend nguyên khối (DONE, kiểm thử Windows theo PR migration)

~~~text
ui/dashboard/  ->  dashboard/
~~~

- Di chuyển cùng package-lock và tests bằng Git, không xóa dự án Vite.
- Cập nhật Python React-dist route, npm prefixes, CI, `.gitignore`, browser test paths, docs và scripts.
- Giữ URL `http://127.0.0.1:8780/dashboard/` không đổi.

**Exit gate:** npm ci/build/tests/Edge smoke, HTTP auth/CSRF và static-asset regression PASS trên Windows. Source đã chuyển nguyên khối, backend `REACT_DIST` đọc `dashboard/dist`, URL `/dashboard/` giữ nguyên. Xem PR migration và CI để xác minh trạng thái cuối; không suy ra từ mock tests đơn lẻ.

### M2 — Di chuyển Python package nguyên khối (DONE, kiểm thử Windows theo PR migration)

~~~text
src/agentforge/  ->  agentforge/
~~~

- Cập nhật package discovery `pyproject.toml` cho flat package; không nhầm `tests/` hoặc `dashboard/` là package distributable.
- Sửa root path tính theo `__file__` ở tất cả module còn dùng hard-coded `parents[2]`, ưu tiên dùng `agentforge.paths`. Tránh vội sửa đường dẫn Owner data trong SQLite.
- Chạy wheel build + pip install, kiểm tra `python -m agentforge` **từ ngoài repo**, rồi chạy unit/CI.

**Exit gate:** import/CLI, task recovery, data ownership, no-duplicate-write và Windows CI PASS. Source đã chuyển nguyên khối, `pyproject.toml` include chỉ `agentforge` và `agentforge.*`; đường dẫn dữ liệu vẫn ở repository root. Không mất `data/` hoặc `workspace/`. Xem PR/CI của M2 cho bằng chứng.

### M3 — Chia API thực tế, không đổi transport (DONE, M0/M3 PR)

- Tách `control_center_v1.py` thành `api/server.py`, `api/auth.py`, `api/routes/*.py` theo nhóm endpoints.
- Giữ entrypoint cũ là shim nếu còn tests/CLI; giữ nguyên cookies, CSRF, Host/Origin, error codes và response schema.
- Không tạo FastAPI/microservice nếu `http.server` vẫn đủ cho một Owner.
- **Đã hoàn thành:** `api/server.py` (HTTP), `api/auth.py` (session), `api/static.py` (assets), `api/routes/read.py` (GET), `api/routes/bootstrap.py` và `api/routes/{artifacts,media,workspace,operations,products,goals}.py` (POST). `control_center_v1.py` là facade tương thích.
- **Bằng chứng bảo vệ:** [M0 API contracts](API_CONTRACT_V1.md), real HTTP security regression, no-reverse-import tests và Windows CI.

**Exit gate:** so sánh HTTP contract tests trước/sau và quyền mutation không suy giảm.

### M4 — Feature-first và integration adapters

- Chuyển `domains/websites`, `domains/webapps`, `domains/growth` thành `features/*` **theo từng module**.
- Chia media dùng chung vs. Film Studio riêng. `long_form.py` và motion orchestration ở `features/film_studio`, ComfyUI transport sang `integrations/comfyui.py`; vẫn giữ owner-gated submission.
- Tách phần research/customer evidence nếu còn hoạt động; bỏ `vN` khỏi filename **sau** khi test path/entrypoint.
- Ops và AI integration modules được chuyển sau, không gom tất cả SQL vào một monolithic repository.

**Exit gate:** một feature/một PR, không khác artifact SHA hoặc business behavior do việc đổi path.

### M5 — Gỡ compatibility & dọn tài liệu

- Xóa từng alias chỉ nếu grep/import graph + unit/CLI tests khẳng định không còn callers; với `sys.modules` alias phải kiểm tra monkeypatch và module identity.
- Tài liệu [FILE_CATALOG.md](FILE_CATALOG.md) được tạo theo current baseline cần cập nhật trạng thái/đường dẫn sau các migration.
- Chỉ xóa file cũ đã chuyển và không còn dùng. Không xóa historical audits hay dữ liệu Owner vô căn cứ.

**Exit gate:** CI PASS, docs links PASS, không có import/path bị rơi, trạng thái hoàn thành cập nhật trong STATUS/ROADMAP.

## Chiến lược merge & rollback

Owner yêu cầu kết quả đã kiểm thử được merge vào `main`. Dùng nhánh ngắn sống qua CI rồi merge ngay khi PASS; không force-push hoặc xóa local worktree. Mỗi milestone phải rollback bằng Git commit mà **không đụng SQLite/user artifacts**.

**Không làm:** `git clean -fdx`, `reset --hard`, `rm -rf data workspace`, tùy ý chạy generated JS trên host, tự publish/chi tiền.

## Việc cần làm khi chốt docs

**Đã hoàn thành M1 + M2:** frontend ở `dashboard/`, Python package ở `agentforge/`. Lệnh chạy hiện hành tại [DEVELOPMENT.md](../DEVELOPMENT.md), đặc biệt cài lại `pip install -e ".[media]"` sau khi pull. M4 feature-first và M5 compatibility cleanup là các bước tiếp theo; M3 đã làm.
