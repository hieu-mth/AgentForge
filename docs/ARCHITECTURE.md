# Kiến trúc AgentForge

## Nguyên tắc sản xuất phim

AgentForge quản lý nội dung, tài sản, quyết định của Owner, trạng thái sản xuất và hậu kỳ; model là công cụ thay thế được theo năng lực đã kiểm chứng. Local-first áp dụng cho quyền sở hữu dữ liệu và điều phối, không bắt buộc toàn bộ inference chạy local. Chất lượng, độ nhất quán và chi phí trên video sử dụng được quyết định phương pháp sản xuất.

Tách ba trách nhiệm:
- Creative: kịch bản, nhân vật, hành động, góc quay và thời lượng theo nội dung. Không để số frame hoặc giới hạn một model quyết định ý đồ đạo diễn.
- Execution: lập kế hoạch kỹ thuật từ ý đồ đã kiểm tra và khả năng adapter thật; khóa đầu vào, route, tài nguyên, approval và receipt. Nếu không khả thi thì báo rõ, không tự đổi model hoặc thay đổi nội dung.
- Quality/post-production: kiểm tra kỹ thuật, chất lượng trực quan và duyệt Owner; FFmpeg xử lý hậu kỳ. CI kỹ thuật không xác nhận chất lượng điện ảnh.

Pipeline chạy được hiện tại vẫn là tạo ảnh local rồi tạo chuyển động từ ảnh (hoặc ghép ảnh tĩnh). Không công bố Reference-to-Video, Text-to-Video, cloud inference hoặc visual QA tự động là tính năng hiện có. Chỉ thêm adapter, route và UI cho phương pháp đã qua benchmark. Không dùng một model cụ thể làm hợp đồng chung của Studio.

## Hợp đồng tài sản nhân vật

Hồ sơ nhân vật hiện lưu metadata trong SQLite. ID hồ sơ và version mô tả dùng cho snapshot casting; trường `model_ref` và `reference_version` hiện không phải định danh ảnh nhận diện hay bằng chứng giữ ngoại hình.

Khi triển khai thư viện tài sản, hợp đồng phải phân biệt:
- Character ID: định danh ổn định của nhân vật, độc lập với model/provider.
- Asset revision: phiên bản bất biến của bộ nhận diện đã duyệt, gắn với character ID. Bộ nhận diện gồm ảnh gốc hoặc ảnh tạo hình được Owner duyệt, có vai trò rõ (ảnh chính diện, toàn thân, góc nhìn khác khi cần). Không yêu cầu model 3D hoặc LoRA nếu ảnh tham chiếu đáp ứng chất lượng.
- Mỗi file tham chiếu có định danh nội bộ, SHA-256 của bytes, loại media và vai trò. Bytes nằm trong storage local ngoài Git; không ghi credential hay URL tạm vào creative plan.
- Provider binding (nếu cần): ánh xạ từ asset revision sang định danh tài sản của provider, riêng theo provider. Không coi ID provider là Character ID.
- Creative plan chọn nhân vật và yêu cầu diễn xuất, bối cảnh; execution plan chọn đúng asset revision và chuyển các tham chiếu được phép theo khả năng adapter. Không tự sinh ngoại hình mới để thay thế asset đã duyệt.
- Approval phải ràng buộc asset revision và file digest cùng nội dung, cấu hình thực thi; thay asset thì duyệt lại phần phụ thuộc. Thiếu hoặc sai file phải dừng, không tự dùng ảnh khác. Gửi ảnh ra cloud cần quyền phù hợp và kiểm soát chi phí; không tự upload.

Đây là hợp đồng phát triển, chưa phải schema SQLite/API lưu ảnh đang chạy. Chưa tạo bảng, endpoint, UI hoặc placeholder asset giả. Việc chọn cách lưu, nhập ảnh và tạo bộ tham chiếu sẽ dựa trên benchmark thực tế. Metadata và production cũ không bị migrate hoặc đổi digest chỉ vì thay đổi định hướng.


## Cấu trúc repository

