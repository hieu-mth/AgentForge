# Skill Engine — M8: adapter theo domain

**Trạng thái hiện tại (11/2026):** M8 adapter đã hoàn tất; M4 chuyển canonical implementation sang `agentforge/features/` cho website, webapps, media, film và growth. `agentforge/domains/` và một số top-level modules là **compatibility aliases**, không phải nơi thêm logic mới. Skill invocation vẫn do `agentforge/core/skill_runner.py` kiểm soát (Owner permissions, task history, no automatic replay). Các giới hạn runtime AI/GPU/Docker chưa được chứng nhận; không coi việc có skill/route là bằng chứng model đang chạy.

## Thêm một kỹ năng an toàn

1. Định nghĩa `skills/<domain>.<action>/skill.toml` theo schema v1 của `agentforge/core/skill_registry.py`. Manifest chỉ là **dữ liệu**, không được chọn Python import, mã lệnh, key API hoặc cấp quyền.
2. Chọn adapter trong `agentforge/core/skill_adapters/`: `web.py` (website/webapp), `research.py`, `media.py`, `analytics.py`, `growth.py`. Bổ sung **hai phần cùng một file**: `POLICY` hardcoded (worker, mode, exact permissions) và nhánh `dispatch` explicit dùng callable đã review. Nhóm domain mới phải được đăng ký tĩnh ở `__init__.py`.
3. Nếu cần loại permission/tool mới, review riêng validator registry, `missing_grants`, HTTP Owner approvals và test trước. **Không** suy ra quyền từ prompt hoặc chỉ từ TOML.
4. Gắn role/model route qua Model Hub cho tác vụ text nếu phù hợp; video/image hiện config-only. Không coi model/provider đã healthy vì có profile.
5. Thêm regression cho schema/permission, happy path, tampered manifest và handler lỗi; chạy `python -m unittest discover -s tests -v` và Windows CI.

## Execution boundary

```text
skills/*.toml -> skill_registry.validate -> skill_runner._contract (exact POLICY)
                                         -> missing_grants (Owner confirms)
                                         -> task_history (durable SQLite)
                                         -> skill_adapters.dispatch (static allowlist)
                                         -> existing business function
```

Các adapter **không import implementation ở module load time**; chỉ import khi chạy handler đã được cho phép. Kết quả, status, SHA và persistence do runner hiện tại xử lý. `skill_adapters.dispatch` là helper nội bộ, không phải API công khai có thể bỏ qua `skill_runner.invoke`.

## Ranh giới và việc chưa làm

- Các feature đã có canonical code dưới `agentforge/features/`; các `domains/*` shims được giữ lại vì một số caller và test monkeypatch dựa vào cùng module object. Đừng xóa hoặc viết implementation mới trong shim nếu chưa có migration/evidence.
- M8 chỉ chia lại policy và invocation theo domain, không thay schema v1, không thêm permission, route HTTP, model billing hay tự chạy tools. `analytics.quality_check` và `growth.report` là deterministic Python rules, **không** dùng model route.
- Kể cả khi unit tests PASS, browser sandbox generated React, ComfyUI GPU thực, channel publishing và doanh thu vẫn chưa được kiểm chứng.
