# UI-1A — Core Reliability

## A. Baseline và nguyên nhân

Ngày 11/11/2026. Branch `fix/dashboard-ui-1a-core-reliability`, tạo từ `main`/`f160a64c67c070f6fe3e1811d1c1c974c4d6633c`; working tree ban đầu sạch. Đã đọc audit, trace source và đối chiếu evidence fixture đúng baseline trước khi sửa. Không mặc định mọi nhận xét audit là runtime PASS.

| Finding | Nguyên nhân được xác minh |
|---|---|
| AF-UI-001 | Workspace đếm UTF-16, backend đếm code point; prompt tối đa 6.000 ký tự nhưng serialized Goal inputs/plan tối đa 8.192 byte. V5 lặp brief, S1 task request cũng có cap 8.192 byte. HTTP cap thực là 65.536; thông báo cũ ghi sai 8.192. |
| AF-UI-003 | Promise.all của Projects chỉ setState khi cả ba GET thành công; spinner thay cả màn hình và che retry khi một API lỗi. |
| AF-UI-004 | Bootstrap lỗi chỉ có spinner/Alert đóng được; không có retry GET. |
| AF-UI-005 | Chỉ App.authError biết 401; các GET của feature tự catch nên không đổi phiên toàn ứng dụng. |
| AF-UI-006 | Header chỉ reload bootstrap; resource feature giữ state riêng; mutate đã bootstrap-refresh rồi caller onReload gọi trùng; Settings effect reset cả form khi data đổi. |

## B. Files thay đổi

- `agentforge/core/brain_planner.py`: preflight budget của inputs, signed plan và payload S1 sau resolve binding, trước khi ghi Goal; không tăng cap.
- `agentforge/api/server.py`: sửa thông báo request-byte-limit theo MAX_BODY hiện hữu, không đổi limit/API gate.
- `dashboard/src/prompt_validation.js`, `features/Workspace.jsx`: code-point counter/UTF-8 bytes, validation ngắn/dài/control, giữ nguyên input, giải thích cap plan/V5.
- `dashboard/src/api.js`: thông báo timeout/offline, GET deadline 15 giây cả body, 401 event tập trung và session generation; không retry/timeout POST tự động; HTTP200 HTML không coi là kết nối thành công.
- `dashboard/src/App.jsx`: auth cleanup, bootstrap error/retry, coalesced bootstrap và refresh screen; feature mutate không refresh bootstrap trùng.
- `dashboard/src/use_resource.jsx`: resource lifecycle riêng, error/retry, latest-request-wins và guard unmount cho loader hiện hữu.
- `dashboard/src/refresh_scope.jsx`, `main.jsx`: các màn hình đang mount đăng ký GET loader, không remount form hoặc tải mọi feature.
- `features/Projects.jsx`: artifacts/health/jobs độc lập, giữ phần thành công, 403/503 rõ, retry đúng GET bị lỗi.
- `features/Models.jsx`: refresh registry/motion/episodes, giữ draft route/editor/form, mutation response không bị GET cũ ghi đè.
- `features/Management.jsx`, `MattressSales.jsx`, `Publishing.jsx`, `Retention.jsx`: đăng ký refresh đúng màn hình, chống GET cũ ghi đè; Settings giữ dirty fields.
- `tests/test_ui1a_reliability.py`: byte/code-point/serialized-plan boundaries, SHA/brief/task preservation và real localhost HTTP/CSRF budget fixture.
- `dashboard/tests/reliability.test.js`, `tests/browser-reliability.mjs`, `package.json`: API/validation/Edge adversarial regression, không dependency mới.
- `.github/workflows/ci.yml`: chạy Edge reliability suite trong CI hiện hữu.
- Tệp báo cáo này: bằng chứng và giới hạn nghiệm thu. Không chỉnh findings ngoài scope, navigation, schema, model config hoặc credential.

## C. Findings đã sửa

**AF-UI-001:** Giữ 6.000 code point và các cap 8 KiB hiện hữu. Không hứa mọi 6.000 ký tự đều vừa multi-step plan: UI nêu giới hạn kết hợp, backend kiểm chính xác trước ghi và trả `PLAN_UTF8_BUDGET` với cách rút gọn/chia việc. Không cắt brief. Kiểm cả payload đã thay binding bằng độ dài SHA thật để task history không nhận payload vượt cap. SHA serialization/schema giữ nguyên. Request lớn hợp lệ không gọi model tại planning.

