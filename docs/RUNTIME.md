# Runtime và vận hành local

Đây là checklist chạy thực tế, không phải chứng nhận Production GO. Không suy ra GPU, motion, voice, upload hay chất lượng video từ CI fixture.

## 1. Preflight mặc định (read-only, không gọi model)

```powershell
cd D:\AgentForge
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
```

Kiểm Python/Node, ComfyUI, FFmpeg và HTTP Dashboard. Nếu không chỉ định ModelRef, Ollama probe trả `NO_MODEL_SELECTED` (không tạo model giả). Các công cụ render local được Owner cài và bật riêng. Receipt được lưu trong `workspace/runtime-certification/` khi bật SaveReport; không upload receipt hoặc secret.

## 2. FFmpeg fixture thực (Owner chủ động)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunFFmpeg -ConfirmLocalExec -SaveReport
```

Chỉ chứng nhận encode/decode clip tạm 1 giây, không phải motion do AI tạo.

## 3. Một lượt Ollama local (Owner chủ động)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunOllama -ConfirmInference -ModelRef my_local_model -SaveReport
```

Trước tiên, đăng ký profile Ollama có ID `my_local_model` (hoặc ID khác) qua Dashboard, rồi thay `-ModelRef` đúng với ID đã đăng ký. Không còn `local_primary` mặc định. Script dùng một prompt cố định, không truyền dữ liệu riêng tư, không pull model và không fallback cloud. PASS_RUNTIME chỉ cho kiểm tra text inference.

## 4. Kiểm tra AI cloud và sản xuất media

Đăng ký hồ sơ ChatGPT Plan (xem [hướng dẫn OAuth](CHATGPT.md)), OpenAI-compatible hoặc Anthropic-compatible tại Model AI. Endpoint là API base URL (ví dụ `https://provider.example/v1`), model ID và API key do Owner cung cấp. **Kiểm tra** chỉ gọi metadata model; **Chạy thử** gửi một yêu cầu JSON cố định tối đa 64 token đầu ra, có thể phát sinh phí. Một số gateway không hỗ trợ metadata, khi đó dùng Chạy thử để xác nhận inference. Không cần Ollama hoặc ComfyUI.

Tại AI điều phối, gán model cho Lập kế hoạch và Sáng tạo kịch bản, có thể gán thêm Chọn nhân vật. Trong AI điều phối, bật lập kế hoạch, sử dụng model đã phân công, gọi AI cloud và đặt giới hạn lượt gọi phù hợp. Không cần quyền gọi AI local hay FFmpeg khi chỉ tạo storyboard cloud. Backend cần `--allow-external-tools`. Dừng khẩn cấp chặn lượt gọi cloud mới; request đang xử lý có thể hoàn tất. Giới hạn lượt gọi không thay cho ngân sách tiền.

### ComfyUI, shot thật và Film Studio

Xem cấu hình motion bên dưới và [kiến trúc Studio](ARCHITECTURE.md).

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

Dữ liệu, model, credential và workspace của Owner luôn nằm ngoài cleanup Git.

## GPU và quản lý tài nguyên

Worker Studio xử lý một bản nháp mỗi lượt, mặc định giới hạn ba job đang chạy hoặc đang chờ. Có thể đặt `AGENTFORGE_DRAFT_QUEUE_LIMIT` từ 1 đến 8 khi khởi động backend. Khi thiếu tài nguyên, job dừng ở checkpoint và có thể tiếp tục bằng nút **Tiếp tục từ checkpoint**. Yêu cầu hủy đang chạy có hiệu lực tại checkpoint kế tiếp.

Studio, FLUX và Motion dùng chung quyền gửi GPU giữa các tiến trình AgentForge trong cùng workspace. Trước khi gửi, AgentForge kiểm tra queue ComfyUI và RAM, commit Windows, VRAM khả dụng. Các mức sàn tính bằng MiB cho ảnh là `4096 / 8192 / 3072`, cho Motion là `8192 / 12288 / 6144`. Có thể tăng từng mức bằng biến môi trường của backend `AGENTFORGE_{IMAGE|MOTION}_MIN_{RAM|COMMIT|VRAM}_MIB`. Đây là số đo lúc nhận job, không dự báo peak. Thiếu dữ liệu đo sẽ chặn GPU inference. ComfyUI mở trực tiếp không dùng khóa này, nên không bấm Run trong ComfyUI khi AgentForge đang dùng GPU.

