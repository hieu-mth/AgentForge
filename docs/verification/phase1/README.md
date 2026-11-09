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
- Dashboard và static console: execution labels riêng, số sản phẩm Owner accepted riêng, artifact state/details, source syntax validation và explicit accept/reject; lưu source không được gọi là nghiệm thu.

## API và report contracts mới

- GET proposal/webapp và goal/task detail có `artifact_acceptance` additive; không đổi `status` execution cũ.
- POST `/api/artifacts/{webapps|proposals}/{id}/syntax`: `ack=VALIDATE_SYNTAX`, `sha256`; session/CSRF/Origin + đã inspect đúng SHA. Trả syntax report, build/browser False và acceptance projection.
- POST `/api/artifacts/{webapps|proposals}/{id}/decision`: `ack=ACCEPT_ARTIFACT|REJECT_ARTIFACT`, `sha256`, `expected_revision`, `evidence_sha`; Owner phải inspect đúng source. Sai SHA, thiếu QA, stale evidence hoặc quyết định concurrent bị từ chối.
- Syntax sidecar gắn proposal_id/source_sha/report_sha; reader đối chiếu lại parsed source. Static QA v2 giữ semantic PASS_STATIC_ONLY cho syntax hợp lệ; syntax fail không gọi Reviewer và không thành artifact ACCEPTED.
- Các proposal cũ không bị rewrite/re-sign. Legacy scaffold chỉ đọc/ghi theo contract cũ, không dùng như toolchain đã vá hoặc được phép chạy ngầm.

## Kết quả thực thi cuối

| Check | Kết quả | Evidence |
|---|---|---|
| Python toàn bộ suite | **767 lượt OK, exit 0** | python-final.log |
| Control Center JS | **12/12** | js-control-final.log |
| Dashboard JS, gồm acceptance | **18/18** | js-dashboard-final.log |
| NovaMart JS | **5/5** | js-novamart-final.log |
| Dashboard build / Edge | **PASS / PASS** | dashboard-build-final.log, dashboard-browser-final.log |
| NovaMart build / Edge | **PASS / PASS** | novamart-build-final.log, novamart-browser-final.log |
| Locked generated scaffold install | **npm ci exit 0**, scripts disabled | generated-lock-ci.log |
| Dependency audit hai trees | **0 vulnerabilities, exit 0** | dashboard-audit-final.json, novamart-audit-final.json |
| Backend wheel / pip check | **PASS / PASS** | backend-build-final.log, pip-check-final.log |
| Windows read-only acceptance | **PASS, exit 0** | windows-acceptance-final.log |
| Docker thật / inference thật | **UNVERIFIED** | runtime-readiness.json |

767 là lượt unittest, không phải coverage hoặc số tính năng độc lập. Model/provider/network responses trong tests dùng fixtures/mocks; SQLite/files/HTTP và các media/reference-browser tests local có thực thi thật. Security Docker tests mock subprocess và chỉ chứng minh command/gating/cleanup contract, không chứng minh isolation hardware.

Edge smoke dashboard kiểm tra production boot và render 4 acceptance states với **API fixtures**, không giả là authenticated end-to-end acceptance. Python HTTP tests kiểm tra session/CSRF/source inspection/decisions trên server local thật. NovaMart Edge kiểm tra search/detail/cart/filter/mobile/offline. Ảnh: [acceptance workspace](acceptance-workspace.png).

Lần full suite đầu có hai regression thật (sidecar inventory và coupling execution với missing artifact) đã sửa code, giữ test cũ. Một request HTTP guard từng bị WinError 10053; focused test và full suite cuối đều PASS, không sửa test để bỏ guard. Log lần đầu giữ tại python-full.log. Build logs có PowerShell NativeCommandError wrappers cho npm/pip stderr notices; exit codes cuối đều được thu riêng và output build hoàn tất, không coi notice là lỗi hoặc giấu failure.

## Tái lập

```powershell
python -m pip install -e '.[media]'
npm.cmd ci --prefix ui/dashboard --ignore-scripts --no-audit --no-fund
npm.cmd ci --prefix examples/novamart --ignore-scripts --no-audit --no-fund
python -m unittest discover -s tests -v
node --test tests/test_control_center_task_detail.cjs tests/test_control_center_v11.cjs tests/test_ops_control_ui.cjs
npm.cmd run test:navigation --prefix ui/dashboard
npm.cmd test --prefix examples/novamart
npm.cmd run build --prefix ui/dashboard
