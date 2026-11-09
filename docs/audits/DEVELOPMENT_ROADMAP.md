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

| Việc / ưu tiên | Evidence và nguyên nhân | Giải pháp / modules | Phụ thuộc; độ phức tạp; rủi ro | Acceptance và test |
|---|---|---|---|---|
| R04 Syntax/build reports, P1 | B01/B06; static_qa.py:65 không parser | Extend sandbox parser + build, typed report tied source SHA, persist report artifacts | R01–R03; M; Docker image/toolchain không sẵn | Malformed JSX/import/dependency fixtures fail có diagnostic; hợp lệ build PASS trong network-none; timeout cleanup; stale report không dùng được |
| R05 Browser flow QA, P1 | B06; template smoke không chứng minh source AI | Separate approved browser run trên artifact built trong runtime isolation; assert required user flows; show preview + results | R03/R04; L; untrusted JS, resource usage | Search/form/local CRUD/modal theo brief có assertions, responsive checks 3 viewports; runtime error/blank page/network attempt => fail; report cùng SHA, build success không thay browser pass |
| R06 Context review đầy đủ, P1 | B07, reviewer.py:59–73 bỏ file phụ | Manifest/dependency-linked context + omitted/truncated metadata; combine deterministic tests, AI advisory remains bounded | R04; M; token tăng và prompt injection | Tests prompt include helpers/components cần thiết; omission hiển thị; reviewer không cấp deployment; usage/cap respected |

## M2 — Feedback trở thành thay đổi source

| Việc / ưu tiên | Evidence và nguyên nhân | Giải pháp / modules | Phụ thuộc; độ phức tạp; rủi ro | Acceptance và test |
|---|---|---|---|---|
| R07 Immutable version + patch, P1 | B04; developer.propose không có base source, API revision bị chặn | version_id/base_sha/files manifest/feedback; source-aware patch proposal; read-only diff, apply atomic, rollback backup; developer.py, webapp_feedback, control_center, UI | R02/R04; L; regression và overwrite | Một app -> đổi layout -> thêm view -> sửa chức năng -> sửa lỗi; hashes/diffs đúng; unaffected files giữ nguyên; no-op/stale base/concurrent edit fail closed; original vẫn nguyên; R05 chạy lại đúng version |
| R08 Scope-aware intake, P1 | FEATURE_MATRIX; fixed catalogue schema không thể đáp ứng full-stack | Show capability contract trước run; route static/marketplace/custom local UI; unsupported backend requirement cần scope clarification, không silently landing-page | Không; M; keyword routing regression | Bộ brief landing/business/multi-page/ecommerce/dashboard/SaaS/full-stack có kỳ vọng rõ; không tuyên bố WORKING cho payment/auth/DB chưa có; test routing + UI scope |

## M3 — Reliability, chi phí và phát hành MVP

| Việc / ưu tiên | Evidence và nguyên nhân | Giải pháp / modules | Phụ thuộc; độ phức tạp; rủi ro | Acceptance và test |
|---|---|---|---|---|
| R09 Deadline/cancel/resource journal, P1 | B08/B09; socket timeout, pause chỉ chặn bước kế; model.py/core runner | Monotonic deadline, cooperative cancel, adapter usage return, reservations/actuals/reconcile journal; model.py, task_history, brain_runner, workspace_policy, UI | R02; L; task side effects và billing ambiguity | Fake-clock continuous chunks vẫn timeout; cancel active call không retry; no double-spend concurrent claims; record usage/latency/provider, giá unknown hiển thị unknown; monetary cap chỉ dùng khi pricing verified |
| R10 Reproducibility/docs/tooling, P2 | B10; README freeze cũ, lock thiếu, check chỉ api.js | Lock transitive deps/toolchain; CI lint/type policy; README generation modes; audit coverage; consolidate ownership of entrypoints sans removing aliases; wheel distribution contract | R01; M; lock/platform differences và aliases regression | Clean install + npm ci/Python locked install + build/test; documented source-tree vs wheel support; no stray ROOT relocation; alias tests PASS; no silent production data migration |
| R11 Crash reconciliation, P1 trước unattended use | core/brain_runner.py:44: stores commit riêng, risk chưa tái hiện | Fault-inject parent/child/artifact commit windows; small reconciler using dispatch journal; retain no-replay by default | R02/R09; M; false recovery có thể replay tool | Kill/restart test trước/sau external result commit; consistent INTERRUPTED/needs review state, exactly-once claim, không tự gọi lại ambiguous side effect |
| R12 Performance/admin UX, P2 | dashboard-build.log chunk JS ~1.238 MB, visual admin chưa audit đầy đủ | Route-based code split nếu số đo hỗ trợ; browser test logged-in admin, mobile/dark/error states | R02; M; routing/loading regression | Login -> submit -> progress -> result -> feedback -> version -> validation flows; keyboard/contrast/overflow checks; compare boot/asset bytes baseline; production build và source navigation tests PASS |

## M4 — Khả năng nâng cao sau MVP

- **P3 backend product contracts:** chỉ thêm khi nhu cầu xác nhận. Tạo allowlisted service/schema/migration/API contract trước, rồi auth/CRUD demo; threat model/secrets/tenant/backup tests riêng. Không nới regex/file allowlist rồi gọi đó là full-stack.
- **P3 adaptive planning:** mở rộng template/typed subtasks dựa trên acceptance data; quota/tool policy vẫn thuộc trusted code. Không cần recursive multi-agent tự cấp quyền.
- **Chưa cần:** microservices, Kubernetes, multi-region, automatic public deploy, revenue automation, provider framework lớn hoặc vector database mặc định.

## Điều kiện GO cho MVP giới hạn

MVP công bố rõ website tĩnh/React offline prototype. R01–R09 có bằng chứng nghiệm thu phù hợp phạm vi; không high/critical advisory áp dụng được bị bỏ qua; generated code chạy trong boundary đã kiểm tra; revision có đúng source hash và validation cùng version; restart/recovery không replay chi phí ngầm.

Owner chọn một tập brief đại diện và duyệt model/provider/cost budget trước real inference. Ghi tỷ lệ generation/build/browser/user-flow pass và lỗi revision từ những lần chạy thực, không từ mock. Chỉ đưa phần trăm hoàn thiện khi có denominator/rubric này. Không đặt lịch hay chi phí giả định trong roadmap.
