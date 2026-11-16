# AgentForge — nghiệm thu PR #122

Đối chiếu `main` tại `541222f` và đầu PR #122 tại `8b7b3fe`. Phạm vi gồm thay đổi giao diện từ #110–#121, luồng Owner API và các điểm nối giữa workflow, sản phẩm và runtime. Môi trường kiểm thử là Linux với Python 3.13.5, Node 24 và Chromium Headless Shell. Dữ liệu probe dùng checkout thử nghiệm.

## Audit trước và sau

| Phạm vi | Phát hiện | Sau sửa |
| --- | --- | --- |
| #110–#118, Tổng quan | Hoàn thành hôm nay chia ngày theo UTC trong khi hoạt động hiển thị giờ Việt Nam. Kế hoạch mới ở trạng thái PLANNED vắng trong hàng chờ Owner. | Ngày và xu hướng dùng giờ Việt Nam. Hàng chờ đi tới danh sách kế hoạch, khử lặp với bootstrap và hiển thị tác vụ gián đoạn đã có trong mẫu. KPI vẫn giới hạn trong snapshot local. |
| #119–#120, Giao việc | Hai mẫu gợi ý đi tới intent Workspace chưa hỗ trợ, một mẫu React thiếu từ khóa định tuyến. Browser smoke vẫn tìm KPI và nút đã bỏ. | Mẫu gợi ý dùng các intent có sẵn. Luồng lên kế hoạch giữ phần prompt mới gõ khi phản hồi của yêu cầu trước đến. Browser test kiểm tra trạng thái thực thi và nghiệm thu riêng trên danh sách hiện hành. |
| #121, Kế hoạch & Duyệt | Một SHA dùng cho mọi bước nên yêu cầu RESUME cũ có thể được nhận khi Goal lại ở trạng thái chờ. Checkbox quyền thiếu tên truy cập. Nút retry hiện cho workflow ngoài allowlist. | RUN/RESUME từ Dashboard mang phiên bản Goal đã xem. SQLite kiểm tra đồng thời trạng thái và phiên bản khi claim. RESUME và RUN sau retry cần phiên bản mới. Initial RUN cũ vẫn tương thích trước lần chạy đầu. Nút retry bám nhóm template hỗ trợ và quyền có tên truy cập. |
| Kết quả và nghiệm thu | Khi GET proposal lỗi, Drawer kế hoạch đóng dù Owner chưa mở được sản phẩm. GET phụ có thể trả về sau đổi phiên. | Giữ Drawer khi mở sản phẩm thất bại, xóa lỗi cũ khi Owner thử lại và bỏ dữ liệu của phiên cũ. Luồng tiếp tục dùng bản đề xuất SHA và các cổng QA/Owner hiện có trước khi chấp nhận hoặc apply. |
| #122, Video / Nhân vật | Media Studio từng hiện series hư cấu và hành động chưa kết nối. Hai module Nhân vật chưa được ghi trong inventory. | Commit đầu của #122 thay trang mock bằng liên kết tới thao tác thật. Bổ sung inventory, giữ các điều kiện xét duyệt ở trang đích. |
| Kho / Ảnh AI, Vận hành, Bộ nhớ | Browser chạy với backend thật lộ lỗi import đồng thời ở lịch sử ảnh và lỗi shadow import trên hai API ops/memory. Fixture UI trả dữ liệu hợp lệ nên không bắt được. | Read routes dùng module ảnh canonical và import brain store ở cấp module. Kiểm thử HTTP kiểm tra cả ba endpoint sau đăng nhập. |
| Bảo mật transport / gateway | So sánh chuỗi Unicode có thể làm HTTP handler lỗi trước khi trả mã xác thực. Linux coi đường dẫn Windows là tên file tương đối. | So sánh digest bằng bytes và trả mã 401/403 đúng. Gateway từ chối path có root/drive Windows trên Linux. |
| Đội ngũ, Lịch sử, Website, Kinh doanh, Cài đặt | Kiểm tra entrypoint và các ranh giới Owner. Growth có dữ liệu synthetic gắn nhãn riêng. Marketplace scaffold dùng dữ liệu demo có chủ đích. | Các route hiện tại được giữ để nghiệm thu. Chức năng kinh doanh vẫn là luồng local, gồm lead/báo giá/lưu đơn và handoff thông báo theo cấu hình. |

