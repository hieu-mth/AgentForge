# AgentForge V3.3 — Compact owner navigation

This is a **navigation-only UI change** during the V3.3 owner review. It does not open a new AI milestone or change server permission gates.

## What changed

The React sidebar now contains exactly six owner-level destinations:

| Sidebar | Context tabs |
| --- | --- |
| **Giao việc** | Prompt-first workspace |
| **Tổng quan** | Company overview |
| **Dự án & Thành phẩm** | Websites, Kho thành phẩm & Ảnh AI, Duyệt AI & Video, Sao lưu & Cleanup |
| **Kinh doanh** | Growth & Revenue, Finance, Channels, Intelligence |
| **Đội ngũ AI** | Team & Roles, Kế hoạch & Duyệt, Task History |
| **Cài đặt** | Cấu hình, Lịch chạy, Vận hành, Owner Memory |

All **17 prior screens remain available**. The sidebar and tab structure are declared only once in `ui/dashboard/src/navigation.js`; React's `App.jsx` renders them without duplicating route lists. Every previously used leaf ID also has a durable URL fragment (example: `/dashboard/#/websites` or `/dashboard/#/tasks`) which survives reload and browser back/forward.

The change does **not** remove Goal SHA review, task audit, media review, ComfyUI controls or quarantine permissions. The same React feature components and Python API actions still run as before.

## Testing

`npm run test:navigation` confirms six groups, full one-to-one coverage of 17 screens, valid defaults, safe fallbacks and deep links. Windows CI runs it before the React production build and existing Python/PowerShell regression suite.

## Owner acceptance

1. Update main and rebuild `ui/dashboard`: `npm.cmd install` then `npm.cmd run build`.
2. Restart the local Python Control Center and open `http://127.0.0.1:8780/dashboard/`.
3. Verify six sidebar items, and switch tabs in Dự án, Kinh doanh, Đội ngũ AI and Cài đặt.
4. Refresh a deep link such as `#/retention` and confirm it remains on Backups & Cleanup.
5. Confirm old S1/S4 approval, image preview and file inventory continue to work.

The legacy dashboard at `/` remains accessible while reviewing the updated React UI.