Preset Wan 2.2 TI2V 5B FP16 đã bị chặn ở bước gửi Motion sau sự cố cạn commit. Các biên nhận đã có vẫn đọc được. ComfyUI và Ollama báo lỗi bộ nhớ hoặc lỗi server trong Studio sẽ giữ checkpoint để Owner xem xét trước khi chạy lại.

## Motion ComfyUI

Studio sử dụng model motion do Owner đăng ký và phân công trong Model Hub. Preset LTX 2B distilled FP8 I2V hiện hành sử dụng ảnh nguồn, 512×288, tối đa 49 frame ở 24 FPS. Wan 2.2 TI2V 5B FP16 bị chặn dispatch do rủi ro cạn Windows commit; biên nhận cũ vẫn có thể đọc.

### Vận hành

1. Cấu hình ComfyUI loopback và launcher trong Dashboard; đăng ký model, encoder và workflow tương thích.
2. Kiểm tra readiness, FFmpeg/ffprobe, RAM, Windows commit, VRAM và queue.
3. Tạo storyboard, kiểm timeline và duyệt đúng digest trước khi tạo media.
4. Theo dõi job; nếu kết quả submit chưa rõ, đối soát history trước khi tiếp tục. Không gửi lại mù.
5. Kiểm clip bằng SHA, frame count, kích thước, FPS và FFmpeg decode; xem trực tiếp để đánh giá motion và continuity.

Không tự tải weights, cài custom nodes hoặc fallback cloud. Không giảm resource guard để vượt lỗi bộ nhớ. Metadata readiness và technical QA không chứng minh chất lượng hình ảnh.

## LTX — kiểm tra workflow và chạy shot độc lập

Kiểm tra metadata chỉ đọc schema từ ComfyUI đang chạy và xuất graph cố định để review.

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m agentforge.features.film_studio.motion_comfy ltx-workflow |
    Set-Content -Encoding ascii workspace\ltx-i2v.json