## Bằng chứng kiểm thử

- Baseline Python 3.13 cài đủ dependency chạy 1.042 test. Suite ghi 2 lỗi kiểm kê module và 1 lỗi đường dẫn Windows trên Linux. GitHub Actions #805 ở đầu PR cũ dừng tại Edge smoke vì test tìm nhãn nghiệm thu tách rời của Workspace cũ.
- Sau sửa, Python 3.13 chạy 1.045 test, OK. Dashboard Node tests 40/40, NovaMart 7/7. Vite build cả hai thành công. Chromium Headless Shell chạy Dashboard smoke, 31 kịch bản reliability và NovaMart smoke. Các suite fixture không gọi model hay AI provider.
- Browser với API localhost thật mở 21 route ở hai kích thước 1366 px và 390 px. Probe đăng nhập Owner, lập kế hoạch, duyệt SHA và kiểm tra khóa model khi backend chưa bật external tools. Không có API fixture trong lượt này.
- Wheel có entrypoint AgentForge và loại trừ frontend/test source. Kiểm tra link tài liệu, source hygiene và 22 compatibility aliases đạt. FFmpeg encode/decode fixture xác minh cả audio lẫn video.

## Quyền và giới hạn

- Lập kế hoạch là bước deterministic. Duyệt SHA rồi mới cấp quyền thực thi. Model Hub và runner vẫn dùng các chính sách nguồn, model, cloud và sandbox hiện có.
- Danh sách Goal, task và artifact có giới hạn snapshot. Dashboard vẫn cần cải thiện kích thước bundle, khoảng 1,38 MB JS minified, 440 kB gzip ở lần build này.
- Cần nghiệm thu riêng Ollama inference, ComfyUI checkpoint và GPU, motion video, Docker offline QA cho React do AI sinh, cloud consent với provider thật và tích hợp gửi thông báo. FFmpeg fixture chỉ xác minh encode/decode audio và video.
- Chưa xác minh hành vi trên Windows/Edge thật hoặc trên dữ liệu Owner đã sử dụng lâu ngày. Duyệt số liệu kinh doanh, chất lượng sản phẩm, keyboard và responsive thực tế theo từng workflow trước khi vận hành thường xuyên.

## Cập nhật và chạy trên Windows

Dừng server hiện tại bằng Ctrl+C. Dùng nhánh PR sau khi đã kiểm tra thay đổi local. Các lệnh dưới đây không cần dọn `data/`, `workspace/` hay cấu hình Owner.

~~~powershell
cd D:\AgentForge
git status --short
git fetch origin
git switch -c verify-pr122 --track origin/feat/dashboard-workflow-hardening
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run test:navigation --prefix dashboard
npm.cmd run build --prefix dashboard
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
npm.cmd run test:browser --prefix dashboard
npm.cmd run test:reliability --prefix dashboard
.\.venv\Scripts\python.exe -m agentforge --port 8780
~~~

Mở http://127.0.0.1:8780/dashboard/ và đăng nhập bằng mã Owner hiện trong PowerShell. Tạo kế hoạch website, đối chiếu SHA trước khi duyệt và kiểm tra nó xuất hiện trong **Đội ngũ AI → Kế hoạch & Duyệt**. Kiểm tra thêm **Lịch sử tác vụ**, **Kho thành phẩm & Ảnh AI**, **Duyệt AI & Video**, **Bộ nhớ Owner** và **Vận hành**.

Chạy preflight trước khi thử inference. Khi cần nghiệm thu lượt model thật, mở server với `--allow-external-tools`, chọn profile Ollama và duyệt từng bước trong Dashboard. Kiểm tra bản nguồn, kết quả QA và SHA trước khi Owner chấp nhận. Với video, xác minh storyboard, ảnh, tệp MP4 và quyết định nghiệm thu riêng.

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
~~~

Xem [hướng dẫn Windows](../DEVELOPMENT.md) và [Owner Runtime Certification](runtime_2026_11/README.md) để chạy các probe model, FFmpeg và Docker tương ứng, đồng thời ghi nhận trạng thái GPU.
