# Runtime — AgentForge Video Studio (Windows / Owner)

Đây là checklist chạy thực tế, không phải chứng nhận Production GO. Không suy ra GPU, motion, voice, upload hay chất lượng video từ CI fixture.

## 1. Preflight mặc định (read-only, không gọi model)

```powershell
cd D:\AgentForge
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
```

Kiểm Python/Node, model catalog Ollama, ComfyUI, FFmpeg và HTTP Dashboard. Không cần Webapp Docker QA; Film Studio hoạt động với ứng dụng local được Owner cài riêng. Receipt được lưu trong `workspace/runtime-certification/` khi bật SaveReport; không upload receipt hoặc secret.

## 2. FFmpeg fixture thực (Owner chủ động)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunFFmpeg -ConfirmLocalExec -SaveReport
```

Chỉ chứng nhận encode/decode clip tạm 1 giây, không phải motion do AI tạo.

## 3. Một lượt Ollama local (Owner chủ động)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunOllama -ConfirmInference -ModelRef local_primary -SaveReport
```

Script dùng một prompt cố định, không truyền dữ liệu riêng tư, không pull model và không fallback cloud. PASS_RUNTIME chỉ cho kiểm tra text inference.

## 4. ComfyUI, shot thật và Film Studio

Dùng [Motion 12 GiB](../architecture/FILM_MOTION_12GB_PILOT.md) và [Film Studio](../../architecture/LONG_FORM_AI_FILM_STUDIO.md).

- Xác nhận ComfyUI chỉ phục vụ loopback; workflow và weights được Owner xem, pin SHA.
- Chạy một shot được phép; không retry nếu trạng thái submit chưa chắc chắn.
- Import MP4 thực, đối chiếu frame count, thời lượng, SHA, ffprobe/FFmpeg decode.
- Owner tự phát video, kiểm chuyển động, character consistency, voice/subtitles; ghi lại latency/VRAM đo được nếu có.
- Ghép multi-shot theo manifest, rồi nghiệm thu và quyết định publish riêng biệt.

## 5. Dashboard / dữ liệu

```powershell
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Đăng nhập Owner tại `http://127.0.0.1:8780/`; kiểm session/CSRF, Character Registry, Film Studio và Model Hub. Backup/restore chỉ trong staging; không ghi đè SQLite đang dùng.

## Verdict

| Bằng chứng | Kết luận được phép |
| --- | --- |
| Windows CI/build và fixture FFmpeg | CODE_CONTRACT_PASS |
| Ollama inference một lượt trên PC | LOCAL_TEXT_RUNTIME_PASS |
| Clip ComfyUI thực, decode và SHA khớp | MOTION_TECHNICAL_PASS |
| Owner xem và chấp nhận continuity/voice/video | OWNER_VIDEO_REVIEW_PASS |
| Publish thực được Owner duyệt và xác minh | PUBLISH_VERIFIED |

Website/Webapp/NovaMart, Growth, bán nệm và các Wave nghiệp vụ đã nghỉ **không thuộc checklist này**. Không xây Docker image từ `templates/novamart`: thư mục đó đã bị xóa. Dữ liệu, model, credential và workspace của Owner luôn nằm ngoài cleanup Git.