```text
agentforge/
  api/           # Owner-auth localhost HTTP, CSRF, feature endpoints
  ai/            # SQLite Model Hub + source capability policy, no implicit execution
  features/
    film_studio/  # characters, long_form, motion, production, publishing
    media/        # visual jobs, Comfy image, FFmpeg, MP4 validation
  integrations/  # ComfyUI loopback, optional YouTube private upload
  ops/           # read-only environment discovery, runtime evidence
  paths.py       # canonical path, symlink/junction checks
  ops_control.py # pause/resume owner-gated actions
dashboard/       # React/Ant Design
examples/film_studio/
scripts/         # Windows setup, preflight, verification and source/docs hygiene
tests/           # only current video/security tests
```

Film Studio giữ SHA-bound receipts và explicit Owner approval. GPU tasks, external subprocess/YouTube upload không tự chạy khi truy cập GET/UI. Schema và receipt cần thiết để đọc dữ liệu Owner đã lưu vẫn được bảo toàn.

Model profiles, model-route assignments và chính sách AI điều phối được lưu ở `data/company/model_hub.sqlite3` (Owner-managed). Một checkout mới không có model mặc định. Catalog capability chỉ nằm trong Python; `config/` đã bị loại bỏ.

`data/`, `workspace/`, `.env`, `models/` thuộc Owner, ngoài phạm vi xóa. Không có migration tự động đối với historical SQLite. Không có `.env` auto-loader; Windows/process environment vẫn có thể được dùng cho tham chiếu secret nếu Owner cần.

## Pipeline và Model Hub routing

### Model routing và tiếp tục production

Studio đọc các capability đã phân công từ một snapshot SQLite của Model Hub. Bản nháp mới chỉ cần route lập kế hoạch/storyboard và quyền gọi model local khi tạo nội dung. Không yêu cầu route ảnh, motion, FFmpeg hay ngưỡng GPU tạo ảnh cho giai đoạn này. Khi Owner duyệt sản xuất mới yêu cầu route media, quyền công cụ và kiểm tra khả năng tương thích. Khi thư viện có nhân vật và Owner chưa gán route casting riêng, Studio dùng model storyboard local đã khóa trong cùng production. Route casting được gán tường minh nhưng không hợp lệ sẽ bị chặn. Studio không dùng model mặc định, đề xuất tự động hay cloud fallback để thay cho route Owner đã chọn.

Bản nháp mới lưu fingerprint của hồ sơ văn bản khi nhận việc. Trước duyệt, timeline vẫn dùng preset I2V hiện hành nhưng chưa khóa adapter media. Khi Owner duyệt sản xuất, Studio kiểm tra fingerprint văn bản, khóa các profile media từ cùng snapshot và kiểm tra output profile khớp timeline đã xem; digest được tính lại với các binding thực thi, nội dung storyboard không đổi. Studio giữ thêm dấu nhận dạng cấu hình ComfyUI Portable cho motion. Bản nháp cũ vẫn giữ cơ chế pin ban đầu. Resume đối chiếu các route liên quan trước khi gọi adapter. Thay đổi Hồ sơ Model Hub ngoài các route này không làm mất hiệu lực duyệt. Rollback về đúng cấu hình đã duyệt có thể cho phép tiếp tục, dù số revision đã tăng.

Bản nháp cũ dùng revision gốc và dữ liệu lịch sử Model Hub để xác minh route khi revision hiện tại khác. Nếu không đủ bằng chứng, Studio giữ checkpoint và yêu cầu khôi phục cấu hình. Mất kết nối ComfyUI không thay đổi danh tính runtime. Job có trạng thái chưa chắc chắn vẫn phải đối soát ledger trước khi tiếp tục. Các ảnh và clip đã xác minh được đọc lại từ checkpoint.

Fingerprint pin cấu hình profile và preset, không xác nhận bytes của tag Ollama hoặc weights FLUX đã bị thay thế tại chỗ trên runtime. LTX tiếp tục xác minh SHA checkpoint và encoder trước dispatch. Kiểm thử fixture không xác nhận inference GPU trên máy Owner.

FLUX và LTX kiểm tra lại route đã duyệt sau bước chuẩn bị runtime, trong giao dịch SQLite dùng cùng ranh giới ghi với Model Hub. Registry không thể commit thay đổi giữa lần kiểm tra đó và POST. Giao dịch giữ qua bước đặt chỗ và upload ảnh nguồn LTX, rồi nhả ngay sau POST, trước khi theo dõi hay thu kết quả. Gửi job đã được chấp nhận vẫn tiếp tục theo ledger nếu Owner thay đổi registry sau đó.

