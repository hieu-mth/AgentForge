# AgentForge — Roadmap thực thi

**Cập nhật:** 10/11/2026. Đây là roadmap **hiện hành**, thay cho các bản V4/C8 trong tài liệu lịch sử. Chỉ đánh dấu DONE khi đạt tiêu chí kiểm chứng; mocked tests không thay thế real-model testing.

## Quyết định kiến trúc repository

Đã chốt [flat-root architecture](architecture/TARGET_STRUCTURE.md): **M1 Dashboard và M2 Python package đã chuyển** thành `dashboard/` và `agentforge/` ngay root. Kiến trúc Feature-First Modular Monolith vẫn là đích; chia API **M3 đã xong**; M4a–M4d2 **đã chuyển** Growth/Website/Webapp/Media/Film và HTTP ComfyUI. M4 research/ops còn review; M5 đã chuyển 22 root aliases trỏ thẳng canonical `features/` và thêm audit CI; **chưa xóa** alias công khai. Xem [migration plan](architecture/MIGRATION_PLAN.md).

## Base V1.0 — Model Hub

**M0/M3:** API đã chia và có security contracts. **M6:** registry/text worker routing, SQLite Owner revision/rollback. **M7:** Dashboard AI Models & Routing, model profiles, local metadata probe và xác nhận Owner. **M8 (adapter foundation):** tách 30 skill policies + trusted handlers sang 5 nhóm domain, giữ permission gate hiện hữu. **M4a:** Growth đã chuyển sang `features/growth/` (giữ compatibility aliases). **M4b:** Website đã chuyển sang `features/websites/`, giữ CLI và import aliases. **M4c:** Webapps đã chuyển sang `features/webapps/`, giữ CLI/compatibility. **M4d1:** shared Media và Film Studio đã chuyển sang `features/media/` và `features/film_studio/`. **M4d2:** HTTP transport ComfyUI đã tách vào `integrations/comfyui.py` (localhost-only, giới hạn response, giữ patch point). M4 research/ops và M5 phase 2 (chỉ xóa alias sau deprecation/evidence) còn chờ; M9 setup/operations: preflight chỉ đọc, script Windows opt-in và Dashboard trạng thái môi trường đã triển khai; phần benchmarking model thực và automated install trên máy Owner còn chờ. Xem [Skill Engine](architecture/SKILL_ENGINE.md).

[Model Hub](architecture/MODEL_HUB.md) phân biệt routing đã nối ở text và video/image mới config-only, không tự chạy GPU/cloud.

## Đợt 5 — Base V1 Acceptance

Đã bổ sung báo cáo read-only (`python -B -m agentforge.ops.base_acceptance`), Windows acceptance script có bộ trusted contract tests và tùy chọn backup → verify → staged restore có xác nhận. **CI chỉ xác minh code/fixture; trạng thái nghiệm thu PC/model/artifact của Owner là PENDING** tới khi checklist B1–B7 được chạy có evidence. Xem [Base V1 Acceptance](verification/base_v1/README.md).

## Hai hướng sản phẩm cần hoàn thiện

| Track | Mục tiêu kinh doanh | Tình trạng |
| --- | --- | --- |
| **AI Film Studio** | Tạo phim AI chuyển động nguyên bản, đủ chất lượng để phát triển kênh YouTube | Planner + adapter ComfyUI đã merge, GPU/runtime chưa xác minh |
| **AI Product Builder** | Tạo **và sửa** website/React app theo feedback, có preview và version | Website/catalog revision có; React AI source revision chưa có |

Không mở rộng thêm agent/worker hoặc microservice khi hai vòng lặp này chưa hoạt động đầy đủ.

## Film Studio — 6 mốc lớn

| Mốc | Deliverable | Nghiệm thu / trạng thái |
| --- | --- | --- |
| F1. Film planning | Chapter, cast/visual bible, shot slots 4–15 giây, SHA, CLI | **DONE ở mức planner**, không có video thật |
| F2. Motion worker local 12 GB | Adapter ComfyUI + one-shot GPU + local verified MP4 | **Code/CI Wave8**, cần 1 clip Wan 2.2 thật và Owner VRAM/time/quality để chốt F2 |
| F3. Continuity | Cast bible, costume/reference SHA, shot notes | **Code/CI Wave 9**, visual consistency 3–5 shot Owner PENDING |
| F4. Film editor/QA | FFmpeg hard-cut, local voice/SRT, SHA receipt, versioned edits | **Code/CI Wave 9**, real 60–90s film Owner PENDING |
| F5. Long-form production | Theo tập/chapter, resume/checkpoint, resource budget, kiểm tra consistency xuyên tập | Chưa: mục tiêu 15–30 phút/tập, sau đó ghép 1–3 giờ |
| F6. YouTube operations | OAuth Desktop optional, private upload, release SHA, metadata/owner status, local schedule intent, manual analytics | **Code/CI Wave 10**, real OAuth/private upload Owner PENDING, no automatic public scheduling or verified monetization |

**Không được coi “phim 2 tiếng” đã hoàn tất chỉ vì có 900 slot trong JSON.** 900 clip ở 8 giây/shot còn đòi hỏi generation, selection, QA và dựng hậu kỳ; điều kiện phần cứng có thể buộc sử dụng offload hoặc API trả phí với quyền riêng.

