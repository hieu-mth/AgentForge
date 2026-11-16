# Nghiệm thu AgentForge trên máy Owner

Phạm vi phát hành là một Owner sử dụng AgentForge trên localhost Windows.
Mỗi luồng chỉ được đưa vào vận hành khi có bằng chứng từ đúng commit và
máy chạy thực tế. CI của repo kiểm tra Dashboard, API, thành phần tham
chiếu và các fixture kỹ thuật.

## Cập nhật và kiểm tra môi trường

Tại PowerShell, dừng server đang chạy rồi cập nhật repo. Dùng Python trong
`.venv` hiện có. Nếu chưa cài môi trường, xem [hướng dẫn Windows](../DEVELOPMENT.md).

~~~powershell
cd D:\AgentForge
git status --short
git switch main
git pull --ff-only origin main
git rev-parse --short HEAD
.\.venv\Scripts\python.exe -m pip install -e ".[media]"
npm.cmd ci --prefix dashboard --ignore-scripts --no-audit --no-fund
npm.cmd run build --prefix dashboard
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -SaveReport
~~~

Chạy [Base V1 acceptance](base_v1/README.md), gồm đăng nhập Owner, đối chiếu
registry/SQLite và backup → verify → restore vào vùng staging. Lưu lại commit,
phiên bản công cụ, thời gian và kết quả. Dùng chính bản backup đã xác minh để
thử phục hồi trước khi áp dụng cho dữ liệu vận hành.

## Điều kiện đưa từng luồng vào sử dụng

| Luồng | Bằng chứng cần có |
| --- | --- |
| Dashboard và workflow | Đăng nhập Owner, tạo goal từ Dashboard, duyệt SHA và cấp quyền đúng bước. Kiểm tra task/goal/artifact sau đóng và mở lại server. |
| Website bán nệm | Tạo website thật bằng Ollama, xem preview desktop/mobile, gửi một feedback cụ thể và kiểm tra nội dung thay đổi. Owner duyệt đúng SHA. |
| Đơn bán nệm | Owner xác nhận danh mục, giá, phạm vi và phí giao. Dùng một đơn thử có consent để đi qua báo giá, chốt đơn và thông báo đến đúng người nhận. |
| React do AI sinh | Chạy create → revision → Docker Chromium offline QA → Owner accept trên đúng proposal SHA. Giữ log và artifact digest. |
| Ảnh và video chuyển động | Tạo một ảnh và một clip bằng ComfyUI trên GPU Owner, đo VRAM/thời gian, kiểm tra SHA và decode, sau đó mới thử ghép nhiều shot. |
| Cloud hoặc YouTube | Nếu dùng, xác nhận provider/account và quyền Owner trước khi chạy smoke riêng. Upload YouTube CLI giới hạn private. |

Ưu tiên luồng website + một đơn bán nệm nếu mục tiêu phát hành là MVP phục
vụ gia đình. Theo dõi trạng thái model/GPU/Docker hoặc tính năng chưa thử
theo [Runtime Certification](runtime_2026_11/README.md). Dùng
[Wave 7](wave7/README.md) cho React QA và [Wave 8](wave8/README.md) cho clip
motion. Mỗi lần nghiệm thu lưu kết quả PASS, FAIL hoặc BLOCKED kèm bằng chứng.
