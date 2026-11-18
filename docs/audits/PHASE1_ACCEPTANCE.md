# Nghiệm thu Đợt 1 — Ổn định nền tảng AgentForge Video Studio

Ngày nghiệm thu: **18/11/2026**. Quyết định: **PASS CI / OWNER RUNTIME CHƯA NGHIỆM THU**.

## Phạm vi nghiệm thu

Đợt 1 chỉ ổn định nền tảng đang giữ: Owner HTTP security/session/CSRF, React Dashboard video-first, Film Studio motion/production/publishing, Character Registry, Video Projects, Model Hub, FFmpeg, operations, backup và retained core services. Đây không phải chứng nhận hoàn thành toàn bộ cleanup module legacy hay sản xuất video AI chạy thực trên PC Owner.

## Bằng chứng từ GitHub Actions

- Commit runtime đã nghiệm thu: [`39766cef`](https://github.com/hieu-mth/AgentForge/commit/39766cef172a00ebf725b89720f22b170eef7dc0).
- [GitHub Actions run #44264562891](https://github.com/hieu-mth/AgentForge/actions/runs/44264562891): **SUCCESS**, cả hai job Windows/Python 3.13 SUCCESS.
- Full suite: **943 tests, 0 failures, 0 errors, 2 skipped**; `python -m unittest discover -s tests -v`.
- Video-focused PowerShell `-RunContractTests`: **107 tests PASS**; không gọi thực GPU/model/provider.
- Independent Owner security + Film project routing job: **5 tests PASS**.
- Dashboard `npm run test:navigation`, `npm run build`, Edge browser smoke, built routing/assets: **PASS**.
- Documentation links, credential/source hygiene, compatibility audit, wheel/import check: **PASS**.
- FFmpeg encode/decode trên fixture video dùng Windows CI: **PASS** (không tương đương QA phim thật).
- Owner runtime preflight PowerShell, M9 setup, read-only owner acceptance: **PASS**.

## Gốc lỗi và thay đổi đã thực hiện

1. Template NovaMart bị loại trước đó nhưng fixture Webapp vẫn tạo proposal React; điều này làm hỏng cả test HTTP Film Studio. Chuyển retained Film/Owner tests sang `tests/owner_http_fixture.py` — server thật, SQLite tạm, không tạo Webapp.
2. Loại khỏi HEAD **21 file test** chỉ phục vụ contract Website/Webapp/Mattress đã bỏ. Xem [PHASE1_REGRESSION_DISPOSITION.md](PHASE1_REGRESSION_DISPOSITION.md). Các test core/security/film còn hợp lệ không được vô hiệu hóa để vượt CI.
3. Cập nhật các test hỗn hợp để xác minh endpoint đã gỡ phải **fail closed**, không ghi workspace, không tạo task hoặc invoke model.
4. Cập nhật `scripts/agentforge_acceptance_windows.ps1`: bỏ hai test Webapp đã xóa, chạy contract Video Studio/Character Registry/Publishing thay thế.
5. Giữ nguyên GitHub full CI suite; thêm job độc lập để tách trạng thái an toàn Video Studio khỏi regression legacy.

## Giới hạn và rủi ro còn mở

- **Chưa kiểm tra trên máy Owner:** RTX GPU/VRAM, ComfyUI thực, Ollama inference, local TTS, runtime dịch vụ dài hạn, QA hình ảnh/chuyển động/nhân vật và video cuối bằng mắt người. Không suy ra Production GO.
- **Chưa hoàn tất cleanup toàn repository:** backend legacy Website/Webapp/Mattress/Growth/Media V1.5 vẫn còn module/dependency và tài liệu lịch sử. Đây là phạm vi Đợt 2–3, không phải lỗi unit test Đợt 1.
- Các 2 `skipped` là kết quả có sẵn của bộ test, không được tính là đã chạy.
- Không xóa/migrate Owner SQLite, media files, workspace, API keys hay model từ local machine trong quá trình này.

## Quyết định

**Đợt 1 hoàn tất trong phạm vi CI stabilization.** Có thể chuyển sang cleanup dependency Đợt 2 mà không tự nhận Video Studio production-ready. Khi sửa runtime ở các đợt sau, cần tiếp tục duy trì đầy đủ cả hai job GitHub Actions và nghiệm thu lại.
