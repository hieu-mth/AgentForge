# Đợt 4 — AI & Product Quality (AF-AUD-005/006/007/010–016/018/019)

## Mục tiêu

Củng cố chất lượng sản phẩm đã tồn tại mà không tạo model, engine, service hoặc
workflow mới. Giữ nguyên local-first, quyền Owner, one-shot dispatch,
SHA-bound proposals, CSP preview và backward compatibility.

## Các thay đổi

| Finding | Phạm vi và điều kiện nghiệm thu |
| --- | --- |
| 005 | Ollama/cloud JSON response được đọc theo giới hạn byte trước parse; Ollama NDJSON giới hạn từng line, tổng wire, số event và text. Không log response bí mật. |
| 006 | Một invocation có budget monotonic từ trước khi mở HTTP qua toàn bộ quá trình đọc. Socket receive timeout được hạ theo thời gian còn lại khi có socket; no retries. Giới hạn hard real-time với DNS/system-level blocking chưa được chứng nhận. |
| 007 | Giới hạn preview bằng tổng budget output đã validation; vẫn sử dụng signed proposal, static QA và CSP sandbox, không thực thi website. |
| 010 | Prompt visual giữ subject, scene riêng và safety suffix, không cho topic dài xóa phần cảnh. |
| 011 | analytics.quality_check / growth.report công bố là rules/deterministic; không thêm model calls; đọc được legacy Owner override nhưng không còn áp dụng lên hai route đã retired. |
| 012 | POST hoàn tất trả receipt ngay cả khi refresh GET lỗi; báo Owner dữ liệu còn stale, tuyệt đối không tự POST lại. |
| 013 | Image Studio dùng HTTP fixed loopback với allowlist /models/checkpoints, /prompt, /history/UUID, /view PNG; không proxy, không follow redirect, byte budget vẫn được enforce. Model health GET cũng không proxy/redirect. |
| 014 | Theme/layout đã validation được giữ trong normalized copy cho compatibility renderer. |
| 015 | `python -m agentforge.workflow --help` gọi CLI main; prototype không thay thế Skill Runner. |
| 016 | Skill Engine doc phản ánh canonical features và compatibility aliases thay vì mô tả migration còn dở. |
| 018 | Token text/CTA dark-light trong Dashboard/NovaMart có contrast tốt hơn, không redesign. |
| 019 | Modal detail/cart NovaMart nhận focus, giữ keyboard Tab bên trong, background inert, Escape đóng và trả focus trigger. |

## Gates

- `python -m unittest discover -s tests -v` trên Windows CI, gồm
  `tests/test_wave4_ai_product_quality.py` và large website HTTP preview.
- Dashboard Node tests gồm `action-receipt.test.js`.
- NovaMart Node contrast tests và Edge smoke có keyboard focus lifecycle.
- Dashboard/NovaMart build, wheel, PowerShell và Windows acceptance.
- Không dùng API/model trả phí, GPU hoặc dữ liệu Owner thật.

## Giới hạn trung thực

- No production AI/GPU/Docker certification. Socket timeout vẫn có giới hạn
  nếu DNS, TLS hoặc OS không cung cấp socket có thể điều chỉnh; monotonic guard
  chặn tiếp tục xử lý khi quá hạn, không phải preempt mọi system call.
- Accessibility chỉ được nghiệm thu trong các thành phần/test nêu trên,
  không phải chứng nhận WCAG toàn bộ dashboard hoặc ứng dụng.
- Legacy Model Hub entries được giữ ở trạng thái inert để tránh làm hỏng
  state và revision; Owner có thể rà soát/rollback theo workflow đã có.
- Preview lớn là nội dung đã giới hạn và bảo vệ trong iframe sandbox, không
  có quyền triển khai hoặc xuất bản tự động.
