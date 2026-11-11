# Đợt 6 — MVP kinh doanh nệm gia đình

**Code status:** LOCAL_OWNER_WORKFLOW_READY · PUBLIC_INGRESS_NOT_CONNECTED · SHIPPING_OWNER_VERIFICATION_REQUIRED · NOT_PRODUCTION_COMMERCE_READY.

## Mục tiêu

Bắt đầu từ khách quen/giới thiệu và khách mua trực tiếp. Nguồn nệm và đơn vị
giao đã có; **phạm vi giao, mẫu nệm, giá và số điện thoại chưa được cung cấp
hoặc xác minh**. Không tự suy ra lợi nhuận ngân hàng, tồn kho hay vùng giao.

Flow: khách chủ động gọi/Zalo → Owner ghi nhận lead đã đồng ý liên hệ →
Owner liên hệ/báo giá → xác minh phí và khu vực với đơn vị vận chuyển →
khách đồng ý, Owner xác nhận đơn → giao hàng → ghi nhận đã giao.
Không có auto checkout, thu tiền, quảng cáo, vận đơn hay gọi model AI.

## 1. Dashboard Owner

Trong Dashboard localhost chọn **Kinh doanh → Bán nệm**.

- Nhập lead qua giới thiệu hoặc trực tiếp: tên, số điện thoại, nhu cầu,
  khu vực và checkbox xác nhận khách đồng ý được liên hệ.
- Trạng thái: NEW → CONTACTED → QUOTED → OWNER_CONFIRMED →
  DELIVERY_PLANNED → DELIVERED; LOST/CANCELLED ở các bước phù hợp.
- Giá bán chỉ nhập sau khi Owner kiểm tra sản phẩm. Khi chưa xác minh
  phạm vi và phí giao từ đơn vị vận chuyển, không thể OWNER_CONFIRMED.
- Đơn đã xác nhận không đồng nghĩa giao thành công.
- Mỗi lead tạo outbox NEW_LEAD. Khi xác nhận đơn, thêm ORDER_CONFIRMED.
  Xem/copy tin qua dashboard, gửi thật cho ba qua Zalo/SMS rồi mới bấm
  **Đã gửi thực tế — ghi nhận**. Copy không tự đánh dấu SENT.

Contact data nằm trong data/company/mattress_sales.sqlite3, được backup
bởi Wave 2 full backup. Dữ liệu SQLite và archive hiện **không mã hóa ở
mức ứng dụng**: bảo vệ bằng account Windows, mã hóa ổ đĩa, kiểm quyền file,
không upload lead/backup vào Git. S5 Growth anonymous metrics không lưu
số điện thoại; hai hệ thống vẫn tách biệt.

## 2. Website giới thiệu nệm

Mẫu không chứa số điện thoại, sản phẩm, giá, bảo hành hoặc vùng giao giả.

PowerShell:

    cd D:\AgentForge
    Copy-Item .\examples\mattress_sales\site.example.json .\data\company\mattress_site.json

Chỉnh file data/company/mattress_site.json theo dữ liệu người bán xác nhận:
brand, phone, zalo_phone (nếu có), intro và danh sách products. Chỉ nhập
sản phẩm đã có thật; phone phải được chủ số đồng ý công khai.

    .\.venv\Scripts\python.exe -m agentforge.features.mattress_sales.cli site-export --settings .\data\company\mattress_site.json --confirm-export

HTML CSS responsive được tạo ở
workspace/products/mattress-referral-mvp/index.html. Website có nút gọi và
Zalo, **không có form / không lấy thông tin khách tự động**, không thanh
toán, không giả vờ đã bán hoặc có tồn kho. File chỉ nằm local; Owner có thể
đưa file lên host static riêng **sau khi kiểm nội dung**. Không public API
Owner 127.0.0.1:8780.

Muốn thay file đã export, trước hết kiểm SHA-256 của bản hiện tại và truyền
cờ --replace-sha <SHA đã đối chiếu>. Lệnh không tự overwrite website cũ.

## 3. Gửi Telegram tùy chọn — chỉ khi người nhận dùng Telegram