**AF-UI-003:** Kho vẫn hiện khi image health/jobs lỗi. Resource có loading/error/empty/retry riêng; chỉ GET failed resource khi retry. Dữ liệu cũ nếu còn được đánh dấu bản tải trước; image submit bị khóa khi health đang lỗi/loading. Không có GPU call khi retry.

**AF-UI-004:** Bootstrap có terminal error, hướng dẫn backend local và nút “Thử kết nối lại”. Chỉ GET session/bootstrap, coalesce click nhanh. Offline, HTTP503 và response HTML sai loại đều không giả thành connected state.

**AF-UI-005:** Mọi API401 thông báo auth chung ngay từ headers, kể cả body lỗi/chậm. App xóa bootstrap/CSRF/Drawer/media state, đóng modal và unmount screen Owner; GET cũ thuộc generation đã hết hạn không trả dữ liệu lại UI. 403 không expire session. Không lưu token/code/CSRF vào localStorage. Prompt nháp trong memory không tự gửi lại.

**AF-UI-006:** Header refresh bootstrap và loader của màn hình đang mount; Models reload cả registry/motion/episodes. Form không remount; dirty Settings/route draft giữ nguyên. Coalesce refresh Header, sequence guard cho GET cũ/mới; resource mutation snapshot thắng GET cũ. Caller sở hữu đúng follow-up GET, bỏ bootstrap-refresh trùng của mutate. POST receipt vẫn trả về nếu refresh thất bại; không auto-replay POST.

## D. Trước và sau

| Tình huống | Trước | Sau |
|---|---|---|
| 5.912 ký tự tiếng Việt nhiều byte | Plan/record exceeds size limit chung chung | Báo cap UTF-8/plan 8 KiB, hướng dẫn chia nhỏ; không ghi Goal hay cắt input |
| Emoji | Counter UTF-16, input có thể bị browser cắt sớm | Counter code point theo Python, bytes riêng, không silent truncation |
| Artifacts200 + health503 | Không thấy kho, spinner vô hạn | Kho hiện; card health báo503/retry riêng |
| Artifacts403 | Spinner/toast, dễ nhầm | Permission error, không logout, có retry |
| API con401 | Shell/dữ liệu cũ còn hiện | Login, Owner screen/modal bị che hoặc unmount |
| Bootstrap503/offline →200 | Phải reload browser | Retry GET trong UI, phục hồi shell |
| Header tại Models | Registry cũ không reload | Registry/motion/episode GET; không gọi module khác |
| Refresh với form đang nhập | Settings overwrite draft | Dirty form/route draft được giữ |
| GET cũ tới sau GET mới | Có thể overwrite | Sequence/session guards bỏ kết quả cũ |
| POST commit rồi refresh503 | Receipt helper có bảo vệ, caller có GET trùng | Giữ bảo vệ, đúng một POST; giảm GET trùng |

## E. Kiểm thử và review đối kháng

Lệnh tái lập với dependencies hiện có:

```powershell
node --test --test-isolation=none dashboard/tests/*.test.js
.\.venv\Scripts\python.exe -B -m unittest tests.test_ui1a_reliability tests.test_prompt_intake tests.test_wave3_core_reliability tests.test_m3_api_boundaries -q
npm.cmd run build --prefix dashboard
npm.cmd run test:browser --prefix dashboard
npm.cmd run test:reliability --prefix dashboard
.\.venv\Scripts\python.exe -B scripts/check_source_hygiene.py
.\.venv\Scripts\python.exe -B scripts/check_docs.py
git diff --check
```

Full suite dùng `unittest discover -s tests` với `AGENTFORGE_DEVELOPER_MAX_TOKENS=''` **chỉ trong process test**. Lượt đầu 1.039 bài có một failure: test default8192 gặp12288 vì dotenv local nạp vào môi trường process. Giữ log lỗi, không sửa .env/model policy và không skip test. Lượt môi trường cô lập đạt1.039/1.039; lượt cuối có thêm HTTP fixture đạt **1.040/1.040, không skip**. Không suy ra lỗi sản phẩm từ cấu hình test kế thừa.

