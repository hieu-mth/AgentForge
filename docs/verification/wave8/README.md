# Đợt 8 — Film Studio 12 GiB: One-shot Wan 2.2 5B

**Phân biệt trạng thái:** code/Windows CI kiểm tra hợp đồng; chưa chạy GPU thật, chưa có MP4 thật của máy Owner, chưa đo peak VRAM và chưa duyệt nội dung. Không gán F2 hoặc WAVE8_OWNER_PASS khi chưa có bằng chứng.

## Chuẩn bị tự nguyện

1. Cài ComfyUI chính hãng tại 127.0.0.1:8188, không public cổng. Chủ động tải Wan 2.2 TI2V 5B fp16 và paired encoder/VAE theo [ComfyUI docs](https://docs.comfy.org/tutorials/video/wan/wan2_2) và [graph official](https://comfy.org/hub/workflows/wan-2-2-5b-video-generation-f83ee3caa04e/). Không có bước tự download trong AgentForge.
2. Model: wan2.2_ti2v_5B_fp16.safetensors ở models/diffusion_models, umt5_xxl_fp8_e4m3fn_scaled.safetensors ở models/text_encoders, wan2.2_vae.safetensors ở models/vae. Workflow mẫu core-node AgentForge: examples/film_studio/wan22_5b_4s_api.json. Graph có 11 node, 640×352, 49 frames, 12 fps, 1 batch (~4.083 giây). **Không có bằng chứng workflow mẫu tương thích mọi bản ComfyUI**; chỉ điều chỉnh local sau khi Owner xem và inspect SHA.
3. Cài FFmpeg/ffprobe có nguồn tin cậy trên PATH. Để lưu peak VRAM thực: chủ động theo dõi nvidia-smi mỗi giây trong quá trình render; nếu không theo dõi thì để trống, không tự giả định.
4. Dashboard Model Hub: tùy chọn thêm profile ComfyUI model ID wan2.2_ti2v_5B_fp16 và gán film.motion. Route vẫn CONFIG_ONLY; **không điều khiển inference**, workflow đã review quyết định weights. Không auto cloud fallback.

## Tạo plan 4s, inspect

Chạy từ PowerShell tại repo đã cập nhật và không có thay đổi local chưa xử lý:

~~~powershell
cd D:\AgentForge
git status --short
git pull --ff-only origin main

.\.venv\Scripts\python.exe -m agentforge.features.film_studio.long_form plan --spec .\examples\film_studio\wan22_5b_pilot_spec.json --output-root .\workspace\films --slug wan5b-pilot
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.long_form inspect --output-root .\workspace\films --slug wan5b-pilot

.\.venv\Scripts\python.exe -m agentforge.features.film_studio.motion_comfy health
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.motion_comfy inspect-workflow --workflow .\examples\film_studio\wan22_5b_4s_api.json
~~~

Lấy plan_sha256 và workflow sha256 đúng từ output. Tạo file D:\FilmWorkflows\shot.txt có prompt nguyên bản 30–1100 ký tự, mô tả chủ thể/action/camera. **Không đưa prompt lên lệnh PowerShell để tránh shell history.**

## One-shot GPU queue và ComfyUI status

~~~powershell
.\.venv\Scripts\python.exe -m agentforge.features.film_studio.motion_comfy submit --film-slug wan5b-pilot --shot-id sh-00001 --plan-sha YOUR_PLAN_SHA --workflow .\examples\film_studio\wan22_5b_4s_api.json --workflow-sha YOUR_WORKFLOW_SHA --prompt-file D:\FilmWorkflows\shot.txt --seed 7 --confirm-gpu-run

.\.venv\Scripts\python.exe -m agentforge.features.film_studio.motion_comfy status --job-id RETURNED_JOB_ID
~~~

AgentForge không retry lỗi không chắc chắn. Nếu status SUBMITTING_UNCERTAIN, **không submit lại**, kiểm tra trực tiếp queue/history của ComfyUI. Chỉ khi status COMFY_COMPLETE_NOT_IMPORTED_OR_VERIFIED mới được import.

## Import MP4 từ Comfy output chính xác

Quan sát file MP4 thật từ ComfyUI trong output dir. Filename bắt buộc dạng af_motion_JOBID_00001.mp4, counter có thể khác nhưng đúng 5 chữ số, không chấp nhận path lồng hoặc link ngoài. Cần ffprobe, ffmpeg.

~~~powershell
where.exe ffprobe
where.exe ffmpeg

.\.venv\Scripts\python.exe -m agentforge.features.film_studio.motion_comfy collect --job-id RETURNED_JOB_ID --output-dir D:\ComfyUI\output --filename af_motion_RETURNED_JOB_ID_00001.mp4 --confirm-import

.\.venv\Scripts\python.exe -m agentforge.features.film_studio.motion_comfy receipt --job-id RETURNED_JOB_ID
~~~

Chỉ nếu bạn đã quan sát mức VRAM cao nhất bằng công cụ riêng, thêm flag --owner-peak-vram-gib 9.5 với **số thực được ghi nhận**. Receipt ghi rõ peak_vram_automatically_measured=false, không đánh đồng total/free snapshot với peak. Wall time từ submit tới lúc Owner import **không phải thời gian inference thuần**.

Output được copy vào workspace/films/wan5b-pilot/motion_clips/JOBID/clip.mp4, receipt.json; không ghi đè. Verify: size bound, exact filename/job, duration 3.8–4.5s, 49 decoded frames, width/height/fps, full FFmpeg decode và SHA-256. Tài liệu/receipt không có token hay đường dẫn ComfyUI tuyệt đối. Không cần upload.

## Dashboard

Ở phiên PowerShell chạy server, chỉ khi Owner tự muốn import qua UI:

~~~powershell
$env:AGENTFORGE_COMFY_OUTPUT_DIR = 'D:\ComfyUI\output'
.\.venv\Scripts\python.exe -m agentforge --port 8780 --allow-external-tools
~~~

Trong AI Models & Routing → Film Studio 4s pilot: xem GPU total/free snapshot, jobs và trạng thái. Nút History kiểm tra provider history, nhập đúng tên file MP4 rồi Import; confirmation hiển thị plan/workflow SHA trước khi chạy. Session, CSRF, Owner external-mode, exact SHA và ops active đều được kiểm tra. Không có quyền gọi GPU hoặc tạo phim mới tự động qua Dashboard.

## Chốt nghiệm thu F2

- ComfyUI GPU/weights thật + workflow 5B chạy đúng trên máy 12 GiB.
- Một file MP4 local hợp lệ, 49 frames ~4.083s, ffprobe/FFmpeg decode thật, SHA receipt khớp khi đọc lại.
- Owner tự xem video, xác nhận có chuyển động đáng kể và không gặp lỗi OOM.
- Ghi GPU/driver/model phiên bản, thời gian thực **ComfyUI sampling** và nếu được, peak VRAM đo trong lúc chạy. Không bịa latency/VRAM từ fixture CI.
- Chỉ khi các điều kiện trên có bằng chứng mới chốt WAVE8_OWNER_12GB_MP4_PASS. Nếu chưa, trạng thái GPU_UNVERIFIED. Continuity/multi-shot/voice/assembly thuộc Đợt 9.
