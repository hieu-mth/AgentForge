# Đợt 5 — Nghiệm thu Runtime thực tế (Owner / Windows)

**Trạng thái của bộ công cụ khi merge code:** RUNTIME_CERTIFICATION_TOOLING_READY / OWNER_MACHINE_PENDING / NOT_PRODUCTION_GO.

Đợt 5 này là phần hardening sau audit 19 findings, **không** phải
milestone lịch sử Wave 5 Base V1 chỉ chạy fixture. CI PASS không chứng minh
GPU/Ollama/ComfyUI/Docker hoạt động trên Windows cá nhân và càng không phải
chứng nhận app/website/phim thương mại.

## 1. Cập nhật và chạy preflight mặc định — KHÔNG gọi AI/GPU

PowerShell trên máy Windows thực sự cài AgentForge:

    cd D:\AgentForge
    git status
    git pull --ff-only origin main
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport

- Mặc định chỉ kiểm tra Python, Node/npm; Model Hub local route;
  Ollama GET /api/tags; ComfyUI /system_stats và /models/checkpoints;
  FFmpeg -version; Docker image inspect đối với image đã pin SHA;
  Dashboard GET / mà không có Owner session.
- Không gửi prompt, gọi model inference, tải model, tạo GPU job, Docker
  container, build source, sửa SQLite/artifacts, OAuth hay xuất bản.
- Cờ SaveReport chủ động tạo JSON nội bộ trong
  workspace/runtime-certification/. Bỏ cờ nếu chỉ muốn xem kết quả và không
  ghi file. JSON loại bỏ output của model, token, password, cookie, full path;
  vẫn phải giữ riêng tư trên máy.
- report_sha256 là digest xác minh nội dung, **không phải chữ ký số**.
- READY_FOR_INFERENCE / READY_FOR_OWNER_GPU_PILOT /
  READY_FOR_OFFLINE_SANDBOX_TEST chỉ là preflight, không phải PASS_RUNTIME.
- UNAVAILABLE hay MODEL_NOT_INSTALLED không có nghĩa source sai: phải kiểm
  môi trường cụ thể, không tự khởi động daemon hoặc tải weights.

Nếu .venv thiếu, xem [hướng dẫn setup](../../DEVELOPMENT.md).

## 2. FFmpeg thực — MP4 + audio/video decode trong thư mục tạm

Chỉ khi Owner đồng ý chạy local executable:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunFFmpeg -ConfirmLocalExec -SaveReport

Tạo video màu và âm sine 1 giây bằng FFmpeg, kiểm cấu trúc MP4 có audio
và video, giải mã cả hai stream. File thử được tạo trong TemporaryDirectory
và xóa khi xong. Không dùng/xóa dữ liệu workspace/media của Owner.
PASS_RUNTIME chỉ chứng nhận fixture encode/decode, không chứng nhận video
AI, hiệu ứng camera hoặc slideshow nghiệp vụ. CI chạy fixture này riêng,
nhưng GitHub runner không thay thế máy Owner.

## 3. Ollama thực — một lượt inference local, không cloud

Chạy khi đã có local model trong Model Hub, ví dụ local_primary:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunOllama -ConfirmInference -ModelRef local_primary -SaveReport

- Chỉ gọi HTTP loopback Ollama POST /api/chat **một lượt**; prompt cố định
  không chứa dữ liệu cá nhân, output tối đa 32 tokens, timeout 120 giây,
  JSON phản hồi tối đa 64 KiB, không retry hoặc pull model.
- Không chuyển sang Anthropic/cloud dù process có cấu hình cloud.
- Báo cáo giữ SHA-256 output và thời gian thực, không lưu text output.
- PASS_RUNTIME chỉ là sống được local inference, không có nghĩa Web AI
  Designer hay React AI Developer làm ra sản phẩm hợp lệ.
- Cần Owner chạy một website/webapp thật, duyệt đúng proposal SHA, mở
  preview/browser QA và yêu cầu sửa có hiệu lực, rồi nghiệm thu thủ công.

## 4. Docker pinned image — smoke offline KHÔNG chạy source AI

Owner tự build browser QA image từ trusted contexts theo
[sandbox/webapp/README.md](../../../sandbox/webapp/README.md).
Không sử dụng root context có .env, data hoặc workspace.
Ví dụ (lần build có thể dùng mạng; chỉ Owner thực hiện):

    docker buildx build --load --build-context reference=./templates/novamart -f ./sandbox/webapp/Dockerfile.browser -t agentforge-webapp-browser:local ./sandbox/webapp
    docker image inspect agentforge-webapp-browser:local --format '{{.Id}}'
    $env:AGENTFORGE_BROWSER_QA_IMAGE = 'sha256:<ID thật từ inspect>'
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunDocker -ConfirmDockerRun -SaveReport