Pipeline hiện có trong source: lập immutable film plan và shot slots → Owner review → ComfyUI motion job một lượt đã duyệt → nhận clip MP4, verify SHA/frames/FFmpeg → versioned production + optional local TTS → render episode có receipt → Owner review → publishing handoff local/optional private-only YouTube CLI.

Studio có thể lập storyboard từ nội dung Owner, tạo ảnh và motion theo timeline đã duyệt, rồi ghép MP4. Chất lượng visual identity, continuity và hiệu suất phim dài cần nghiệm thu riêng. Mỗi lượt dispatch cần workflow, weights và quyền phù hợp.

## Quản lý model và chính sách Owner

**Model Hub dùng SQLite, không có model mặc định trong Git.** Owner đăng ký, chỉnh sửa và xóa profile từ **Cài đặt → Model AI**. Một máy mới có **0 model đã đăng ký**. Ollama hoặc ComfyUI được phát hiện bởi trang Môi trường không đồng nghĩa được tự thêm vào Model Hub.

- Nguồn dữ liệu duy nhất của model profile, các model được gán cho tác vụ và chính sách điều phối: `data/company/model_hub.sqlite3` (ignored), revision/CAS, rollback transaction và Owner confirmation.
- Danh mục capability (`general.text`, `film.storyboard`, `film.motion`, `image.generate`, `ops.monitor`) được khai báo từ `agentforge/ai/orchestrator_policy.py` và `model_hub.route_catalog()` — chỉ metadata thuộc source, **không chứa model ID mặc định**.
- Lưu profile và gán route **không chạy model**. Film/image routes `CONFIG_ONLY`; `ops.monitor` deterministic. Studio lấy route đã phân công từ snapshot Model Hub và kiểm tra fingerprint trước dispatch; trạng thái CONFIG_ONLY không tự cấp quyền thực thi.
- Owner có thể xóa profile chưa được phân công cho năng lực hiện hành. Muốn xóa profile đang được phân công phải bỏ gán trước. Xóa profile không xóa weights, DB khác hay workspace.
- Cơ sở dữ liệu đã tồn tại được giữ nguyên, không tự sửa hoặc migrate khi GET. Overlay/profile Owner cũ tiếp tục được đọc. Các ID route lịch sử ngoài catalog chỉ lưu trữ, không xuất hiện hay thực thi. Owner đăng ký hồ sơ cần dùng.
- Các giá trị `api_key_env`, `base_url_env` của cloud profile là **tên biến môi trường**, không phải token; không có cơ chế tự nạp file `.env` ở ứng dụng. Nếu cần dùng credentials về sau, chúng phải được inject an toàn vào môi trường tiến trình. Cloud text inference dùng quyền call_cloud đã cấp; mỗi production có giới hạn lượt gọi thực thi, không tự fallback.
- `.env` không nằm trong Git, bị ignore để ngăn lộ bí mật. Không cần tạo file `.env` để chạy local Video Studio; không xóa `.env` sẵn có trên máy Owner bằng Git cleanup.

Chỉ ComfyUI loopback + workflow/SHA/Owner consent thuộc Film Studio mới được gửi GPU thật. Profile có mặt không chứng minh model đã tải, khả năng sinh hoặc độ phù hợp VRAM.

## Hợp đồng readiness

Trong **Cài đặt → Model AI**, Owner có thể xem lại và xác thực cấu hình trước khi lưu, phân công hồ sơ theo năng lực và kiểm tra metadata theo yêu cầu. API `POST /api/model-hub/profile/preview` nhận `ack: "PREVIEW_MODEL_PROFILE"`, `expected_revision` và `profile` để xác thực hồ sơ nháp. API key chỉ gửi ở thao tác lưu hồ sơ.

`GET /api/model-hub` trả `capability_contracts` cho từng profile, gồm adapter tương thích, mã lý do và giới hạn đầu ra. Để kiểm tra runtime, phiên Owner gửi `POST /api/model-hub/readiness` với CSRF và payload gồm `ack: "CHECK_CAPABILITY_READINESS"`, `profile_id`, `capability` và `expected_revision` lấy từ catalog.

