# Wave 6 — AI React Source-Aware Revision

Trạng thái: code triển khai, CI chờ PASS; real-model và generated React browser QA vẫn UNVERIFIED.

## Luồng sửa và quyền

1. Owner mở proposal AI Developer qua authenticated GET /api/webapps/{id} và xem đầy đủ source cùng SHA-256.
2. Gửi feedback 10–3000 ký tự qua POST /api/webapps/{id}/revision có ack REQUEST_REVISION. Backend xác minh session đã review source và tạo Goal webapp.source_revision; chưa gọi model.
3. Owner duyệt SHA plan, cấp riêng model.invoke và workspace.propose; một call webapp_developer đọc source hiện tại cùng feedback, chỉ trả 1–8 file thay đổi. Backend giữ nguyên mọi file khác; chặn no-op, unsafe API/import, JSX syntax hỏng, SHA stale, path ngoài allowlist, ghi đè lockfile và template.
4. Mỗi phiên bản mới là proposal bất biến trong data/company, ghi parent proposal ID+SHA; giao diện hiện bounded unified diffs và lịch sử nguồn. Không chạy npm hoặc deploy.
5. Rollback: UI phải hiển thị đủ source của phiên bản đích. POST /api/webapps/{current}/rollback chỉ cho phép target đã được inspect cùng Owner session, SHA đúng và là ancestor. Tạo proposal mới dùng code ancestor, không gọi model, không đè workspace project. Apply vào thư mục mới cần Owner đồng ý riêng.

M4/M5 compatibility aliases và SHA của proposal cũ không đổi. Version chain giới hạn để chặn vòng lặp/malicious provenance. Bản sửa vẫn giới hạn 8 file source allowlisted, không phải arbitrary full-stack.

## Definition of done

CI: Python unittest bao gồm 2–3 edits, CSS-only/JSX-only preservation, SHA/diff, no-op, path/import/unsafe, rollback ancestor, tamper, HTTP auth+CSRF, trusted Dashboard build. Không thi hành generated code trên máy host.

Owner QA vẫn chờ: tạo React app thật với model đang cấu hình; thực hiện 3 lần feedback khác nhau và kiểm tra source/diff mỗi lần; rollback; ghi nhận tỷ lệ đúng yêu cầu và latency. Build/browser QA cách ly, kiểm lỗi runtime, screenshots và export thuộc Đợt 7.

## Lệnh kiểm tra Windows

~~~powershell
cd D:\AgentForge
git status --short
.\.venv\Scripts\python.exe -m unittest -v tests.test_wave6_source_revision
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
npm.cmd run test:navigation --prefix dashboard
npm.cmd run build --prefix dashboard
~~~

Không chạy npm của source AI tạo ra trên host Windows. Phần QA runtime cần sandbox riêng ở Đợt 7.
