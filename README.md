# AgentForge — Local AI Video Studio

AgentForge là ứng dụng local-first (Python 3.13 + React) cho một Owner, tập trung vào sản xuất video AI và kiểm duyệt trước khi xuất bản. Đây là bản thử nghiệm; GPU, ComfyUI và chất lượng video thực tế chưa được chứng nhận trên máy Owner.

## Chạy trên Windows

```powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Mở http://127.0.0.1:8780/ và đăng nhập bằng mã Owner hiển thị trong PowerShell.

## Phạm vi đang giữ

- Film Studio: episode, shot, motion receipt, FFmpeg assembly, Owner review.
- Character Registry, Model Hub, môi trường chạy và lưu trữ local.
- Publishing handoff có xác nhận Owner, không tự public.
- Dashboard video-first; một số backend và kiểm thử legacy còn đang được loại bỏ.

Không coi CI fixture là bằng chứng model/GPU/video thực tế chạy thành công.

## Tài liệu

- [Hướng dẫn phát triển](docs/DEVELOPMENT.md)
- [Trạng thái cleanup](docs/STATUS.md)
- [Định hướng cleanup](docs/ROADMAP.md)
- [Film Studio](docs/architecture/LONG_FORM_AI_FILM_STUDIO.md)
- [Motion GPU](docs/architecture/FILM_MOTION_12GB_PILOT.md)
- [Nghiệm thu Owner](docs/verification/OWNER_PRODUCTION_GATE.md)

Dữ liệu và model trên máy Owner không được xóa bởi thao tác cleanup Git.
