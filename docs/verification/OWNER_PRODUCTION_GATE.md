# Owner production gate — AgentForge Video Studio

CI Windows/React chỉ kiểm code, security contracts, fixture FFmpeg và static asset serving. Production GO đòi bằng chứng trên PC Owner với đúng commit.

1. Đăng nhập Dashboard localhost; xác nhận Owner session, CSRF và các route sản xuất video.
2. Ollama/ComfyUI model phải được kiểm bằng runtime thực, không suy từ `config/models.toml`.
3. Tạo một shot motion có consent; kiểm graph, model hash, Comfy history, MP4 decode và SHA receipt; không blind retry.
4. Owner xem motion thật, continuity và nguồn âm thanh, quyền sử dụng.
5. Render episode với FFmpeg, phát lại và đối chiếu source/receipt SHA.
6. Chỉ tạo Publishing handoff khi Owner đã duyệt; private upload phải xác minh độc lập trong YouTube Studio.
7. Không xóa/migrate SQLite, workspace, model, secret, video trong cleanup Git.

Xem [Runtime](RUNTIME.md), [Motion](MOTION.md), [Production](PRODUCTION.md), [Publishing](PUBLISHING.md).