JavaScript suite đạt32/32 ở lượt sau review. Python target HTTP/prompt/auth/reliability đạt30/30. Production build và browser smoke có sẵn đạt. Edge reliability có17 tình huống với assertions: initial503/recovery; offline/recovery; GET timeout terminal; artifact200/health+jobs503; retry chỉ endpoint lỗi;403;401 ở7 screens; Models Header và draft route; dirty Settings; rapid refresh coalesce; GET cũ tới sau; committed POST/failed GET đúng1 POST; Unicode không cắt.

Vòng review sau implementation trace lại đường GET/mutation/auth, không chỉ dựa test mới. Đã phát hiện và xử lý thêm:

- GET deadline phải bao cả stalled JSON body; 401 expire ngay headers, không đợi parse body.
- HTTP200 HTML fallback phải thành API error, không mở shell giả.
- Model mutation response phải invalidate GET đang chờ; reload không set snapshot cũ lần thứ hai.
- Các screen loader ngoài Projects/Models cũng cần guard sequence/unmount khi đăng ký Header refresh.
- Settings setFieldsValue có thể đánh dấu touched; chỉ đánh dấu pristine sau hydrate server, không overwrite dirty form.
- Browser race test đầu chọn nhầm Header thay card refresh, nên chờ coalesced request rồi timeout; sửa selector, giữ log lần lỗi. Không sửa production để chiều test.

Evidence local đặt tại TEMP/agentforge-ui1a và các TEMP/agentforge-ui1a-browser-*; screenshots đều synthetic. Browser/API mock không gọi backend Owner, provider, GPU hoặc gửi thông báo thật. Browser smoke cũ tạo lại ảnh phase1; ảnh đó được restore, không nằm trong diff UI-1A.

## F. Compatibility và bảo mật

- Không DB/schema migration, tăng byte/model/process budgets hoặc đổi template/plan/SHA serialization. Goal cũ vẫn qua verify như trước.
- Không đổi permission IDs, grants, consent, CSRF, Host/Origin, loopback-only bind, execution gate, no-overwrite hoặc idempotency keys.
- API client chỉ phát read-only auth event, không tự login/POST/replay. POST mất kết nối báo kết quả chưa xác định và yêu cầu kiểm lịch sử trước gửi lại.
- GET có deadline/retry thủ công; POST tool dài không bị client tự timeout rồi khuyến khích retry.
- Registry refresh chỉ screen đang mount; không framework/state library mới.
- Rollback bằng revert commit và rebuild Dashboard, không cần rollback dữ liệu vì schema/cấu hình không đổi.

## G. Rủi ro và phần chưa thử

- NOT TESTED: mã Owner thật, model local/cloud inference, GPU, Docker/source AI runtime, thông báo thật, dữ liệu khách thật hoặc production deployment.
- Giới hạn8KiB vẫn có chủ ý; brief rất dài/V5 vẫn phải rút gọn/chia nhỏ. Sửa bằng validation/hướng dẫn chứ không nới ngân sách tùy tiện.
- Header không tự replay mutation hoặc cập nhật mọi module không mount. Drawer chi tiết có read flow riêng; không mở rộng thành hệ thống live polling.
- API GET quá15giây sẽ báo timeout; backend có thể hoàn tất việc đọc sau khi client đã bỏ. Không suy từ timeout sang thất bại một POST.
- Các finding audit khác (attention/KPI/catalogue/saved website/version/contrast) không thuộc UI-1A và chưa được claim đã sửa.
- Chỉ merge sau required checks trên HEAD cuối PASS. Runtime fixture PASS không đồng nghĩa production-ready.

## H. Kết luận

UI-1A sửa năm finding trong phạm vi core reliability theo cách incremental, giữ giới hạn/SHA/security gates và hành vi local-first. Đủ điều kiện review qua PR khi gates đã đạt; không claim nghiệm thu model/GPU/nghiệp vụ thật. Trạng thái commit/PR/CI cuối được báo kèm liên kết PR.