& $python -m agentforge.features.film_studio.motion_comfy inspect-workflow --workflow workspace\ltx-i2v.json
& $python -m agentforge.features.film_studio.motion_comfy ltx-readiness
```

Owner chủ động đặt [checkpoint chính thức](https://huggingface.co/Lightricks/LTX-Video/blob/main/ltxv-2b-0.9.8-distilled-fp8.safetensors) vào `ComfyUI/models/checkpoints` của Portable đã đăng ký. Adapter yêu cầu file đúng kích thước và SHA-256, dùng VAE trong checkpoint và [T5 FP8](https://huggingface.co/comfyanonymous/flux_text_encoders/blob/main/t5xxl_fp8_e4m3fn.safetensors) đã index trong ComfyUI. Chuẩn bị một ảnh PNG FLUX đã lưu có job ID và SHA-256, một shot đã lên kế hoạch và prompt local. Mức sàn là 12 GiB RAM khả dụng, 16 GiB commit Windows còn lại, 8 GiB VRAM trống và các queue đã đăng ký phải rỗng.

```powershell
& $python -m agentforge.features.film_studio.motion_comfy submit --film-slug $film --shot-id $shot --plan-sha $planSha --workflow workspace\ltx-i2v.json --workflow-sha $workflowSha --prompt-file $promptFile --seed 42 --image-job $imageJob --image-sha $imageSha --ltx-encoder $encoderFile --confirm-gpu-run --confirm-ltx-gate-b
```

Graph một pass dùng ảnh làm điều kiện đầu, 512×288, 33 frame, 24 fps, CFG 1 và các mốc đầu của [cấu hình distilled](https://github.com/Lightricks/LTX-Video/blob/main/configs/ltxv-2b-0.9.8-distilled-fp8.yaml). Không upscale. Theo dõi RAM khả dụng, Windows commit và VRAM từ trước khi gửi cho tới nạp model, sampling và VAE decode. Dừng lần thử nếu thiếu tài nguyên và giữ log, không gửi lại job. Dùng `status` rồi `collect` với tên file `af_motion_<job_id>_00001_.mp4` thực tế từ ComfyUI. Collect kiểm tra đủ 33 frame và giải mã qua FFmpeg. Owner vẫn cần đối chiếu các frame về chuyển động thực và ngoại hình nhân vật.

Sau khi Owner duyệt một lần thử mới cho shot đã lỗi, thêm `--confirm-new-attempt` vào lệnh `submit`. Ledger giữ lịch sử theo từng job ID. Job đang chạy hoặc chưa xác định được kết quả phải được đối soát trước. Ledger chỉ hỗ trợ schema hiện hành (user_version=2); schema cũ bị từ chối, không tự migrate. Dừng worker, đối soát toàn bộ tác vụ cũ và archive DB cùng sidecar trước khi khởi tạo ledger mới. Không xóa ledger còn job chưa rõ kết quả.


## Tạo video trên Dashboard

Để tạo phim chuyển động local từ Dashboard, đăng ký checkpoint LTX 2B FP8 và đường dẫn tuyệt đối của encoder đã xác minh trong Model Hub, rồi gán hồ sơ đó cho **Tạo chuyển động**. Cấu hình launcher và endpoint ComfyUI. Đặt `ffmpeg` và `ffprobe` trong `data/company/runtime_tools/ffmpeg` hoặc trên PATH của backend. Trong Studio video, nhập nội dung, chọn phương pháp sản xuất và bấm **Tạo storyboard**. Với video cloud, xem [Cloud video](CLOUD_VIDEO.md). Model văn bản đã phân công lập kế hoạch thời lượng (Ollama local hoặc API cloud tương thích). Với cloud, không yêu cầu Ollama, ComfyUI hay GPU để tạo storyboard. Bạn cũng có thể nhập số giây trong phần tùy chỉnh. Backend hỗ trợ 4–60 giây cho phim chuyển động và 6–60 giây cho ảnh tĩnh, với tối đa 32 cảnh chuyển động và 49 frame mỗi clip LTX local; LTX Cloud có giới hạn riêng theo adapter. Xem thời lượng đề xuất và timeline đã kiểm tra, chỉnh storyboard nếu cần rồi duyệt đúng phiên bản trước khi tạo ảnh FLUX hoặc clip LTX.

Video 30 giây ở 24 FPS cần đúng 720 frame; 60 giây cần 1.440 frame. Số segment phụ thuộc timeline và giới hạn runtime. Studio cắt mỗi clip LTX theo timeline rồi ghép MP4 16:9. Giới hạn theo dõi job phụ thuộc adapter; LTX local có giới hạn 240 giây và 256 MiB clip đầu vào khi ghép. Nếu mất kết nối, dùng **Tiếp tục từ checkpoint** để đối soát job cũ qua lịch sử ComfyUI. Một phiên bản sửa giữ clip và ảnh đã xác minh nếu đầu vào tương ứng giữ nguyên. Khi xuất video, có thể tải biên nhận và phụ đề SRT đã nhập. Visual QA và Owner QA là các bước riêng.


Nếu job dừng ở `COMMIT_LOW` ngay sau ảnh đầu, so sánh mốc sau cảnh 1 với mốc trước cảnh 2 trong biên nhận. Khi ComfyUI vẫn giữ nhiều private memory dù hàng đợi rỗng, có thể thử thêm `--cache-none` vào lệnh khởi chạy một phiên ComfyUI kiểm thử. Cờ này chạy lại từng node, có thể làm mỗi cảnh lâu hơn và có thể giảm bộ nhớ giữ lại giữa các cảnh. Giữ nguyên ngưỡng tài nguyên và đo lại cả ba clip trước khi áp dụng cho phiên Owner.

## Đo tài nguyên thực tế

Tạo ba draft kiểm thử riêng bằng Dashboard; duyệt từng storyboard trước khi dispatch. Chạy lần lượt, không chạy cùng production khác. Dùng production ID thực tế để lấy mẫu:

```powershell
.\.venv\Scripts\python.exe -m scripts.studio_resource_baseline <production-id> --sample-seconds 600
```

Chỉ kết luận đạt khi cả ba MP4 qua kiểm tra và Dashboard vẫn sử dụng được. Mẫu theo chu kỳ không chứng minh peak tuyệt đối. Không giảm ngưỡng RAM/commit/VRAM để ép chạy.


## Khởi tạo lại Model Hub

Schema hiện hành không đọc chính sách Model Hub cũ (có mapping hoặc quyền cũ). Không tự động xóa hay migrate DB. Sau khi dừng backend và xác nhận không có job đang chạy hoặc chưa đối soát, Owner có thể chuyển DB Model Hub cũ và các sidecar SQLite (nếu có) ra thư mục lưu trữ ngoài `data`, rồi khởi động lại. Ví dụ trên PowerShell, từ thư mục repository:

```powershell
$backup = Join-Path $HOME ("agentforge-hub-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backup | Out-Null
Get-ChildItem -LiteralPath .\data\company -File |
    Where-Object { $_.Name -in @('model_hub.sqlite3','model_hub.sqlite3-wal','model_hub.sqlite3-shm','model_hub.sqlite3-journal') } |
    Move-Item -Destination $backup
```

Đăng ký lại model, phân công và cấp quyền trong Dashboard. Việc này đặt lại revision, cấu hình và lịch sử snapshot Model Hub. Bản nháp đã duyệt bằng cấu hình cũ có thể không tiếp tục được: tạo production mới, không sửa digest thủ công. Không xóa các ledger motion/cloud, workspace, weights, DB nhân vật hoặc credential OAuth. ChatGPT account token nằm riêng; đăng ký lại profile dùng account reference đã kết nối nếu phiên còn hợp lệ. Không chạy lệnh khi backend hoặc công cụ khác còn sử dụng DB.

### Checkpoint image workflows

Model Hub accepts a ComfyUI API-format image workflow using a supported graph
dialect. Existing `flux` profiles retain the original nine-node FLUX GGUF
validation. The `comfy_image` option also accepts the seven-node checkpoint
graph: CheckpointLoaderSimple, two CLIPTextEncode nodes, EmptyLatentImage,
KSampler, VAEDecode and SaveImage, with the approved conditioning and VAE links.
The registered model ID must match the loader's installed safetensors filename.
Node IDs may vary; batch is one, dimensions are multiples of 16, and the
configured maximum is 1536 pixels per side, 20 steps and 600 seconds.
Metadata checks do not generate images. Only an explicit probe or an approved
Studio production dispatches inference. Both dialects use the existing
visual-job ledger, output filename binding and verified PNG import.
Unsupported topology, custom nodes and mismatched model IDs are rejected.
This is not arbitrary ComfyUI graph support or runtime certification of every
checkpoint. Local motion retains its existing reviewed LTX path.

### Configured local I2V profiles

The `comfy_video` option and absolute `motion_encoder` path register a
bounded checkpoint-based I2V graph using the existing supported LTX-style
node topology. Use the legacy inspected graph as a template; change its
wrapper format to `agentforge.film.comfy.i2v.v2` and add
`weights_sha256: {checkpoint: <64 hex>, encoder: <64 hex>}`. The registered
model must equal the checkpoint filename; the encoder path must match the
graph's encoder basename. Both files are verified before GPU dispatch.
The checkpoint is under the registered Portable installation's
`ComfyUI/models/checkpoints` directory. The graph may vary its checkpoint,
encoder, resolution (256–640, multiples of 32), frames (9–97, 8n+1), and FPS
(8–30) within the original pixel-frame budget and five-second limit.
Sampling and topology remain fixed. No arbitrary graph/custom node is
accepted; unsupported topology requires a separate reviewed dialect.
This does not establish that every checkpoint runs or fits on the Owner GPU.
The blocked Wan FP16 path remains blocked. Existing legacy profiles and
receipts retain their original interpretation; the local motion ledger
upgrades version 2 to 3 transactionally on write, preserving unresolved
jobs and all existing source evidence.
