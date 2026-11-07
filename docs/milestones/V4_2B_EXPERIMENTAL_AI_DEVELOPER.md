# V4.2b — Experimental AI Developer (explicit opt-in)

The stable webapp.create workflow remains a data-driven marketplace scaffold.
This separate webapp.develop mode lets a selected model propose **original**
React component code, local state and CSS through a strict allowlisted JSON
source contract, with fixed trusted Vite/React dependencies and entrypoint.

## How to opt in

Type an explicit AI Developer/React tùy biến request in Giao việc, for example:

"AI Developer: Tạo web app React tùy biến kiểu sàn mua sắm. Có tìm kiếm,
lọc danh mục, giỏ hàng tăng giảm số lượng, trang chi tiết dạng modal, dữ liệu
demo, mobile-first. Hãy viết component và state thực sự."

The Owner must approve SHA of the Goal and model call. The output remains an
immutable proposal. The same authenticated source review UI can show all
files, but **there is no automatic JS preview or native execution**.
The model's source is untrusted, even when it passes the static checks.

## Safety and QA

- Allowlisted paths only: src/App.jsx, src/styles.css and a small set of
  local components/data modules; no model-selected package.json, Vite config,
  shell scripts or dependencies.
- Reject remote URLs, package imports other than React, fetch/network APIs,
  eval, raw embedded HTML/script and dangerous DOM injection patterns.
- This screening is heuristic and must never be mistaken for a security proof.
- Owner review requires exact proposal SHA. Applying only writes source.
- Optional webapp.qa runs npm unit contract test and Vite build in Docker
  with no network, read-only source and separately approved process.run.
- Functional interaction QA and safe interactive previews of arbitrary AI
  source are not yet established. A successful build does not mean the app
  meets the requested features. Run only after explicit Owner review.
- The existing marketplace revision flow supports structured data; advanced
  code revisions will require a separate dedicated source-aware patch skill.

Never silently change the stable marketplace route into experimental code
generation. Owner must select advanced mode in the prompt.
