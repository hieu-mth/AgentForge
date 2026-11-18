# Nghiệm thu AgentForge Video Studio trên máy Owner

Phạm vi hiện hành: một Owner, Windows localhost, Film Studio, Character Registry, Model Hub, media render và publishing handoff có duyệt. CI chỉ chứng minh source/build/contract; không chứng minh GPU hoặc video thực tế.

## Chuẩn bị

```powershell
cd D:\AgentForge
git status --short
git switch main
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
```

Không dùng `git clean -fdx`, `reset --hard` hoặc xóa `data/`, `workspace/`, `.env`, `models/`. Các kết quả preflight không chứng nhận inference hay video.

## Tiêu chí nghiệm thu

| Phạm vi | Bằng chứng bắt buộc |
| --- | --- |
| Dashboard | Đăng nhập Owner; session/CSRF; xem Film Studio, Model Hub, Character Registry và tình trạng hệ thống trên localhost |
| Local model | Model tồn tại, suy luận thực trên Ollama (chỉ khi Owner chủ động cho phép); không tự fallback lên cloud |
| Character Registry | Tạo/chọn nhân vật đã đăng ký, tham chiếu và metadata đúng; không giả nhận dạng ảnh |
| ComfyUI / GPU | Chạy một shot được Owner cho phép; ghi model, receipt, VRAM thực tế nếu đo được, thời gian và lỗi |
| Film assembly | MP4 có motion thực, FFmpeg/ffprobe decode, SHA receipt, tiếng/phụ đề được kiểm tra |
| Continuity | Owner xem nhiều shot và duyệt tính nhất quán nhân vật/cảnh, không chỉ dựa metadata |
| Publishing | Owner duyệt từng release, kiểm tra quyền tài khoản; không tự suy ra đã upload từ handoff |
| Local data | Backup/restore thử trong staging độc lập, không ghi đè database đang dùng |

Tài liệu thao tác Film Studio: [Motion 12GB](../architecture/FILM_MOTION_12GB_PILOT.md), [Film Studio](../architecture/LONG_FORM_AI_FILM_STUDIO.md), [Runtime checklist](runtime_2026_11/README.md).

## Ranh giới

Website/Webapp/Growth, bán nệm, các template commerce và các Wave nghiệp vụ lịch sử **không thuộc phạm vi phát hành**. Không sử dụng tài liệu hoặc test legacy để tuyên bố tính năng đó còn được hỗ trợ. Phần source, manifests và callers chưa gỡ sạch phải tiếp tục được xử lý trong cleanup Đợt 4. Chỉ phát hành khi runtime trên PC Owner có evidence; không gán Production GO từ CI fixture.
