# Templates — reviewed source dependencies

Các file trong thư mục này là **source template đã review được AgentForge đọc khi tạo sản phẩm**. Chúng khác với JSON minh họa trong [examples](../examples/README.md).

## Templates hiện có

- [NovaMart](novamart/README.md) — React marketplace reference. Runtime `agentforge/domains/webapps/builder.py` và `toolchain.py` đọc `package.json`, `package-lock.json`, `src/` và scaffold để sinh đề xuất WebApp. Vẫn là demo cart/search, **không phải sàn thương mại điện tử có thanh toán**.

## Quy tắc bảo trì

- **Không xóa template chỉ vì trông giống demo**. Trước khi di chuyển/đổi dependency, kiểm tra callers, tests, CI và sandbox.
- Giữ lockfile và mã nguồn đã duyệt; mọi thay đổi template ảnh hưởng source của **proposal mới**. Proposal cũ phải giữ nguyên SHA và khả năng đọc lại.
- CI có quyền build và browser-test **trusted template**; AI-generated source vẫn không được chạy trên Windows host hay Owner browser origin nếu chưa có isolation đã xác minh.
- `node_modules/`, `dist/` là build cache local, không commit Git. Không sửa hoặc xóa `data/`, `workspace/`.
- Repository hiện dùng **local-first checkout**: template nằm ngoài Python wheel và cần có trong checkout để chạy Builder. Không coi việc build wheel thành công là bằng chứng template có trong bản wheel độc lập.

Xem [cấu trúc hiện hành](../docs/architecture/REPOSITORY_STRUCTURE.md) và [trạng thái tính năng](../docs/STATUS.md).