### Thứ tự thực thi gần nhất

1. Chạy 4 giây T2V thực bằng ComfyUI/Wan 2.2 5B trên GPU 12 GB, đo peak VRAM và thời gian; fail thì điều chỉnh profile/model, không tự đoán kết quả.
2. Import MP4 có kiểm tra SHA + ffprobe/FFmpeg decode; không cho QA PASS chỉ vì ComfyUI history success.
3. Dựng 60–90 giây nhiều shot có chung nhân vật, voiceover/subtitles và continuity audit.
4. Mở rộng lên tập 15–30 phút trước khi thử một phim dài hàng giờ.

## Đợt 9 — Film Production Pipeline

Code/CI: draft episode từ Wave 8 receipts; cast bible và mỗi-shot reference/costume/location/props/action/camera/caption; metadata continuity changes cần lý do. 3–5 shot (~12–20s) hoặc 15–22 shot (~61–90s), không loop clip; Owner-only TTS Windows/Piper, SRT, FFmpeg + ffprobe/full decode video/audio, receipt SHA và versioned edit (không regenerate GPU shots cũ). **Real 60–90s film, true GPU, voice và visual continuity PENDING**. [Wave 9](verification/wave9/README.md).

## Đợt 10 — Publishing & Business Operations

Local film release ledger từ Wave 9 đã kiểm SHA, Owner watch/rights và disclosure, planned UTC **không tự schedule**, YouTube Studio manual handoff, metrics do Owner ghi. Tùy chọn OAuth Desktop bằng CLI gửi video lên YouTube **private-only**, idempotent uncertain checkpoint, không tự public, auto-spend hoặc ghi nhận doanh thu. **Code/CI chỉ xác minh hợp đồng; Owner real OAuth/private upload vẫn PENDING**. Xem [Wave 10](verification/wave10/README.md).

## Đợt 8 — Film Studio runtime 12 GiB

Code có mẫu core-node Wan2.2 5B, 640×352/49 frames/12 fps, one-shot Owner-gated, local output import với job/plan/workflow SHA, ffprobe+FFmpeg decode và receipt. Model Hub film.motion vẫn config-only, không lấy model tùy ý từ LLM, không auto-download/cloud/retry/upload. **Owner GPU 12GB và chất lượng clip PENDING**. Xem [Wave 8](verification/wave8/README.md). F2 chỉ chốt khi có file MP4, thời gian và VRAM thật.

## Đợt 7 — Product QA và Export

Lập Goal `webapp.browser_qa` 0 model calls, 1 Owner-approved process run, Docker Chromium offline, source readonly, screenshot desktop/mobile + báo cáo SHA; export ZIP source signed manifest. CI chỉ kiểm tra code/fixture, **Owner browser runtime và chức năng thực tế vẫn UNVERIFIED**. Xem [Wave 7](verification/wave7/README.md).

## Đợt 6 — AI React revision

Đã thêm kế hoạch webapp.source_revision, API revision cho AI JSX/CSS, partial-file edits được gắn source SHA, immutable version và diff; rollback tạo proposal riêng chỉ từ verified ancestor. Bản nguồn AI vẫn chưa được chạy/kiểm thử trên browser cách ly, model thực chưa được benchmark. Xem [Wave 6 acceptance](verification/wave6/README.md).

## AI Product Builder — roadmap song song

| Ưu tiên | Việc | Definition of done |
| --- | --- | --- |
| P0 | Source-aware revision cho AI React | **Code/CI Wave 6**: file edits, SHA, diff/version, rollback proposal, Owner approval; real-model/browser QA chưa xác minh |
| P0 | Build/browser QA riêng biệt | Chạy ở sandbox kiểm chứng, ảnh/chức năng/console errors, evidence gắn SHA |
| P1 | Adaptive planning & multi-file | AI chọn plan theo capabilities, không keyword-landing bias; filename linh hoạt trong policy |
| P1 | Benchmark mẫu | Brief chuẩn, tính tỷ lệ tạo/sửa/QA thành công, latency và chi phí model thật |
| P2 | Export/Deploy theo ý Owner | Zip/source bàn giao có thể khôi phục và hướng dẫn triển khai |

## Release gates áp dụng cho cả hai track

- Mọi sản phẩm được theo dõi bằng **source/artifact SHA** và bằng chứng kiểm tra phù hợp.
- Owner có quyền xem, từ chối, yêu cầu sửa và rollback; không tự public hoặc chi tiền.
- Không xóa/migrate dữ liệu không thể khôi phục mà thiếu backup và kiểm thử.
- Dữ liệu thật, model thật, runtime thật và chi phí thật phải ghi nhận riêng so với fixture/mocks.
- CI Windows PASS mới merge `main`; đánh dấu BLOCKED nếu hạ tầng Owner chưa sẵn sàng.

Để hiểu tại sao những việc này được chọn, xem [trạng thái hiện tại](STATUS.md), [audit Phase 1](verification/phase1/README.md) và [roadmap audit lịch sử](audits/DEVELOPMENT_ROADMAP.md).
