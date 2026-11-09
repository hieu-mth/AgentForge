# Feature-first — ranh giới module AgentForge (M4)

**Đã triển khai:** `features/growth`, `features/websites`, `features/webapps`, `features/media`, `features/film_studio` và `integrations/comfyui.py` (M4a–M4d2). **Chưa triển khai:** chuyển research/ops theo các business use case còn sống và gỡ compat aliases M5. Không nhầm refactor module với nghiệm thu GPU/AI model thật.

## 1. Chọn chỗ để code

| Thư mục | Ownership | Không thuộc trách nhiệm |
| --- | --- | --- |
| `api/` | Session, CSRF, HTTP, payload | Business decision, IO video |
| `core/` | Workflow, quyền, acceptance, durable task | Prompt/feature-specific code |
| `ai/` | Model profiles, task text routing | Approval, GPU/YouTube billing |
| `features/websites/` | Site design, revision, asset preview, QA | HTTP auth, model credentials |
| `features/webapps/` | React proposals, static QA, bounded sandbox control | Tùy ý execute AI source trên Windows host |
| `features/media/` | Asset/media/SRT/voice/video rendering và quality | Film long-form scheduling |
| `features/film_studio/` | Film plan/shot ledger, validated workflow, one-shot submission | Tùy tiện download GPU model hoặc video accepted |
| `features/growth/` | Campaign, owner-written records, manual handoff, reports | Real YouTube publishing/payment |
| `integrations/comfyui.py` | Fixed localhost /system_stats, /prompt, /history JSON transport | Approval, retry policy, video QA |
| `storage/` | Shared artifact persistence/path guards | Business SQL của riêng một feature |
| `ops/preflight.py` | M9 kiểm tra read-only setup/versions/local paths | Tự sửa file, chạy provider hoặc cài package |
| `domains/` | Compatibility imports cho code cũ | Logic nghiệp vụ mới |

## 2. Luồng dependency

```text
dashboard React -> api/ (Owner auth + CSRF)
                  -> core/ (permissions/approvals/task history)
                  -> features/<capability> -> ai/ (text model routing)
                                           -> integrations/ (bounded IO)
                                           -> storage/ (durable state)
```

- Feature code mới import `agentforge.features.<domain>`. Không tạo business logic dưới `domains/`.
- Import legacy vẫn trả **cùng module object** nhờ shim, nên monkeypatch, runtime state và test hiện có không tách đôi.
- CLI cũ dùng `python -m agentforge.domains....` vẫn hoạt động qua forwarding `main()` khi có CLI cũ.
- `integrations/comfyui.py` không import `features/`, không cấp quyền và không retry HTTP. `film_studio.motion_comfy._json_request` là compatibility patch point, lỗi transport được chuyển về `MotionError`.
- Giữ nguyên `data/`, `workspace/`, SQLite file names, proposal SHA, Owner review. Refactor code không migrate hoặc dọn user artifacts.

## 3. Quy trình thêm skill/feature

1. Bắt đầu từ mục tiêu người dùng và deliverable, chọn `features/` tương ứng; không tạo folder trống theo roadmap.
2. Nếu cần skill, thêm manifest TOML, code-level POLICY và handler explicit tại `core/skill_adapters/` theo [Skill Engine](SKILL_ENGINE.md). Manifest tuyệt đối không có Python import/secret hoặc tự nâng quyền.
3. Nếu gọi model text, cấu hình route trong Model Hub; nếu gọi image/video, ghi rõ `config-only` hay `runtime verified`, không tự tuyên bố GPU hoạt động.
4. Đối với tool IO mới, viết transport riêng trong `integrations/` chỉ sau khi có use case thực, kiểm thử timeout/bounded response/allowlist/Owner consent và no-blind-retry.
5. Thêm test import identity, quyền, path, CLI, SHA/evidence; cập nhật [STATUS](../STATUS.md) và [FILE_CATALOG](FILE_CATALOG.md); chỉ merge khi Windows CI PASS.

**Định nghĩa hoàn thành:** code/module được refactor và CI PASS khác với sản phẩm website chất lượng cao, React AI browser QA, video motion thật, hoặc publishing ngoài đời. Các mốc thực phải có evidence và Owner approval riêng.
