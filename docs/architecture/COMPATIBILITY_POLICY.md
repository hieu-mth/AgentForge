# M5 — Compatibility imports: hiện trạng và tiêu chí dọn

**M5 phase 1 triển khai:** 22 root compatibility imports đã trỏ **trực tiếp** tới canonical `agentforge.features.*` thay vì đi qua `agentforge.domains.*`. Kiểm tra read-only nằm ở `scripts/compat_audit.py` và regression `tests/test_m5_compatibility.py`.

## Vì sao không xóa ngay?

- Alias `agentforge.product_builder`, `agentforge.media_assets`, `agentforge.growth_store` cùng các CLI `agentforge.webapp_builder` có thể vẫn được các script nội bộ, test hoặc tooling ngoài Git gọi.
- Chỉ grep repo không thể chứng minh người dùng không có script PowerShell/Python ở ngoài repository đang import những tên này.
- Các `agentforge.domains.*` compatibility modules vẫn được giữ với **cùng module object** để monkeypatch/SQL state không bị tách đôi.
- CLI `python -m agentforge.product_builder`, `python -m agentforge.domains.websites.builder` vẫn forwarding sang implementation mới, không được xóa mà chưa có kế hoạch migration.

## Thực thi hiện tại

```powershell
cd D:\AgentForge
.\.venv\Scripts\python.exe scripts/compat_audit.py --check
```

Script chỉ đọc Python trong `agentforge/`, `tests/`, `scripts/`; **không** đọc `data/`, `workspace/`, `.env` hay model weights. Báo cáo gồm 22 alias, canonical đích, dấu vết caller trong source và trạng thái. `internal_references` chỉ là bằng chứng tĩnh (AST), **không** bảo đảm bao phủ import động hoặc caller ngoài repo. `safe_to_delete` luôn false; công cụ này không có thao tác xóa.

## Điều kiện để cân nhắc xóa một alias ở M5 phase 2

1. Xác minh được caller trong cả Python/CLI/scripts/PowerShell và các hướng dẫn dùng thật trên máy Owner; cập nhật mọi caller trước.
2. Có regression cho import identity, monkeypatch, root paths, CLI và user data. Không đánh đổi sự ổn định để giảm vài file.
3. Có giai đoạn deprecation/documentation trước khi bỏ một public import; **không mặc định** rằng zero internal caller là an toàn cho external tools.
4. Mỗi thay đổi phạm vi nhỏ, Windows CI PASS và cách rollback qua Git commit mà không phải migrate/delete `data/`, `workspace/`.

**M5 phase 2 chưa làm.** 22 root aliases và tất cả `domains/` shims vẫn được giữ; phase 1 chỉ loại bỏ chuỗi trung gian trong root wrappers và cung cấp audit gate. M4 research/ops cũng vẫn cần review riêng.
