# AgentForge — Local AI Video Studio

AgentForge là nền tảng video AI local-first (Python 3.13 + React/Ant Design), tập trung vào Film Studio, Character Registry, media generation, Model Hub và publishing handoff có xác nhận Owner. Các nghiệp vụ ngoài Studio không nằm trong runtime hiện hành.

## Chạy trên Windows

```powershell
cd D:\AgentForge
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
```

Mở http://127.0.0.1:8780/dashboard/ và đăng nhập bằng mã Owner được in riêng tại terminal. Model Hub khởi tạo với **không model nào được đăng ký**; Owner thêm và phân công model qua Dashboard. Capability metadata nằm trong Python, không còn thư mục `config/`. Chỉ bật `--allow-external-tools` khi chủ động chạy các tác vụ media đã review. Ứng dụng không tự cài ComfyUI, tải weights, kích hoạt GPU hay public YouTube.

## Hướng dẫn

- [Phát triển và CI](docs/DEVELOPMENT.md)
- [Cấu trúc nền tảng](docs/architecture/REPOSITORY_STRUCTURE.md)
- [Film Studio](docs/architecture/LONG_FORM_AI_FILM_STUDIO.md)
- [Motion ComfyUI 12 GiB](docs/verification/MOTION.md)
- [Production/FFmpeg](docs/verification/PRODUCTION.md)
- [Publishing handoff](docs/verification/PUBLISHING.md)
- [Owner runtime acceptance](docs/verification/OWNER_PRODUCTION_GATE.md)

Git cleanup **không xóa hay migrate** `data/`, `workspace/`, `.env`, model weights, secrets, video và backups của Owner. AgentForge không cần file `.env` để khởi động; source không tự nạp `.env`, nhưng file này vẫn được Git ignore để tránh lộ secrets. CI fixture không chứng minh GPU, continuity, voice hay upload thật.

### Kiểm thử bộ nhớ Studio với ba bản nháp

Khi Ollama và ComfyUI đang chạy và Model Hub đã gán các năng lực local, dùng một lúc máy rảnh để chạy:

```powershell
.\.venv\Scripts\python.exe scripts/check_draft_resources.py --confirm-local-inference
```

Lệnh tạo ba bản nháp liên tiếp bằng model thật trong workspace kiểm thử riêng. So sánh các dòng cuối mỗi clip trong `samples.jsonl` và các mốc trước/sau từng bước trong `clip-*.json`. Số liệu gồm RAM khả dụng, commit của Windows, VRAM, working set và private bytes theo tiến trình nhận diện được. Chạy thử dashboard song song nếu cần kiểm tra tab trình duyệt. Chỉ coi kiểm thử live đạt khi cả ba MP4 qua xác minh và tab hoạt động như mong đợi.

Worker Studio xử lý một bản nháp mỗi lượt, mặc định giới hạn ba job đang chạy hoặc đang chờ. Có thể đặt `AGENTFORGE_DRAFT_QUEUE_LIMIT` từ 1 đến 8 khi khởi động backend. Khi thiếu tài nguyên, job dừng ở checkpoint và có thể tiếp tục bằng nút **Tiếp tục từ checkpoint**. Yêu cầu hủy đang chạy có hiệu lực tại checkpoint kế tiếp.

Studio, FLUX và Motion dùng chung quyền gửi GPU giữa các tiến trình AgentForge trong cùng workspace. Trước khi gửi, AgentForge kiểm tra queue ComfyUI và RAM, commit Windows, VRAM khả dụng. Các mức sàn tính bằng MiB cho ảnh là `4096 / 8192 / 3072`, cho Motion là `8192 / 12288 / 6144`. Có thể tăng từng mức bằng biến môi trường của backend `AGENTFORGE_{IMAGE|MOTION}_MIN_{RAM|COMMIT|VRAM}_MIB`. Đây là số đo lúc nhận job, không dự báo peak. Thiếu dữ liệu đo sẽ chặn GPU inference. ComfyUI mở trực tiếp không dùng khóa này, nên không bấm Run trong ComfyUI khi AgentForge đang dùng GPU.

Preset Wan 2.2 TI2V 5B FP16 đã bị chặn ở bước gửi Motion sau sự cố cạn commit. Các biên nhận đã có vẫn đọc được. ComfyUI và Ollama báo lỗi bộ nhớ hoặc lỗi server trong Studio sẽ giữ checkpoint để Owner xem xét trước khi chạy lại.

### LTX-Video 2B distilled FP8 I2V pilot

Gate A chỉ đọc schema từ ComfyUI đang chạy và xuất graph cố định để review.

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m agentforge.features.film_studio.motion_comfy ltx-workflow |
    Set-Content -Encoding ascii workspace\ltx-i2v-pilot.json