Smoke chỉ chạy Node --version trong một container Linux đã cache với
--pull never, --network none, root filesystem read-only, cap-drop ALL,
non-root UID và giới hạn CPU/RAM/PIDs. Không có mount source hay secrets.
PASS_RUNTIME chỉ chứng minh image startup; không chứng nhận browser QA.

Để nghiệm thu generated React app: mở đúng signed proposal trong Dashboard,
chọn QA Chromium offline, duyệt Goal, SHA và quyền process.run. Xem
report SHA và ảnh desktop/mobile thật. PASS_SMOKE_ONLY vẫn không có nghĩa
search, checkout, account, hiệu năng hoặc app security đã PASS.

## 5. ComfyUI/GPU/Wan 5B — phải do Owner chạy một-shot riêng

Preflight chỉ kiểm tra API readonly /system_stats và checkpoint discovery,
không gửi /prompt. VRAM total/free chỉ là snapshot, không phải peak.

Theo [Film Studio 12GB](../../architecture/FILM_MOTION_12GB_PILOT.md) và
[Wave 8 import QA](../wave8/README.md), Owner thực hiện:

1. Kiểm ComfyUI chỉ nghe 127.0.0.1:8188, workflow API-format được review
   và SHA, chỉ dùng core nodes/weights được allowlist.
2. Xác minh đúng checkpoint Wan2.2 TI2V 5B cùng encoder/VAE; không tự
   tải model hoặc bật GPU chỉ vì báo READY.
3. Chuẩn bị plan shot 4 giây (640x352, 49f/12fps, batch 1). Owner
   mới chọn submit --confirm-gpu-run cho **một** shot. Không retry trạng thái
   SUBMITTING còn mơ hồ.
4. Sau khi history xác nhận, import MP4 từ thư mục nguồn Owner chỉ định,
   kiểm ffprobe, FFmpeg decode, SHA receipt, frame count và thời lượng.
5. Owner phát video để xem chất lượng, continuity, nghe voice nếu có và
   ghi thời gian/mức VRAM đo được. Không dùng inference 4 giây để tuyên bố
   phim 60-90 giây hay dài 15-30 phút sẵn sàng.

Báo cáo script không tự đặt real_gpu_video_verified=true.

## 6. Dashboard và backup/restore thật

- Owner mở http://127.0.0.1:8780, đăng nhập bằng mã in riêng trên console,
  xác minh session/CSRF, mở proposal preview và thực hiện một workflow
  có review rõ quyền. Không chia sẻ mã đăng nhập.
- Với backup Owner thực hiện create --include-workspace --confirm-backup,
  verify checksum và stage-restore vào **thư mục mới** theo
  [Wave 2 Backup Coverage](../../milestones/WAVE2_BACKUP_COVERAGE.md).
  Đối chiếu tham chiếu DB/artifacts và business data trong staged copy,
  không ghi đè active SQLite. Backup/staging không mã hóa, không upload.
- Kiểm recovery sau restart/crash trên bản sao an toàn do Owner chọn;
  không fault-inject vào data sản xuất.
- Các điều kiện này không tự biến thành PASS nhờ script preflight.

## 7. Định nghĩa verdict

| Bằng chứng | Kết luận được phép |
| --- | --- |
| GitHub CI full suite và Windows Edge | CODE_CONTRACT_PASS, không phải PC Owner |
| Local model/GPU/Docker preflight | READY_FOR_OWNER_TEST hoặc UNAVAILABLE |
| FFmpeg MP4 fixture trên PC | PASS_RUNTIME chỉ cho fixture media |
| Local Ollama inference một lượt | PASS_RUNTIME chỉ cho text inference |
| Docker pinned image chạy offline | PASS_RUNTIME chỉ cho container startup |
| React app QA trong Docker | PASS_SMOKE_ONLY, chưa chứng nhận chức năng |
| Film clip import + decode + Owner xem | OWNER_REVIEW_REQUIRED đến khi duyệt |
| Backup thật và staged reference cross-check | Owner nghiệm thu riêng |
| Production GO | **KHÔNG tự suy ra từ các probe** |

Probe opt-in thất bại được ghi OPTIONAL_PROBE_FAILED và trả exit code khác 0.
Không lấy lỗi mạng/thiếu model làm lý do retry tự động. Nếu chạy lại, Owner
phải cấp phép lần nữa.

## 8. Những thứ còn chưa được xác nhận bằng CI

Runtime AI/GPU trên PC, film Wan 5B, browser QA cho source AI thật,
cross-DB restore integrity, cloud billing, account/OAuth, publish thực,
lead/notification/order của MVP bán nệm và public production security.
Không được gọi Đợt 5 là toàn bộ runtime PASS trước khi thu đủ bằng chứng.