Đây là tích hợp **opt-in**, không phải tính năng Zalo OA.
Nếu người nhận đồng ý, Owner tạo Telegram Bot + private chat ID và đặt
credentials vào biến môi trường, **không commit/lưu vào repo**:

    $env:AGENTFORGE_MATTRESS_TELEGRAM_BOT_TOKEN = '<bot token>'
    $env:AGENTFORGE_MATTRESS_TELEGRAM_CHAT_ID = '<chat ID>'
    .\.venv\Scripts\python.exe -m agentforge.features.mattress_sales.cli notify-telegram --notice-id <id từ Dashboard> --confirm-external-send

Mỗi lệnh chỉ gửi 1 notice. Outbox chuyển PENDING → DISPATCHING trước khi
gửi. Chỉ HTTP 200 và JSON ok=true mới là SENT; timeout/unknown đánh dấu
NEEDS_REVIEW (hoặc DISPATCHING khi process chết). Không có retry mù, không
in token và không tự bật scheduler. Muốn tự động gửi khi PC chạy phải xây
cấu hình vận hành và xác nhận kênh trước; bản này chưa tuyên bố tự thông báo
24/7.

## 4. Nhận CSV từ một public form provider (không có public API AgentForge)

Nếu có dịch vụ form công khai độc lập đã kiểm điều khoản quyền riêng tư,
lấy CSV UTF-8 đúng các cột:

    external_id,customer_name,phone,interest,area,consent_to_contact

external_id ổn định/duy nhất; consent_to_contact chỉ YES khi khách
thực sự chọn checkbox đồng ý. File tối đa 256 KiB, tối đa 500 dòng;
các dòng được validate trước khi ghi.

    .\.venv\Scripts\python.exe -m agentforge.features.mattress_sales.cli import-csv --file <đường dẫn CSV> --confirm-import --confirm-consent-provenance

Request ID từ external_id giúp import lại không tạo khách/thông báo trùng.
Mỗi row commit riêng; nếu lỗi I/O giữa batch, có thể import một phần,
rerun là idempotent. Không có public hosted receiver, background sync hay
lời hứa form đã hoạt động trước khi Owner chọn provider và triển khai.

## 5. Nghiệm thu thực tế theo thứ tự

1. Chạy Dashboard, mở Bán nệm, thêm một lead thử với consent thật.
2. Ghi nhận CONTACTED sau khi liên hệ; nhập sản phẩm/giá đã hỏi.
3. Xác nhận đơn trước khi hỏi vận chuyển phải bị từ chối.
4. Hỏi carrier về khu vực và phí giao; unsupported vẫn không thể chốt.
5. Chỉ khi supported, phí rõ ràng và khách đồng ý mới xác nhận đơn.
6. Thông báo chờ gửi xuất hiện; copy/gửi cho đúng người nhận, rồi mới
   bấm xác nhận đã gửi.
7. Ghi nhận lịch giao và đã giao sau khi xác minh thực tế.
8. Tạo full backup, verify và staged restore vào một thư mục khác;
   đối chiếu mattress_sales.sqlite3 và HTML không bị mất.
9. Nếu muốn Telegram, thử bot riêng với data synthetic trước khi
   truyền dữ liệu khách thật.

Các tests tự động nằm tại tests/test_wave6_mattress_mvp.py. Không có chi
tiết nguồn nệm, số điện thoại hay vùng giao của Owner nào được đưa vào
source/test. Cần Owner nghiệm thu kênh liên hệ và đơn vị vận chuyển trước
khi đăng trang public.

## 6. Quyết định chưa triển khai (không giả vờ đã xong)

- Public lead form có chống spam/rate limit, consent log và trusted pull
  24/7: **chưa tích hợp**. Không được expose Dashboard/API localhost.
- Zalo OA push tự động: **chưa tích hợp**. Cần quyền và kênh chính thức.
- Telegram tự động nền: **chưa bật** và không có cam kết gửi khi PC tắt.
- Phạm vi giao, phí, giá, hàng tồn và chính sách bảo hành: **Owner phải
  xác minh**. Không có AI quyết định thay.
- Payment gateway, hóa đơn, tracking vận chuyển, quảng cáo tự tiêu tiền,
  compliance dữ liệu cá nhân, production uptime: **chưa chứng nhận**.

MVP local-first đủ để thử bán thật bằng kênh người quen, đo leads và đơn
Owner xác nhận. Chỉ nâng cấp tiếp sau khi có dữ liệu và đã chốt carrier,
số liên hệ, nơi host website và kênh thông báo.
