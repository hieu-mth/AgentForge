# Phase 1 — Reliability & Acceptance

Ngày: 09/11/2026 (Asia/Bangkok). Base: `6fbaa47026ba2788ea8127bef8abe17a5f2a9bb3`, branch `main`. Không push; không inference trả phí, deploy, destructive migration, đổi secrets hoặc chỉnh runtime data của Owner. Thư mục audit chưa commit từ lượt trước được giữ nguyên, chỉ roadmap được bổ sung trạng thái triển khai.

## Vấn đề đã sửa và kiến trúc trước/sau

Trước: workflow có thể SUCCEEDED khi static QA chỉ kiểm tra shape/provenance và Reviewer REVISE. Source JSX sai vẫn qua contract. UI đếm workflow success như hoàn tất, chưa có ledger nghiệm thu.

Sau: workflow execution vẫn giữ enum/hợp đồng cũ để tương thích. Artifact acceptance được lưu trong các bảng **additive** ở task SQLite: artifact_acceptance, artifact_validations, artifact_decisions. Không đổi goal/task lịch sử hoặc proposal digest. Đọc legacy không tạo acceptance table hoặc tự chấp nhận sản phẩm.

| Artifact | Gate bắt buộc trước Owner acceptance |
|---|---|
| Static website | Contract + static quality xác minh từ source |
| Interactive website | Contract, JavaScript syntax, browser QA |
| React template / AI source | Contract, patched locked toolchain, syntax, isolated build, browser QA |

REVISE hoặc validation FAIL → NEEDS_REVISION. Thiếu gate → NEEDS_VALIDATION. Đủ gate → READY_FOR_REVIEW, **không tự ACCEPTED**. Owner quyết định riêng trên đúng source SHA, evidence digest và expected revision; transaction BEGIN IMMEDIATE chặn concurrent decisions ghi đè. Evidence mới làm quyết định cũ mất hiệu lực nếu không còn đủ điều kiện. Không có HTTP route cho client tự khai QA PASS.

Phase 1 chưa triển khai browser runner cho React AI: BROWSER_VALID vẫn thiếu, nên source AI không thể được nghiệm thu chỉ với parser/build. Preview tương tác luôn disabled và không có route chạy source trên Owner origin.

## Modules thay đổi

- `core/artifact_acceptance.py`: policy theo loại artifact, evidence gắn SHA, state projection và Owner decisions, đọc legacy an toàn.
- `core/skill_runner.py`, `core/brain_runner.py`, `control_center_v1.py`: ghi evidence từ trusted producers; trả execution và artifact status riêng. Artifact không tìm thấy được ghi checkpoint, không viết lại execution contract cũ và không tạo acceptance.
- `domains/webapps/syntax.py`: Tree-sitter 0.25.2 + grammar JS 0.25.0 parse source như dữ liệu, không subprocess/eval/import source. Diagnostics chỉ filenames đã allowlist và vị trí. Đây không phải security sandbox hoặc chứng minh build/runtime.
- `domains/webapps/developer.py`, `builder.py`: scaffold locked mới, parser/sidecar syntax reports dưới `proposals/syntax/`; không trộn report vào proposal inventory. Legacy SHA/scaffold còn đọc được, toolchain cũ bị chặn ở QA hiện tại.
- `domains/webapps/static_qa.py`: report v2 chứa syntax report cùng source SHA, malformed source cho FAIL_SYNTAX; reader v1 giữ nguyên SHA, không bịa thêm syntax evidence. Reviewer từ chối source syntax fail trước inference.
- `domains/webapps/toolchain.py`, package manifests/locks, CI và sandbox Dockerfile: Vite 7.3.7 patch trong major 7; esbuild 0.28.1 nằm trong supported dependency range của Vite; npm ci/ignore-scripts. Lock generated project đã được npm ci độc lập kiểm tra, không chạy app scripts/source trên host.
- `domains/webapps/sandbox.py`: giữ process approval/local daemon/pinned image/network none/read-only/non-root/resource caps, kiểm tra patched toolchain trong image; cleanup khi timeout/launch ambiguity/interruption. BUILD_VALID không ghi browser PASS.
