# Development Roadmap

## Cập nhật triển khai Phase 1 — 09/11/2026

Phần roadmap audit bên dưới được giữ lại làm snapshot tại `6fbaa47`. Trạng thái mới:

| Mục | Đã triển khai | Giới hạn còn lại |
|---|---|---|
| R01 | Vite 7.3.7 / esbuild 0.28.1; lock dashboard, NovaMart và scaffold; CI/Dockerfile dùng npm ci; hai npm audit 0 advisory | Chưa rebuild/chạy Docker image thật vì không có Docker CLI/image; guard runtime từ chối image cũ |
| R02 | Acceptance ledger SQLite riêng với execution history; REVISE → NEEDS_REVISION; gates theo artifact/source SHA; Owner decision + revision/evidence CAS; UI tách hai trạng thái | React chưa thể ACCEPTED nếu thiếu browser QA; không tự tạo PASS cho gate chưa chạy |
| R03 | Giữ preview disabled, không host/Owner-origin execution; env allowlist/network none/non-root/resource caps; cleanup cả timeout/OSError/interrupt; indirect API regression | Isolation thực trên Docker/hardware UNVERIFIED; không nới quyền hoặc mở preview |
| B01 / phần syntax R04 | Parser Tree-sitter JS/JSX, diagnostics an toàn, report gắn SHA; static QA v2 đọc được report v1; source sai bị chặn | SYNTAX_VALID không phải BUILD_VALID; browser/build vẫn cần bằng chứng riêng |

Commits: `b97a6cc` dependency, `e8f1efe` acceptance, `4a7ab6d` syntax, `1657ede` security. Final verification: **767 Python tests OK, 35 JS tests PASS, 2 builds + 2 Edge smokes PASS, generated-lock npm ci PASS, backend wheel/pip check/Windows acceptance PASS**. Không gọi model trả phí hoặc sửa dữ liệu Owner.

Chi tiết, kết quả và điều kiện bắt đầu Phase 2: [Phase 1 verification](../verification/phase1/README.md). Chưa triển khai source revision, browser runner, full-stack, deadline/cancel hoặc Phase 2–5.

Roadmap theo phát hiện của audit 09/11/2026. Mỗi hàng là milestone nhỏ có thể commit riêng; độ phức tạp tương đối S/M/L, không phải ước tính lịch chắc chắn. Giữ production modules hiện tại, không rewrite.

## M0 — Đóng điều kiện chặn phát hành

| Việc / ưu tiên | Evidence và nguyên nhân | Giải pháp / modules | Phụ thuộc; độ phức tạp; rủi ro | Acceptance và test |
|---|---|---|---|---|
| R01 Dependency security, P0 release gate | B05, npm-audit-resolved.log; Vite pin 7.3.1 có advisory | Patch dashboard + NovaMart trusted manifest; regenerate reviewed sandbox image; record SBOM/lock | Không; M; upgrade có thể đổi build hoặc trusted scaffold comparisons | Scanner không còn high/critical áp dụng được chưa xử lý; test React/source revalidation + 2 build + Edge smoke PASS; review lower advisories riêng |
| R02 Acceptance semantics, P0 release gate | B01/B02/B06; audit-checks.log: invalid source/REVISE -> SUCCEEDED | Artifact acceptance state riêng; label dashboard; policy linking syntax/build/browser/review reports cùng SHA; core/brain_runner, result_view, UI Workspace/Webapps | Không; M; tương thích status/history cũ | REVISE => NEEDS_REVISION; static-only => NEEDS_VALIDATION; invalid source không ACCEPTED; migration nhẹ/không destructive; tests status + UI + legacy records |
| R03 Generated runtime boundary, P0 trước interactive preview | B03; regex indirect API được nhận | Giữ no-host-execution; egress isolation và origin riêng; parser bổ sung nhưng không thay sandbox; sandbox.py/control_center/UI | R01; M; preview có thể lộ console cookie nếu làm sai | Indirect APIs không nhận secrets/cookies/network; test isolated origin/CSP/request blocking và cleanup; không tự bật quyền trong prompt |

P0 ở đây là **điều kiện chặn phát hành**, không phải tuyên bố có exploit nghiêm trọng đã khai thác. Không mở host execution/Internet trong khi các điều kiện còn thiếu.

## M1 — Một sản phẩm React offline được nghiệm thu thật

