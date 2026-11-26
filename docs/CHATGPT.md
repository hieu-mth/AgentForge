# ChatGPT Plan — kết nối và vận hành

AgentForge implements a Windows-only opt-in OAuth CLI and model profile. CI verifies the integration contract, not a live account. Only the Owner's local runtime may use the connection; no background scheduling, account rotation or proxy API is added. The user must authorize plan usage; the existing cloud consent and call cap remain in force. Do not use hosted/shared runtimes. Usage counts against the user's ChatGPT limits and credits.

## Local verification

1. Run `python -m pip install -e ".[media,chatgpt]"`.
2. Run `python -m agentforge.ai.chatgpt_auth login owner`, review consent in the browser.
3. Run `python -m agentforge.ai.chatgpt_auth models owner` and choose an actual slug.
4. Run `python -m agentforge.ai.chatgpt_auth probe owner --model YOUR_SLUG`.
5. Register a ChatGPT Plan profile in Model Hub with account reference owner and that slug. Assign general.text, film.storyboard, character.select or vision.qa in Model AI. In AI điều phối, enable cloud permission and explicitly approve cloud data transfer; verify a real storyboard and visual review.
6. Run `python -m agentforge.ai.chatgpt_auth logout owner` to clear local tokens; if remote revocation is not confirmed, disconnect in ChatGPT Settings.

DPAPI encrypted account records are outside the repository at ~/.agentforge/chatgpt.sqlite3. Account reference is configuration, not a token. No credentials in the UI or production receipts. CLI and Dashboard use the same local OAuth account store. Dashboard provides explicit Owner-initiated browser sign-in and disconnect; live OAuth and inference are not certified by CI. The ID token must verify against official JWKS. The Responses endpoint requires store=false, stream=true; incomplete streams fail, quota failures do not fall back. No model is hardcoded. No real account has been used in CI.

Official docs: https://developers.openai.com/siwc/token-sharing-open-source/sign-in ; https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference ; https://openai.com/policies/sign-in-with-chatgpt-terms/ .

## Dashboard

Khởi động backend bằng `--allow-external-tools`, đăng nhập Owner, vào Model AI → đăng ký model Cloud → ChatGPT Plan. Chọn mã tài khoản, bấm Liên kết ChatGPT (trình duyệt OpenAI), sau đó chọn model từ danh sách. Nếu đã đăng nhập bằng CLI, chỉ cần Lấy danh sách model. Nút Ngắt kết nối yêu cầu xác nhận và xóa credential local; không tự xóa các profile. Catalog không trả email, token hoặc secret về Dashboard. OAuth và inference thật vẫn cần Owner nghiệm thu, CI chỉ mock giao thức/provider.