& $python -m agentforge.features.film_studio.motion_comfy inspect-workflow --workflow workspace\ltx-i2v-pilot.json
& $python -m agentforge.features.film_studio.motion_comfy ltx-readiness
```

Sau khi Owner duyệt Gate B, đặt [checkpoint chính thức](https://huggingface.co/Lightricks/LTX-Video/blob/main/ltxv-2b-0.9.8-distilled-fp8.safetensors) vào `ComfyUI/models/checkpoints` của Portable đã đăng ký. Pilot yêu cầu file đúng kích thước và SHA-256, dùng VAE trong checkpoint và [T5 FP8](https://huggingface.co/comfyanonymous/flux_text_encoders/blob/main/t5xxl_fp8_e4m3fn.safetensors) đã index trong ComfyUI. Chuẩn bị một ảnh PNG FLUX đã lưu có job ID và SHA-256, một shot đã lên kế hoạch và prompt local. Mức sàn là 12 GiB RAM khả dụng, 16 GiB commit Windows còn lại, 8 GiB VRAM trống và các queue đã đăng ký phải rỗng.

```powershell
& $python -m agentforge.features.film_studio.motion_comfy submit --film-slug $film --shot-id $shot --plan-sha $planSha --workflow workspace\ltx-i2v-pilot.json --workflow-sha $workflowSha --prompt-file $promptFile --seed 42 --image-job $imageJob --image-sha $imageSha --ltx-encoder $encoderFile --confirm-gpu-run --confirm-ltx-gate-b
```

Graph một pass dùng ảnh làm điều kiện đầu, 512×288, 33 frame, 24 fps, CFG 1 và các mốc đầu của [cấu hình distilled](https://github.com/Lightricks/LTX-Video/blob/main/configs/ltxv-2b-0.9.8-distilled-fp8.yaml). Không upscale. Theo dõi RAM khả dụng, Windows commit và VRAM từ trước khi gửi cho tới nạp model, sampling và VAE decode. Dừng lần thử nếu thiếu tài nguyên và giữ log, không gửi lại job. Dùng `status` rồi `collect` với tên file `af_motion_<job_id>_00001_.mp4` thực tế từ ComfyUI. Collect kiểm tra đủ 33 frame và giải mã qua FFmpeg. Owner vẫn cần đối chiếu các frame về chuyển động thực và ngoại hình nhân vật.

Sau khi Owner duyệt một lần thử mới cho shot đã lỗi, thêm `--confirm-new-attempt` vào lệnh `submit`. Ledger giữ lịch sử theo từng job ID. Job đang chạy hoặc chưa xác định được kết quả phải được đối soát trước. Lệnh `migrate-ledger` có thể cập nhật ledger hiện có và xuất đường dẫn backup cùng số bản ghi trước/sau mà không gửi job.

Để tạo phim chuyển động từ Dashboard, đăng ký checkpoint LTX 2B FP8 và đường dẫn tuyệt đối của encoder đã xác minh trong Model Hub, rồi gán hồ sơ đó cho **Tạo chuyển động**. Cấu hình launcher và endpoint ComfyUI; đặt `ffmpeg`, `ffprobe` trên PATH của backend. Trong Studio video, chọn **Phim chuyển động LTX**, chọn thời lượng 4, 6, 15 hoặc 30 giây, rồi bấm **Tạo storyboard**. Xem từng cảnh, chỉnh prompt nếu cần và duyệt đúng phiên bản trước khi tạo ảnh FLUX và clip LTX.

Preset 15 giây dùng 8–9 shot riêng. Với 30 giây, AI chọn 15–16 shot và phân bổ tối đa 49 frame mỗi shot, tổng đúng 720 frame. Studio cắt mỗi clip LTX 49 frame theo timeline rồi ghép MP4 16:9. Giới hạn tối đa 16 shot cho một phiên bản, 240 giây theo dõi mỗi job LTX và 256 MiB clip đầu vào khi ghép. Nếu mất kết nối, dùng **Tiếp tục từ checkpoint** để đối soát job cũ qua lịch sử ComfyUI. Một phiên bản sửa giữ clip và ảnh đã xác minh nếu đầu vào tương ứng giữ nguyên. Khi xuất video, có thể tải biên nhận và phụ đề SRT đã nhập. Visual QA và Owner QA là các bước riêng.

Nếu job dừng ở `COMMIT_LOW` ngay sau ảnh đầu, so sánh mốc sau cảnh 1 với mốc trước cảnh 2 trong biên nhận. Khi ComfyUI vẫn giữ nhiều private memory dù hàng đợi rỗng, có thể thử thêm `--cache-none` vào lệnh khởi chạy một phiên ComfyUI kiểm thử. Cờ này chạy lại từng node, có thể làm mỗi cảnh lâu hơn và có thể giảm bộ nhớ giữ lại giữa các cảnh. Giữ nguyên ngưỡng tài nguyên và đo lại cả ba clip trước khi áp dụng cho phiên Owner.
