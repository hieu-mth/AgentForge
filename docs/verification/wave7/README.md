# Wave 7 — Product QA & Export

**Trạng thái:** CODE/Windows CI CONTRACT TESTS, Owner Docker runtime và generated React functional QA: UNVERIFIED.

## QA được Owner duyệt

- Luồng build-only V4.2 (`webapp.qa`) vẫn giữ nguyên. Wave 7 thêm `webapp.browser_qa`: 0 model calls, 1 external process.run riêng được duyệt theo SHA Goal.
- Owner phải cài Docker Desktop Linux và build browser image riêng, pin ID dạng sha256:<64 hex> trong AGENTFORGE_BROWSER_QA_IMAGE. Hướng dẫn từng bước ở [sandbox/webapp/README.md](../../../sandbox/webapp/README.md). Không tự download image/model, install dependencies hoặc chạy mã AI trên máy host.
- Trusted `browser_runner.mjs` chạy trong image Node+Chromium đã chuẩn bị. Backend chỉ truyền signed source vào bind mount read-only, tmpfs container; Docker flags: --pull never, --network none, readonly root, cap-drop ALL, UID 10001, giới hạn tài nguyên và thời gian.
- Browser test chạy node contracts, Vite build, preview loopback trong container, Playwright smoke: main/body, button click, desktop/mobile 375px overflow, JS pageerror/console errors và blocked external requests.
- Report là PASS_SMOKE_ONLY/FAIL với mã lỗi hữu hạn, source proposal SHA, PNG desktop/mobile và SHA report; lưu ở workspace/webapp-browser-qa/<report-id>. Không phản ánh đầy đủ nghiệp vụ, security, accessibility, performance hoặc deployment.
- Không tự động sửa source sau QA thất bại. Owner phải chủ động mở revision mới để cấp quyền gọi model.

## Export

Owner phải đọc GET /api/webapps/{id} để session ghi exact SHA. GET /api/webapps/{id}/export trả ZIP cùng X-Archive-SHA256, X-Source-SHA256. ZIP chỉ gồm source proposal files allowlisted, ZIP deterministic, manifest agentforge-export-manifest.json với SHA256 từng file và flags build/browser/deploy=false. Không có .env, node_modules hoặc generated runtime ngoài proposal. `verify_zip()` so byte-for-byte với nguồn verified local.

## Acceptance gates

CI dùng mock Docker và HTTP session thật trên loopback để kiểm tra permission, image pin, flags, reproducible export, integrity và screenshot hashes; node --check trusted runner; Dashboard build. Không có browser Docker thực chạy trong CI Windows.

Owner PC: tạo app React, sửa vài lần, duyệt webapp.browser_qa, đọc report PNG desktop/mobile, tự thử search/cart/modal/mobile, export ZIP và đối chiếu SHA. Không gán PASS product chỉ vì PASS_SMOKE_ONLY. Cẩn trọng khi dùng Docker image/node:22-bookworm-slim chưa pin upstream digest trong Dockerfile — kiểm tra supply chain thủ công.
