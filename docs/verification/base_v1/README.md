# Đợt 5 — Base V1 acceptance (09/11/2026)

**Phạm vi:** nghiệm thu nền tảng AgentForge trên Windows một Owner. Công cụ mới giúp kiểm tra **khả năng sẵn sàng**, không biến test/mock thành bằng chứng model hoặc sản phẩm đã chạy trên máy Owner.

## Phân loại bằng chứng

| Gate | CI Windows (trusted code / fixtures) | Owner Windows (yêu cầu tự xác minh) |
| --- | --- | --- |
| Python package, configs, Node/npm, Dashboard build | CI scripts + `ops.preflight`; Node/npm PATH presence không chứng minh version trên Owner | Kiểm tra Python 3.13+, Node 22; build & mở Dashboard |
| API, session, CSRF, Owner permissions | Python HTTP tests dùng server loopback + database fixture | Owner đăng nhập và logout trên browser cá nhân |
| Model Hub text/code routing | Tests kiểm tra routing, rollback, local metadata probe mocks | Chọn model text thật, xác nhận health/model inference riêng |
| Goal / task / approval | `tests.test_s4_brain`; SQLite fixture, permission & SHA gates | Tạo Goal từ prompt, duyệt đúng SHA, xem task detail |
| Artifact validation/acceptance | `tests.test_artifact_acceptance` + HTTP tests; SHA/no spoof, fixture | Kiểm tra artifact, QA thực, chấp nhận/từ chối, rollback |
| Backup, verify, stage restore | `tests.test_ops_reliability`, tmp SQLite (WAL), staged files | Backup local có đồng ý, verify, stage restore, kiểm tra dữ liệu |
| Operations pause/resume | `tests.test_ops_control` dùng temp state | Thử pause/resume thủ công khi không có task đang chạy |
| Generated React sandbox, GPU, ComfyUI motion, YouTube | **KHÔNG chứng minh trong đợt này** | **UNVERIFIED**, theo roadmap riêng |

Các dòng Owner trong bảng luôn **UNVERIFIED** cho tới khi Owner cung cấp bằng chứng riêng. Không cho phép báo cáo một `PASS` tổng chỉ dựa vào unit tests.

## A. Nghiệm thu tự động (an toàn / không chạy model)

Tại checkout sạch; **không** `git clean -fdx`, `git reset --hard`, xóa `data/`, `workspace/` hoặc `.env`:

```powershell
cd D:\AgentForge
git status --short
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
.\.venv\Scripts\python.exe -B -m agentforge.ops.base_acceptance
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunContractTests
```

`base_acceptance` không tạo backup, không ghi file, không gọi model/mạng/ComfyUI, và **luôn** ghi `owner_machine_verified=false`, `production_go=false`. Status `OWNER_REVIEW_REQUIRED` là đúng khi code/config có thể đọc được nhưng Owner chưa nghiệm thu. `BLOCKED` đòi hỏi sửa config/SQLite/registry trước. `-RunContractTests` chạy các **trusted fixture tests** và tạo dữ liệu trong vùng tạm do test quản lý; không chạy generated React source trên host.

Nếu thiếu venv/Node, cần cài dependency chủ động theo [Windows development](../../DEVELOPMENT.md). Mọi kết quả tại CI chỉ phản ánh commit đó, không phản ánh model hoặc GPU trên máy cá nhân.

## B. Checklist nghiệm thu Owner — cần thực hiện trên PC thật

- [ ] **B1 — Setup:** xác nhận Python 3.13+, Node 22, `setup_windows.ps1` không báo `BLOCKED`; chỉ opt-in install khi cần: `-Install -AllowNetwork`.
- [ ] **B2 — Dashboard:** khởi động `.\.venv\Scripts\python.exe -m agentforge --port 8780`; mở `http://127.0.0.1:8780/`. Không đăng mã Owner vào issue, ảnh chụp màn hình hoặc log công khai. Xác nhận đăng nhập, trang Tổng quan, Giao việc, Models, Vận hành, logout.
- [ ] **B3 — Routing:** tại **Cài đặt → AI Models & Routing**, đối chiếu cấu hình model text với runtime thực. Có thể bấm kiểm tra Ollama metadata read-only; đó **không phải inference PASS**. Nếu chủ động thử inference, duyệt riêng quyền gọi model/API và ghi latency/chi phí nếu có. Image/video chỉ config-only.
- [ ] **B4 — Workflow:** tạo một công việc read-only phù hợp nguồn dữ liệu thử có sẵn; xem plan và SHA, kiểm tra quyền, duyệt thủ công, xem task history. Không để automation tự chi tiền/đăng bài.
- [ ] **B5 — Artifact:** với một sản phẩm do bạn chủ động tạo, xem proposal/source SHA, QA thực và acceptance state. Kiểm tra rejection/no-op và rollback khi có artifact hợp lệ. Nếu source AI React chưa đạt build/browser QA, ghi `BLOCKED_BY_PRODUCT_BUILDER`, không tự đánh ACCEPTED.
- [ ] **B6 — Recovery:** sau khi dừng các task đang ghi dữ liệu, chạy backup **chỉ khi Owner đồng ý** và chỉ khi có SQLite thật. Kiểm tra archive và thư mục staging mới; đối chiếu bản snapshot, **không ghi đè DB đang chạy**.
- [ ] **B7 — Operations:** kiểm tra pause/resume tại Cài đặt → Vận hành, không tự chạy job mới sau resume.

**B6 (tạo bản sao không mã hóa chứa dữ liệu nhạy cảm):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -CreateBackup -StageRestore
```

Hai cờ này là hành động có chủ đích. Lệnh chỉ stage vào một thư mục **mới** dưới `workspace/acceptance-restore/`, không apply thay DB hiện hành. Nếu đích đã tồn tại, tool từ chối overwrite. Không gửi ZIP/staged SQLite ra chat hoặc repo; không tự xóa bản gốc, backup hoặc staging nếu chưa đối chiếu.

## C. Điều kiện chốt Base V1

- **CI CODE GATE**: Python full suite, read-only acceptance & focused contract tests, Dashboard/NovaMart builds/browser reference, docs links đều PASS tại HEAD.
- **OWNER LOCAL GATE**: B1–B7 có kết quả/evidence thật và mọi lỗi setup phát hiện đã được sửa.
- **PRODUCT GATE**: không thuộc Base V1; Generated React revision/QA và GPU video còn theo các đợt 6–9.

**Chỉ khi CI và Owner Local cùng đạt mới đánh dấu `BASE_V1_OWNER_ACCEPTED`.** Nếu chưa có B1–B7 thì **`CI_VERIFIED_OWNER_PENDING`**, không phải GO production. Không có quyền tự public/chi tiền, và UI/dashboard chỉ là local một Owner.