`route_configurable` phản ánh chính sách gán route, còn `local_runtime_compatible` phản ánh adapter local. Hồ sơ OpenAI-compatible và Anthropic-compatible hỗ trợ text inference qua HTTPS. Metadata kiểm tra endpoint model, không xác nhận inference; probe cố định cần Owner xác nhận riêng.

Preflight trả `METADATA_COMPATIBLE`, `UNAVAILABLE`, `UNSUPPORTED`, `MISSING_DEPENDENCY` hoặc `NOT_CHECKED`, cùng mã `reason` cụ thể. `runtime_available` cho biết runtime có trả được metadata cần thiết, còn `endpoint_metadata_compatible` cho biết metadata đó phù hợp với model/workflow. Giá trị `null` là chưa xác định. Kết quả luôn có `inference_verified: false` và `endpoint_ownership: "NOT_CHECKED"`. ComfyUI mở bên ngoài có thể trả metadata tương thích. LTX vẫn cần cấu hình thư mục Portable, công cụ media và weights local theo chính sách dispatch hiện hành. SHA weights và tài nguyên khả dụng vẫn do runtime kiểm tra khi thực thi.


## Creative Director

Bản nháp motion có tiêu đề cảnh và chế độ thời lượng hiện hành dùng Creative Director. Bản nháp cũ, ý tưởng tự do và sản xuất ảnh tĩnh vẫn dùng planner hiện tại. Không cần migrate SQLite. AI đề xuất nhóm hành động theo thứ tự, góc quay, ý đồ và thời lượng tương đối; nhận thời lượng cảnh bằng giây thay vì số frame kỹ thuật. `creative_plan.validate_scene_shots` kiểm tra hợp đồng sáng tạo không phụ thuộc output profile. `compile_plan` chuyển nội dung đã kiểm tra thành segment theo output profile và ngân sách runtime hiện hành. Định dạng creative plan đã lưu và cách kiểm tra digest không đổi.

Đây là ranh giới đầu tiên trong đường chạy authored script, chưa phải planner độc lập hoàn toàn với runtime. Free-form planning và worker vẫn yêu cầu pipeline local hiện hành; không tuyên bố hỗ trợ phương pháp sản xuất khác trước khi adapter thật được kiểm chứng.

The approval digest includes the compiled plan, the segment storyboard and the existing model and motion identity. On resume the stored plan is recompiled against the pinned output profile and the storyboard frame counts are rechecked. Editing segment text updates the storyboard digest and uses the existing asset invalidation rules. Authored scene boundaries and the creative segment layout stay fixed during segment edits. A new production is required to propose a different layout.

### Planning repair and limitations

Incomplete or out-of-order action coverage receives at most one contextual model revision; invalid coverage after that stops planning. Segment prompts distinguish prepare, progress and complete for continued actions. Exact duplicate descriptions or motion prompts receive bounded repair. These controls do not establish semantic or visual continuity.

Xem [runtime](RUNTIME.md) và [production](PRODUCTION.md) để kiểm tra hành vi thực tế.

Chính sách điều phối lưu mode, mappings, permissions, tools và cloud_call_limit. Các snapshot cũ được đọc qua lớp tương thích và chiếu sang chính sách hiện hành; không tự ghi lại SQLite khi đọc. Khi Owner lưu chính sách mới, các trường đã ngừng hỗ trợ không còn được lưu trong snapshot mới. Lịch sử và rollback vẫn bảo toàn dữ liệu gốc.

Cloud text: endpoint là API base URL (ví dụ `https://provider.example/v1`), không phải URL đầy đủ của `/chat/completions` hoặc `/messages`. Dùng API key nhập trực tiếp được DPAPI bảo vệ hoặc biến môi trường hiện có. Chỉ cấp quyền `call_cloud` nếu đồng ý gửi nội dung và metadata nhân vật đến provider. Lượt gọi được lưu trước khi dispatch và tính cả thất bại; giới hạn số lượt không phải giới hạn tiền. Không tự retry, không chuyển provider. Kiểm tra model metadata có thể không được gateway hỗ trợ; thử inference riêng để xác nhận JSON. Cloud image/video chưa hỗ trợ.
