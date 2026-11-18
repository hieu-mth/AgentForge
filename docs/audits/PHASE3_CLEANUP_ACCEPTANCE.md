# Đợt 3 — Cleanup Structure, Tests & Documentation

Ngày: 18/11/2026. **Kết luận: PASS cho phạm vi cleanup đã kiểm chứng trên Git/Windows CI; chưa phải chứng nhận repository hoàn toàn không có legacy.**

## Bằng chứng

- Baseline cuối Đợt 2: `9ac7f57f8952d8ee2db39850983a8f74fc0b75e4`.
- Mốc đã nghiệm thu: [`f55d3172`](https://github.com/hieu-mth/AgentForge/commit/f55d317224ea15c63143bcb3d7372d10c825432b).
- [GitHub Actions #44281787675](https://github.com/hieu-mth/AgentForge/actions/runs/44281787675): **SUCCESS**, cả hai job Windows/Python 3.13.
- Full Python suite: **777 tests, 0 errors, 0 failures, 2 skipped**.
- Video Studio isolated contracts: **112 tests PASS**; independent Owner/API boundary: **7 tests PASS**.
- React navigation/build, Edge browser smoke, docs links, source hygiene, compatibility audit, wheel/import, FFmpeg encode/decode fixture, PowerShell preflight và read-only acceptance: **PASS**.

## File cleanup thực tế

So sánh Git `9ac7f57f...f55d3172`: **18 commits, 226 file thay đổi; 186 file xóa, 40 file sửa**.

| Nhóm xóa | Số lượng |
| --- | ---: |
| Backend Python | 45 |
| Dashboard JS / test | 17 |
| Markdown documentation | 91 |
| Skill manifests | 13 |
| Python tests | 15 |
| Worker configs | 2 |
| Examples | 3 |
| **Tổng** | **186** |

Đã loại bỏ các shim `agentforge/domains/`, Media Workflow V1.5, business autopilot V1.3/Quality V1.4, nhiều legacy dashboard helpers và business examples, Growth/Webapp dispatch manifests, cùng Markdown milestones/QA không còn làm nguồn chân lý. Full CI giữ nguyên; test về security, session, Film Studio, Publishing và Model Hub tiếp tục được chạy.

## Model Hub và dữ liệu Owner

`config/task_routes.toml` không còn phơi các route `web.create`, `webapp.*`, `growth.report`, `media.copy_draft` trong bảng cấu hình tác vụ mới. `ai/model_hub.py` vẫn đọc được overlay cũ có những route đó mà **không tự di chuyển/sửa SQLite khi GET**; chúng không được chạy qua routing mới, không được cấu hình lại thành active route. Có kiểm thử regressions trường hợp SQLite owner lịch sử và các deterministic rules.

## Những phần còn caller, chưa đủ bằng chứng để xóa an toàn

- **29 Python files** còn trong `features/websites/`, `features/webapps/`, `features/growth/` (bao gồm `__init__.py`). Một số vẫn có caller trong test/core/legacy CLI hoặc là reader dữ liệu lịch sử. Chúng không thuộc Owner API video-first nhưng việc xóa vật lý cần tiếp tục truy vết và thay thế read path.
- Một số root compatibility aliases, web skill manifests và worker configs còn được tests/core sử dụng. Không suy ra UNUSED từ việc sidebar không còn menu.
- `agentforge/core/brain_planner.py` vẫn có parser template lịch sử để đọc/kiểm chứng goal lưu sẵn; Owner API phải tiếp tục **fail closed** khi tạo job mới thuộc nhóm đã nghỉ.
- Đợt 4 cần đối chiếu chính xác callers còn lại và phân loại thành **read-only archive cần giữ**, **có thể xóa**, hoặc **runtime leakage phải sửa**. Chưa đạt tiêu chí "zero legacy files".

## Giới hạn chứng nhận

GitHub runner không chứng thực inference Ollama/ComfyUI trên GPU máy Owner, TTS tiếng Việt, tính liên tục nhân vật, chất lượng MP4, OAuth thực hay upload YouTube. Các lượt kiểm thử dùng fixture không cấp quyền xuất bản. Không chạy lệnh xóa/migrate `data/`, `workspace/`, `.env`, model checkpoint hoặc video Owner.

## Verdict

**PASS: Đợt 3 source/documentation consolidation + regression CI.**

**OPEN: quyết định xóa 29 file feature legacy và một số root alias/skill/worker còn callers.** Không được gọi repository là hoàn toàn sạch cho tới khi Đợt 4 chứng minh được ranh giới hoặc loại hết dependency cần xóa.
