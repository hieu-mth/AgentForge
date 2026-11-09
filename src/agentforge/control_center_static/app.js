/* AgentForge Control Center V1 — no libraries, no CDN, no client storage.
   The browser never determines permissions. Server-side owner gates are final. */
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v === null || v === undefined ? "—" : v)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
const state = {csrf:null, data:null, view:"workspace", goal:null, task:null, memory:null, proposal:null, ops:null, inspectedDraft:null, inspectedVideo:null, artifacts:null, modelHealth:null, imageHealth:null, imageJobs:null, previewDevice:"desktop"};
const viewNames = {workspace:"Giao việc",team:"Team & Roles",channels:"Channels",finance:"Finance",settings:"Settings",artifacts:"Projects & Files",overview:"Tổng quan",goals:"Goals & Phê duyệt",tasks:"Task History",
 skills:"AI Workforce",websites:"Websites",analytics:"Intelligence",growth:"Growth & Revenue",
 schedules:"Schedules",integrations:"Integrations",memory:"Owner Memory"};
function notice(message,bad=false){
 const node=document.createElement("div");
 node.className="toast"+(bad?" error":"");node.textContent=String(message);
 $("toast-host").append(node);setTimeout(()=>node.remove(),6000);
}
async function api(path,method="GET",body=null){
 const opts={method,credentials:"same-origin",headers:{}};
 if(method!=="GET"){
   opts.headers["Content-Type"]="application/json";
   if(state.csrf)opts.headers["X-CSRF-Token"]=state.csrf;
   opts.body=JSON.stringify(body||{});
 }
 const response=await fetch(path,opts);
 const text=await response.text();
 let value;
 try{value=JSON.parse(text);}catch{throw Error("Invalid local API response");}
 if(!response.ok){
   const error=new Error(value.message||value.error||("HTTP "+response.status));
   error.status=response.status;throw error;
 }
 return value;
}
function showLogin(){
 $("login").hidden=false;$("shell").hidden=true;$("owner-code").value="";
 $("login-feedback").textContent="";state.csrf=null;
}
async function start(){
 try{
   const data=await api("/api/bootstrap");
   state.data=data;
   const session=await api("/api/session");
   state.csrf=session.csrf;showShell();
 }catch(err){
   if(err.status!==401)notice(err.message,true);
   showLogin();
 }
}
function showShell(){
 $("login").hidden=true;$("shell").hidden=false;
 render();
}
async function refresh(){
 try{state.data=await api("/api/bootstrap");render();}
 catch(err){if(err.status===401)showLogin();else notice(err.message,true);}
}
function badge(status){
 const s=String(status||"UNKNOWN");
 const color=s==="ACCEPTED"||s==="VALID"||s==="ACTIVE"?"success":
 ["WAITING_APPROVAL","REVIEW_REQUIRED","PLANNED","APPROVED","READY_FOR_OWNER_UPLOAD"].includes(s)?"warning":
 ["FAILED","INTERRUPTED"].includes(s)?"danger":
 s==="RUNNING"?"blue":"muted";
 return '<span class="pill pill-'+color+'">'+esc(s==='SUCCEEDED'?'Đã thực thi xong':s)+'</span>';
}
function header(eyebrow,title,subtitle,actions=""){
 return '<div class="page-header"><div><div class="eyebrow">'+esc(eyebrow)+
 '</div><h1>'+esc(title)+'</h1><p>'+esc(subtitle)+'</p></div>'+actions+'</div>';
}
function card(title,content,extra=""){
 return '<section class="card"><div class="section-head"><h2>'+esc(title)+'</h2>'+
 extra+'</div>'+content+'</section>';
}
function empty(text){
 return '<div class="empty-state"><strong>Chưa có dữ liệu</strong>'+esc(text)+'</div>';
}
function table(columns,rows,emptyText="Chưa có bản ghi"){
 return '<div class="table-wrap"><table class="table"><thead><tr>'+
 columns.map(c=>'<th>'+esc(c)+'</th>').join("")+'</tr></thead><tbody>'+
 (rows.length?rows.join(""):'<tr><td colspan="'+columns.length+
 '" class="empty-cell">'+esc(emptyText)+'</td></tr>')+'</tbody></table></div>';
}
function fmt(v){return (typeof v==="number"?v.toLocaleString("vi-VN"):esc(v));}
function short(id){return esc(String(id||"").slice(0,12));}
function renderWorkspace(){
 const data=state.data;
 const recent=(data.goals||[]).slice(0,5).map(g=>
   '<div class="workspace-job"><div><strong>'+esc(g.title)+'</strong><small>'+esc(g.template)+'</small></div>'+
   badge(g.status)+(g.artifact_acceptance?' <span class="small muted">Sản phẩm: '+esc(g.artifact_acceptance.status)+'</span>':'')+' <button class="btn btn-small btn-outline" type="button" data-detail-goal="'+esc(g.goal_id)+'">Chi tiết</button></div>').join("");
 return '<div class="workspace-hero"><div class="eyebrow">YOUR AI COMPANY · LOCAL FIRST</div>'+
  '<h1>Hôm nay bạn muốn xây dựng điều gì?</h1>'+
  '<p>Chỉ cần mô tả mục tiêu. AgentForge chuyển yêu cầu thành kế hoạch để bạn duyệt trước khi chạy AI.</p>'+
  '<p class="small muted">Policy: '+esc(
    (data.workspace_policy?.max_estimated_model_calls??1))+
    ' lượt model/Goal tối đa · Website '+(data.workspace_policy?.website_enabled?"Bật":"Tắt")+
    ' · Storyboard '+(data.workspace_policy?.storyboard_enabled?"Bật":"Tắt")+'</p>'+
  '<form id="workspace-request-form" class="workspace-prompt">'+
  '<label for="workspace-prompt">Yêu cầu công việc</label>'+
  '<textarea id="workspace-prompt" rows="5" maxlength="600" required minlength="20" placeholder="Ví dụ: Tạo landing page nệm cao cấp cho ba tôi, có hình minh họa đẹp, mobile-first, hotline 0879547988..."></textarea>'+
  '<div class="workspace-prompt-footer"><span>Không gọi AI khi lập kế hoạch · Mọi bước thực thi cần được duyệt</span>'+
  '<button type="submit" class="btn btn-primary">Tạo kế hoạch →</button></div></form></div>'+
  '<div class="workspace-health">'+
  '<span class="small muted">Website Builder: '+esc(state.modelHealth?
    (state.modelHealth.status==="READY"?"Ollama đã cài & phản hồi":state.modelHealth.status):
    "Chưa kiểm tra khả năng kết nối model")+'</span>'+
  '<button type="button" class="btn btn-outline btn-small" data-check-model-health="1">Kiểm tra Ollama (không sinh nội dung)</button>'+
  '</div>'+ 
  '<div class="workspace-columns"><section class="card"><div class="section-head"><h2>Việc gần đây</h2>'+
  '<button class="section-link" data-view="goals">Xem tất cả</button></div>'+
  (recent||'<p class="muted">Chưa có kế hoạch. Hãy mô tả việc cần làm ở trên.</p>')+'</section>'+
  '<section class="card"><h2>Kiểm soát rõ ràng</h2>'+
  '<p class="muted">Chỉ hỗ trợ yêu cầu website/landing page và storyboard trong luồng prompt đầu tiên. Các công việc khác vẫn có thể thao tác bằng module hiện có.</p>'+
  '<div class="workspace-insight">Kế hoạch không tự chạy, không tự đăng, không cấp quyền ngân sách.</div>'+
  '<button class="btn btn-outline" type="button" data-view="overview">Xem hệ thống & báo cáo</button></section></div>'+
  (state.goal?'<div class="section">'+card("Kế hoạch đang xử lý",renderGoalDetail())+'</div>':'');
}
function renderTeam(){
 const rows=(state.data.skills||[]).map(x=>'<tr><td>'+esc(x.worker)+'</td><td>'+esc(x.id)+'</td><td>'+badge(x.mode)+'</td></tr>');
 return header("AI WORKFORCE","Team & Roles","Các AI role và skill đang được khai báo; không có quyền tự tạo role hoặc tự nâng quyền từ prompt.")+
  '<div class="callout">Quyền thực thi được kiểm tra bằng S1 Skill Contract và phê duyệt owner. Role là worker profile, không phải nhân viên pháp lý hoặc tác nhân có ngân sách độc lập.</div>'+
  '<div class="section">'+card("Danh mục role & skills",table(["WORKER","SKILL","EXECUTION"],rows))+'</div>';
}
function renderChannels(){
 const rows=(state.data.connectors||[]).map(x=>
  '<div class="channel-status"><div><strong>'+esc(x.name)+'</strong>'+
  '<small>'+(x.authenticated?'Đã có xác thực':'Chưa kết nối OAuth/API chính thức')+'</small></div>'+badge(x.status)+'</div>').join("");
 return header("EXTERNAL ACCOUNTS","Channels","Tình trạng kênh thật. Không hiển thị CONNECTED nếu thiếu chứng cứ xác thực.")+
  '<div class="callout warning">YouTube/TikTok hiện chỉ hỗ trợ chuẩn bị nội dung và owner upload thủ công. Không có nút kết nối giả và không lưu mật khẩu trong SQLite.</div>'+
  card("Các kênh",rows||empty("Chưa có kênh được cấu hình."));
}
function renderFinance(){
 const c=state.data.company_v2||{},b=c.business||{},ap=c.autopilot||{};
 return header("OWNER FINANCE","Finance","Tách số liệu ghi nhận thủ công khỏi doanh thu/chi phí đã được bên cung cấp xác minh.")+
 '<div class="finance-cards">'+
  card("Giới hạn model theo lượt",'<div class="finance-value">'+fmt(ap.daily_call_cap??0)+'</div><p class="small muted">Lượt ước tính mỗi ngày UTC, không phải ngân sách VND.</p>')+
  card("Lượt model đã dùng hôm nay",'<div class="finance-value">'+fmt(ap.estimated_calls_used_today??0)+'</div><p class="small muted">Chưa đối soát với hóa đơn provider.</p>')+
  card("Lợi nhuận đã xác minh",'<div class="finance-value">Chưa xác minh</div><p class="small muted">Không có kết nối ngân hàng hay đối soát hoa hồng.</p>')+
  card("Chiến dịch thật",'<div class="finance-value">'+fmt(b.real_campaigns??0)+'</div><p class="small muted">Các số liệu owner nhập không được tự coi là doanh thu thật.</p>')+
 '</div><div class="section">'+card("Quy tắc tài chính",'<p>Không tự chi tiền, mua quảng cáo hoặc thực hiện thanh toán. Hạn mức provider thực tế chưa thể xác minh bằng AgentForge hiện tại.</p>'+
 '<button class="btn btn-outline" type="button" data-view="growth">Xem sổ chiến dịch owner →</button>')+'</div>';
}
function renderSettings(){
 const ap=state.data.autopilot_policy||{enabled:false,daily_cap:0};
 const wp=state.data.workspace_policy||{max_estimated_model_calls:1,website_enabled:true,storyboard_enabled:true};
 return header("OWNER GOVERNANCE","Settings","Cấu hình delegation và kiểm soát chi phí ước tính; quyền bên ngoài vẫn cần phê duyệt theo tác vụ.")+
 '<div class="settings-panel">'+card("Autopilot · hạn mức lượt model",
 '<p class="muted">Tắt bật delegation cho hàng đợi V1.3. Không tự gọi model, không kiểm soát chi phí hóa đơn.</p>'+
 '<div class="form-field"><label for="ap-policy-cap">Lượt dự kiến mỗi ngày UTC (0–10)</label>'+
 '<input id="ap-policy-cap" type="number" min="0" max="10" step="1" value="'+esc(ap.daily_cap)+'"></div>'+
 '<div class="form-field"><label for="ap-policy-enabled">Delegation</label>'+
 '<select id="ap-policy-enabled"><option value="false" '+(!ap.enabled?'selected':'')+'>Tắt</option>'+
 '<option value="true" '+(ap.enabled?'selected':'')+'>Bật</option></select></div>'+
 '<div class="form-actions"><button class="btn btn-primary" type="button" data-autopilot-configure="1">Lưu chính sách</button></div>')+
 card("Prompt Workspace · Role & lượt model",
 '<p class="muted">Giới hạn tạo kế hoạch mới từ ô prompt; không thay thế quota Autopilot, quyền S1 hoặc hóa đơn provider.</p>'+
 '<div class="form-field"><label for="wp-model-cap">Số lượt model ước tính tối đa mỗi Goal (0–3)</label>'+
 '<input id="wp-model-cap" type="number" min="0" max="3" step="1" value="'+esc(wp.max_estimated_model_calls)+'"></div>'+
 '<label class="check-row"><input id="wp-website" type="checkbox" '+(wp.website_enabled?"checked":"")+
 '>Cho phép role Website Builder nhận yêu cầu mới</label>'+
 '<label class="check-row"><input id="wp-storyboard" type="checkbox" '+(wp.storyboard_enabled?"checked":"")+
 '>Cho phép role Storyboard nhận yêu cầu mới</label>'+
 '<p class="small muted">Role bật/tắt ở đây chỉ áp dụng cho luồng prompt. Không nâng quyền model/process/network.</p>'+
 '<div class="form-actions"><button class="btn btn-outline" type="button" data-workspace-policy-save="1">Lưu hạn mức & role</button></div>')+
 card("Local-first & Data Safety",
 '<p>SQLite và workspace vẫn ở máy bạn. Dùng quy trình backup được kiểm chứng trước khi cleanup dữ liệu.</p>'+
 '<p class="small muted">Không nhập mật khẩu, số tài khoản hoặc dữ liệu khách vào Prompt hay Task History.</p>'+
 '<button class="btn btn-outline" type="button" data-view="integrations">Xem System Health →</button>')+'</div>';
}
function renderOverview(){
 const d=state.data,s=d.stats;
 const metrics=[
 ["Tổng nhiệm vụ",s.tasks,"S1 · Task History","≡"],
 ["Đã thực thi xong",s.succeeded,"Chưa phải nghiệm thu sản phẩm","✓"],
 ["Cần phê duyệt",s.waiting_approval,"Chờ owner quyết định","◎"],
 ["AI Skills",s.skills,"Registry đã đăng ký","◇"]
 ];
 const tiles=metrics.map(([label,value,foot,symbol])=>
 '<div class="metric"><div class="metric-label">'+esc(label)+
 '<span class="metric-symbol">'+symbol+'</span></div><div class="metric-value">'+fmt(value)+
 '</div><div class="metric-foot">'+esc(foot)+'</div></div>').join("");
 const goals=d.goals.slice(0,5).map(g=>
 '<div class="goal-tile"><span class="goal-mark">◎</span><div class="goal-main"><strong>'+
 esc(g.title)+'</strong><small>'+esc(g.template)+' · '+short(g.goal_id)+
 '</small></div>'+badge(g.status)+(g.artifact_acceptance?' <span class="small muted">Sản phẩm: '+esc(g.artifact_acceptance.status)+'</span>':'')+'<button type="button" class="btn btn-small btn-outline" data-detail-goal="'+
 esc(g.goal_id)+'">Xem</button></div>').join("");
 const recent=d.tasks.slice(0,6).map(t=>
 '<tr><td><button class="link-button" data-detail-task="'+esc(t.task_id)+'">'+
 short(t.task_id)+'</button></td><td>'+esc(t.skill_id)+'</td><td>'+badge(t.status)+
 '</td><td>'+esc(String(t.updated_at||"").replace("T"," ").slice(0,19))+'</td></tr>');
 const operations=d.operations||{mode:"ACTIVE"};
 const paused=operations.mode!=="ACTIVE";
 const h=d.daemon;
 const engine=h.fresh?'DAEMON ACTIVE':'MANUAL / OFFLINE';
 const attention=(d.attention||[]).map(x=>{
  const where=x.kind==="goal"?"data-detail-goal":x.kind==="task"?"data-detail-task":"data-view";
  const target=x.kind==="schedules"?"schedules":x.id;
  return '<div class="goal-tile"><div class="goal-main"><strong>'+esc(x.title)+
  '</strong><small>'+esc(x.priority)+' · '+esc(x.status)+'</small></div>'+
  '<button type="button" class="btn btn-small btn-outline" '+where+'="'+esc(target)+
  '">Xem</button></div>';
 }).join("");
 const reviewData=d.autopilot_reviews||{pending_count:0,items:[],business_context:null};
 const reviewRows=(reviewData.items||[]).filter(r=>r.decision==="PENDING").slice(0,8).map(r=>
  '<tr><td>'+short(r.job_id)+'</td><td>'+esc(r.skill_id)+'</td>'+
  '<td>'+badge(r.quality)+'</td><td>'+esc((r.reasons||[]).join(", "))+'</td>'+
  '<td><button class="link-button" data-detail-task="'+esc(r.task_id)+'">Xem task</button> '+
  '<button class="btn btn-small btn-outline" data-draft-inspect="'+esc(r.job_id)+'">Kiểm tra & duyệt</button></td></tr>');
 const reviewCard=card("AI Draft Review Queue · "+fmt(reviewData.pending_count)+" chờ duyệt",
  '<p class="small muted">Business: '+esc(reviewData.business_context?reviewData.business_context.business:"Chưa cấu hình")+
  '. PASS_HEURISTIC vẫn cần duyệt thủ công. Dùng CLI quality_v14 để quyết định theo output SHA; không tự đăng hay apply.</p>'+
  table(["JOB","SKILL","QUALITY","LÝ DO","NỘI DUNG"],reviewRows,"Chưa có bản nháp cần duyệt"));
 const ap=d.autopilot_policy||{enabled:false,daily_cap:0};
 const company=d.company_v2||{};
 const apCard=card("V2 · Autopilot Owner Control",
  '<p class="small muted">Điều chỉnh hạn mức ước tính lượt model/UTC ngày. Bật delegation không tự tạo job và không chứng minh chi phí provider.</p>'+
  '<div class="form-field"><label for="ap-policy-cap">Giới hạn lượt model/ngày (0–10)</label>'+
  '<input id="ap-policy-cap" type="number" min="0" max="10" step="1" value="'+esc(ap.daily_cap)+'"></div>'+
  '<div class="form-field"><label for="ap-policy-enabled">Standing delegation</label>'+
  '<select id="ap-policy-enabled"><option value="false" '+(!ap.enabled?'selected':'')+'>Tắt</option>'+
  '<option value="true" '+(ap.enabled?'selected':'')+'>Bật</option></select></div>'+
  '<div class="form-actions"><button class="btn btn-outline" data-autopilot-configure="1">Áp dụng chính sách (xác nhận)</button></div>'+
  '<p class="small muted">Quy trình chạy model vẫn dùng CLI hoặc processor riêng; bảng này không kích hoạt model ngay.</p>');
 const healthV2=company.business||{};
 const companyCard=card("V2.0 · Business Operations Pilot",
  '<p class="small muted">MVP local-first, chưa xác nhận kinh doanh có lãi. Không sử dụng AI tự giao dịch hoặc tự đăng bài.</p>'+
  '<div class="stack"><div class="goal-tile"><strong>Chiến dịch thật: '+fmt(healthV2.real_campaigns||0)+'</strong>'+
  '<small>Khách tiềm năng do owner nhập: '+fmt(healthV2.owner_recorded_leads||0)+'</small></div>'+
  '<div class="goal-tile"><strong>MP4 đã owner duyệt: '+fmt(company.content?.owner_approved_local_videos||0)+'</strong>'+
  '<small>Bài đăng owner khai báo: '+fmt(healthV2.owner_attested_publications||0)+'</small></div>'+
  '<div class="goal-tile"><strong>Điều kiện chưa đạt</strong>'+
  '<small>'+esc((company.launch_blockers||[]).join(" · ")||"Chưa có blocker nội bộ")+'</small></div>'+
  '<div class="goal-tile"><strong>Việc cần làm tiếp</strong>'+
  '<small>'+esc((company.next_owner_actions||[]).join(" · "))+'</small></div></div>');
 const videoData=d.local_video||{pending_count:0,items:[]};
 const videoRows=(videoData.items||[]).slice(0,8).map(v=>
  '<tr><td>'+short(v.production_id)+'</td><td>'+short(v.run_id)+'</td>'+
  '<td>'+badge(v.status)+'</td><td>'+esc(v.quality||"—")+'</td>'+
  '<td>'+(v.status==="VIDEO_READY"?'<button class="btn btn-small btn-outline" data-video-inspect="'+esc(v.production_id)+'">Duyệt MP4</button>':'—')+'</td></tr>');
 const starterStoryboard={slug:"nem-ngu-edited",title:"Tư vấn chọn nệm ngủ",scenes:[
   {headline:"Chọn nệm ngủ thế nào?",caption:"Xem xét nhu cầu nghỉ ngơi và độ nâng đỡ của nệm.",duration_seconds:5},
   {headline:"Cần tư vấn chọn nệm?",caption:"Chia sẻ ngân sách và nhu cầu để được gợi ý phù hợp.",duration_seconds:5}
 ]};
 const editorCard=card("Storyboard Editor (local)",
  '<p class="small muted">Chỉnh sửa JSON bản nháp của owner. Chuẩn bị chỉ tạo PNG, WAV, SRT trên máy và không gọi AI/FFmpeg. Dùng slug mới mỗi lần; kiểm tra nội dung trước khi bấm.</p>'+
  '<div class="form-field"><label for="media-editor-json">Storyboard chỉnh sửa</label>'+
  '<textarea id="media-editor-json" rows="13" spellcheck="false">'+
  esc(JSON.stringify(starterStoryboard,null,2))+'</textarea></div>'+
  '<div class="form-actions"><button type="button" class="btn btn-primary" data-media-prepare="1">Tạo tài nguyên local (xác nhận)</button></div>'+
  '<p class="small muted">Muốn dựng MP4 và duyệt video, sử dụng CLI media_workflow_v15 và xem file trước khi phê duyệt. Không có tự động đăng bài.</p>');
 const videoCard=card("Local Video Production · "+fmt(videoData.pending_count)+" chờ xem video",
  '<p class="small muted">Storyboard chỉnh sửa → ảnh/phụ đề local → FFmpeg → VIDEO_PASS → owner duyệt. Video không tự xuất bản. Xem MP4 trong workspace/media/{run_id}/video.mp4; quyết định qua media_workflow_v15 CLI.</p>'+
  table(["PRODUCTION","RUN","TRẠNG THÁI","QA","OWNER"],videoRows,"Chưa có video production"));
 const safety='<div class="callout '+(paused?'warning':'')+'">'+
   '<strong>Operations: '+esc(operations.mode)+'</strong> — '+
   esc(paused?'Đã dừng phân phối nhiệm vụ mới. Việc đang chạy có thể kết thúc hoặc bị gián đoạn.':
       'Có thể chạy nhiệm vụ theo quyền đã cấp. Tạm dừng khi cần kiểm tra sự cố.')+
   '<div class="form-actions"><button class="btn btn-outline" type="button" data-ops-mode="'+
   (paused?'ACTIVE':'PAUSED')+'">'+(paused?'Tiếp tục vận hành':'Tạm dừng hệ thống')+
   '</button></div></div>';
 const health=card("Trạng thái vận hành",
  '<div class="stack"><div class="goal-tile"><span class="goal-mark">◷</span>'+
  '<div class="goal-main"><strong>Scheduler</strong><small>'+
  esc(h.fresh?'Heartbeat gần đây':'Chưa có daemon đang hoạt động được xác minh')+
  '</small></div>'+badge(engine)+'</div>'+
  '<div class="goal-tile"><span class="goal-mark">⎔</span><div class="goal-main">'+
  '<strong>Kênh phân phối</strong><small>YouTube · TikTok</small></div>'+
  badge("MANUAL_ONLY")+'</div>'+
  '<div class="callout">Mọi chỉ số revenue từ S3/S5 đều do owner nhập hoặc là DEMO. Không có doanh thu được đối soát độc lập.</div></div>');
 return header("OPERATIONS / OVERVIEW","Trung tâm điều hành",
  "Nắm toàn bộ công việc, tiến độ và quyết định của AgentForge ở một nơi.",
  '<button class="btn btn-primary" data-view="goals">+ Tạo mục tiêu</button>')+
 '<div class="hero"><div class="hero-content"><div class="eyebrow">LOCAL-FIRST AUTONOMY</div>'+
 '<h2>Điều hành theo mục tiêu.<br>Giữ quyền quyết định.</h2>'+
 '<p>Các workflow được điều phối bởi Company Brain. Mọi quyền ghi, gọi model, mở trình duyệt hoặc chạy công cụ đều qua cổng phê duyệt.</p>'+
 '</div><span class="hero-pill">● 24 skills · 5 MVP layers</span></div>'+
 '<div class="metrics">'+tiles+'</div>'+
 '<div class="section">'+safety+'</div>'+
 '<div class="grid-2 section">'+apCard+companyCard+'</div>'+
 '<div class="section">'+reviewCard+'</div>'+
 '<div class="section">'+videoCard+'</div>'+
 '<div class="section">'+editorCard+'</div>'+
 '<div class="section">'+card("Cần owner xử lý",
  attention?'<div class="stack">'+attention+'</div>':
   '<p class="small muted">Chưa có Goal đang chờ phê duyệt hoặc sự cố cần xem xét.</p>')+'</div>'+
 '<div class="grid-2 section">'+card("Mục tiêu gần đây",
  '<div class="stack">'+(goals||empty("Tạo mục tiêu đầu tiên từ Goal Manager."))+'</div>',
  '<button class="section-link" data-view="goals">Xem tất cả →</button>')+
 health+'</div><div class="section">'+card("Hoạt động mới nhất",
 table(["TASK","SKILL / WORKFLOW","STATUS","UPDATED (UTC)"],recent),
 '<button class="section-link" data-view="tasks">Xem Task History →</button>')+'</div>';
}
function goalRows(){
 return state.data.goals.map(g=>
 '<tr><td><button type="button" class="link-button" data-detail-goal="'+esc(g.goal_id)+'">'+
 short(g.goal_id)+'</button></td><td>'+esc(g.title)+'</td><td>'+esc(g.template)+
 '</td><td>'+badge(g.status)+(g.artifact_acceptance?' <span class="small muted">Sản phẩm: '+esc(g.artifact_acceptance.status)+'</span>':'')+'</td><td>'+fmt(g.current_step)+'</td></tr>');
}
function renderGoals(){
 const templates=Object.keys(state.data.templates);
 const selected=templates.includes("campaign.review")?"campaign.review":templates[0];
 const templateOptions=templates.map(k=>'<option value="'+esc(k)+'"'+(k===selected?' selected':'')+'>'+esc(k)+'</option>').join("");
 const datasets=state.data.datasets||[];
 const defaultDataset=datasets.length?datasets[0].dataset:"";
 const options=datasets.map(d=>'<option value="'+esc(d.dataset)+'">'+esc(d.dataset)+
    (d.synthetic?' · DEMO':' · owner supplied')+'</option>').join("");
 const dataControl='<div class="form-field" id="goal-dataset-control"><label for="goal-dataset-pick">Dataset từ Intelligence</label>'+
  (datasets.length?'<select id="goal-dataset-pick">'+options+'</select>':
    '<p class="small muted">Chưa có dataset. Tạo/import dữ liệu tại Intelligence trước khi lập Goal phân tích.</p>')+'</div>';
 const form='<form id="goal-form"><div class="form-field"><label for="goal-title">Tên mục tiêu</label>'+
 '<input id="goal-title" required minlength="3" maxlength="160" value="Review campaign" /></div>'+
 '<div class="form-field"><label for="goal-template">Workflow có sẵn</label>'+
 '<select id="goal-template">'+templateOptions+'</select></div>'+dataControl+
 '<div class="form-field"><label for="goal-json">Đầu vào · JSON</label>'+
 '<textarea id="goal-json" rows="5" spellcheck="false">'+esc(JSON.stringify({dataset:defaultDataset},null,2))+'</textarea></div>'+
 '<div class="form-row"><div class="form-field"><label for="goal-model-cap">Max model calls (ước tính)</label>'+
 '<input id="goal-model-cap" type="number" min="0" max="3" value="0"></div>'+
 '<div class="form-field"><label for="goal-process-cap">Max external process runs</label>'+
 '<input id="goal-process-cap" type="number" min="0" max="3" value="0"></div></div>'+
 '<div class="callout">Đề xuất không tự thực thi. Bạn phải xem kế hoạch, đối chiếu SHA rồi duyệt. Các thao tác ghi hoặc external tiếp tục yêu cầu grant riêng.</div>'+
 '<div class="form-actions"><button type="button" class="btn btn-outline" data-preflight-goal>Kiểm tra dữ liệu</button>'+
 '<button type="submit" class="btn btn-primary">Tạo kế hoạch</button></div>'+
 '<p class="small muted" id="goal-preflight-status" role="status" aria-live="polite">Dữ liệu sẽ được kiểm tra lại trước khi duyệt/chạy.</p></form>';
 const details=state.goal?renderGoalDetail():'<div class="empty-state"><strong>Chọn một Goal</strong>Xem SHA, các bước thực thi và phê duyệt ngay tại đây.</div>';
 return header("COMPANY BRAIN","Goals & Phê duyệt",
  "Tạo mục tiêu có giới hạn, kiểm tra từng bước và chỉ cấp quyền khi cần.")+
 '<div class="split">'+card("Tạo mục tiêu",form)+
 card("Kế hoạch & quyền hạn",'<div id="goal-detail" class="details">'+details+'</div>')+
 '</div><div class="section">'+card("Danh sách mục tiêu",
 table(["GOAL ID","MỤC TIÊU","TEMPLATE","TRẠNG THÁI","BƯỚC"],goalRows()))+'</div>';
}
function renderGoalDetail(){
 const g=state.goal;
 if(!g)return "";
 const stepRows=(g.plan||[]).map((step,i)=>{
  const executed=(g.step_runs||[]).find(x=>x.step_index===i);
  const childTask=executed?.child_task_id?
   '<button type="button" class="btn btn-outline btn-small" data-detail-task="'+
    esc(executed.child_task_id)+'">Xem kết quả / lỗi</button>':"";
  return '<li class="step"><span class="step-num">'+(i+1)+'</span><div class="step-text"><strong>'+
   esc(step.skill_id)+'</strong><small>'+esc(step.worker_id)+' · '+
   esc((step.required_permissions||[]).join(", ")||"read_only")+
   '</small>'+childTask+'</div>'+badge(executed?executed.status:"NOT_STARTED")+'</li>';
 }).join("");
 const possible=g.status==="APPROVED"||g.status==="WAITING_APPROVAL";
 const action=g.status==="APPROVED"?"run":"resume";
 const grantChecks=["workspace.write","workspace.propose","model.invoke","network.search",
                    "network.read","browser.run","process.run"]
   .map(x=>'<label class="check-row"><input type="checkbox" name="grant" value="'+esc(x)+
   '"><span>'+esc(x)+'</span></label>').join("");
 const permissions=possible?
  '<div class="callout warning">Các quyền dưới đây chỉ áp dụng cho lần chạy này. Quyền external cần server khởi động với --allow-external-tools.</div>'+
  '<div class="permissions">'+grantChecks+'</div>'+
  '<div class="permissions">'+
  '<label class="check-row"><input type="checkbox" id="confirm-model">Cho phép gọi model</label>'+
  '<label class="check-row"><input type="checkbox" id="confirm-browser">Cho phép browser</label>'+
  '<label class="check-row"><input type="checkbox" id="confirm-process">Cho phép process/FFmpeg</label></div>'+
  '<div class="form-actions"><button class="btn btn-primary" data-'+action+'-goal="'+
  esc(g.goal_id)+'">'+(action==="run"?"Chạy kế hoạch":"Tiếp tục từ approval gate")+'</button></div>':"";
 const approve=g.status==="PLANNED"?
  '<div class="form-actions"><button class="btn btn-primary" data-approve-goal="'+
  esc(g.goal_id)+'">Duyệt SHA và mở quyền chạy</button></div>':"";
 return '<div class="detail-header"><div><h2>'+esc(g.title)+'</h2><div class="small muted">'+
 esc(g.template)+' · '+short(g.goal_id)+'</div></div>'+badge(g.status)+(g.artifact_acceptance?' <span class="small muted">Sản phẩm: '+esc(g.artifact_acceptance.status)+'</span>':'')+'</div>'+
 '<p class="small muted" style="margin-top:12px">SHA-256 kế hoạch (bắt buộc khớp)</p>'+
 '<div class="mono callout">'+esc(g.plan_sha256)+'</div>'+
 '<ol class="step-list">'+stepRows+'</ol>'+approve+permissions+
 '<details class="section"><summary class="small muted">Xem đầy đủ inputs và plan để kiểm tra</summary>'+
 '<pre class="code-box">'+esc(JSON.stringify({inputs:g.inputs,plan:g.plan},null,2))+'</pre></details>';
}
function renderResultReport(report){
 if(!report)return "";
 const human=v=>v===null?"Chưa xác minh":typeof v==="boolean"?(v?"Có":"Không"):
   typeof v==="number"?v.toLocaleString("vi-VN"):String(v);
 const rows=Object.entries(report.fields||{}).map(([key,value])=>
  '<tr><td>'+esc(key)+'</td><td>'+esc(human(value))+'</td></tr>');
 const metricRows=Object.entries(report.metrics||{}).map(([key,value])=>
  '<tr><td>'+esc(key)+'</td><td>'+esc(human(value))+'</td></tr>');
 const channels=(report.channels||[]).map(x=>
  '<tr><td>'+esc(x.name)+'</td><td>'+esc(JSON.stringify(x.metrics))+'</td></tr>');
 const signals=(report.signals||[]).map(x=>
  '<li>'+esc(JSON.stringify(x))+'</li>').join("");
 const notices=(report.notices||[]).map(x=>'<li>'+esc(x)+'</li>').join("");
 return '<section class="result-report section"><h3>Kết quả phân tích</h3>'+
  '<div class="callout warning">Dữ liệu import từ owner có thể chưa được xác minh. DEMO không phải doanh thu thật;'+
  ' kết quả phân tích không tự cấp quyền chi tiền.</div>'+
  (rows.length?table(["CHỈ SỐ / TRẠNG THÁI","GIÁ TRỊ"],rows):"")+
  (metricRows.length?'<h3>Hiệu quả tổng hợp</h3>'+table(["METRIC","VALUE"],metricRows):"")+
  (channels.length?'<h3>Theo kênh</h3>'+table(["CHANNEL","METRICS"],channels):"")+
  (signals?'<h3>Tín hiệu cần kiểm chứng</h3><ul class="report-list">'+signals+'</ul>':"")+
  (notices?'<h3>Hạn chế & cảnh báo</h3><ul class="report-list">'+notices+'</ul>':"")+
  '<p class="small muted">Số nguồn nhập: '+esc(report.source_count??"Chưa có")+
  ' · Doanh thu xác minh độc lập: Không</p></section>';
}
function renderTaskDetail(task){
 const events=(task.events||[]).map(x=>
  '<tr><td>'+esc(x.at)+'</td><td>'+esc(x.name)+'</td></tr>');
 return '<div class="detail-header"><h3 class="mono">'+esc(task.task_id)+'</h3>'+
  badge(task.status)+'</div>'+
  '<p class="small muted">Skill / workflow: '+esc(task.skill_id)+'</p>'+
  (task.error?'<div class="callout warning"><strong>Lỗi thực thi:</strong> '+
    esc(task.error)+'</div>':"")+
  '<div class="callout">Artifacts: '+esc((task.artifacts||[]).join(", ")||"None")+'</div>'+
  renderResultReport(task.report)+
  (task.web_proposal?'<div class="form-actions"><button class="btn btn-primary" data-view-proposal="'+
    esc(task.web_proposal.proposal_id)+'">Xem và duyệt website proposal</button></div>':"")+
  '<div class="section"><h3>Lịch sử sự kiện</h3>'+
  table(["AT","EVENT"],events)+'</div>';
}
function renderTasks(){
 const rows=state.data.tasks.map(t=>
 '<tr><td><button class="link-button" data-detail-task="'+esc(t.task_id)+'">'+
 short(t.task_id)+'</button></td><td>'+esc(t.kind)+'</td><td>'+esc(t.skill_id)+
 '</td><td>'+badge(t.status)+'</td><td>'+esc(String(t.updated_at||"").slice(0,19))+
 '</td></tr>');
 return header("AUDIT TRAIL","Task History",
  "Bấm Task ID để xem lỗi, artifacts và log sự kiện ngay trong cửa sổ chi tiết.")+
 card("Các tác vụ gần đây",table(["TASK ID","LOẠI","SKILL","TRẠNG THÁI","UPDATED UTC"],rows));
}
function renderSkills(){
 const cards=state.data.skills.map(s=>
 '<div class="channel-card"><div class="channel-mark">◇</div><div class="channel-name mono">'+
 esc(s.id)+'</div><p>Worker: '+esc(s.worker)+'</p>'+badge(s.mode)+
 '</div>').join("");
 return header("WORKFORCE","AI Workforce","Danh mục skills hiện có, chạy qua một policy và Task History thống nhất.")+
 '<div class="callout section">Skill Registry có '+fmt(state.data.stats.skills)+
 ' contracts. Không thể tự tạo executor hoặc bypass quyền qua giao diện.</div>'+
 '<div class="flow-grid section">'+cards+'</div>';
}
function renderArtifacts(){
 const source=state.artifacts;
 if(!source)return header("LOCAL STORAGE","Projects & Files","Danh sách tài sản cục bộ, chỉ đọc.")+
  card("Đang tải","<p class='muted'>Đang kiểm kê file an toàn...</p>");
 const rows=(source.items||[]).map(a=>'<tr><td>'+esc(a.kind)+'</td><td class="mono">'+
  esc(a.id)+'</td><td>'+badge(a.status)+'</td><td>'+fmt(a.bytes)+'</td>'+
  '<td>Chưa xác minh triển khai</td></tr>');
 return header("LOCAL STORAGE","Projects & Files",
  "Chỉ kiểm kê những tài sản thuộc AgentForge. Không có nút xóa hàng loạt; không chạm dữ liệu nghiệp vụ.")+
  '<div class="callout">Workspace và SQLite được giữ nguyên trên máy. Website local ≠ đã triển khai online. Proposal ≠ sản phẩm được duyệt. Muốn dọn cache dùng scripts/repo_hygiene.py sau khi xem báo cáo.</div>'+
  '<div class="section">'+card("Kiểm kê tài sản · "+fmt(source.total_items),
    table(["LOẠI","ID/SLUG","TRẠNG THÁI","BYTES","ĐĂNG ONLINE"],rows,"Chưa có tài sản hợp lệ."))+'</div>'+
  (source.truncated?'<p class="small muted">Danh sách giới hạn 40 mục; tổng số hiển thị phía trên.</p>':'')+
  '<div class="section">'+renderImageStudio()+'</div>';
}
function renderImageStudio(){
 const health=state.imageHealth||{status:"NOT_CHECKED",checkpoints:[]};
 const jobs=state.imageJobs?.jobs||[];
 const sites=(state.artifacts?.items||[]).filter(x=>x.kind==="website");
 const checkpoints=(health.checkpoints||[]).map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join("");
 const sitesList=sites.map(x=>'<option value="'+esc(x.id)+'">'+esc(x.id)+'</option>').join("");
 const rows=jobs.map(x=>'<tr><td>'+short(x.job_id)+'</td><td>'+esc(x.slug)+'</td>'+
   '<td>'+badge(x.status)+'</td><td class="mono">'+short(x.asset_sha||"")+'</td>'+
   '<td>'+(x.status==="SUBMITTED"?
   '<button type="button" class="btn btn-small btn-outline" data-image-collect="'+esc(x.job_id)+'">Nhận ảnh khi xong</button>':
   x.status==="ASSET_READY"?
   '<button type="button" class="btn btn-small btn-primary" data-image-attach="'+esc(x.job_id)+'">Gắn ảnh vào web</button>':
   '—')+'</td></tr>');
 const form=health.status==="READY"&&sites.length?
   '<div class="form-field"><label for="image-project">Website đã apply (local)</label><select id="image-project">'+sitesList+'</select></div>'+
   '<div class="form-field"><label for="image-checkpoint">Checkpoint ComfyUI đã cài</label><select id="image-checkpoint">'+checkpoints+'</select></div>'+
   '<div class="form-field"><label for="image-prompt">Mô tả ảnh (20–450 ký tự)</label>'+
   '<textarea id="image-prompt" minlength="20" maxlength="450" rows="3" placeholder="Photorealistic cozy Vietnamese bedroom with elegant mattress, warm natural light, neutral palette, no text, no labels"></textarea></div>'+
   '<button type="button" class="btn btn-primary" data-image-submit="1">Tạo ảnh AI local · Xác nhận GPU</button>':
   '<p class="muted">Chưa có ComfyUI local + checkpoint hợp lệ hoặc chưa có website đã apply. Không tự tạo ảnh giả hay gọi dịch vụ cloud.</p>';
 return card("AI Image Studio · ComfyUI local (tùy chọn)",
  '<div class="callout">Dùng model ảnh riêng tại 127.0.0.1:8188, không phải Ollama qwen3:8b. Sinh ảnh có thể sử dụng GPU và điện. Ảnh phải được owner xem trước khi gắn vào website; không tự đăng online.</div>'+
  '<div class="form-actions"><button type="button" class="btn btn-outline" data-image-health="1">Kiểm tra ComfyUI / checkpoints</button>'+
  '<span class="small muted">Trạng thái: '+esc(health.status)+'</span></div>'+
  '<div class="section">'+form+'</div>'+
  '<div class="section"><h3>Các lượt tạo ảnh</h3>'+
  table(["JOB","WEBSITE","TRẠNG THÁI","ẢNH SHA","THAO TÁC"],rows,
        "Chưa có job AI image. Tác vụ đã gửi sẽ không tự chạy lại.")+'</div>'+
  '<p class="small muted">Sau khi nhận ảnh, mở workspace/products/SLUG/assets/af-ai-JOB_ID.png và kiểm tra bằng trình xem ảnh trên máy. Gắn ảnh sẽ lưu bản backup HTML; không ghi đè âm thầm.</p>');
}
function renderWebsites(){
 const proposals=state.data.tasks.filter(x=>x.web_proposal);
 const rows=proposals.map(t=>
  '<tr><td>'+esc(t.web_proposal.slug)+'</td><td>'+short(t.web_proposal.proposal_id)+
  '</td><td><span class="mono">'+short(t.web_proposal.sha256)+'</span></td><td>'+
  '<button class="btn btn-small btn-outline" data-view-proposal="'+
  esc(t.web_proposal.proposal_id)+'">Xem website</button></td></tr>');
 const p=state.proposal;
 const frame=p?'/api/proposals/'+encodeURIComponent(p.proposal_id)+'/preview':'';
 const preview=p?
  '<div class="detail-header"><div><h2>'+esc(p.project_slug)+'</h2>'+
  '<span class="small muted">Bản nháp · chỉ xem trước, chưa triển khai</span></div>'+badge(p.status)+'</div>'+
  '<div class="web-preview-controls"><strong>Xem giao diện thật</strong>'+
  '<div class="web-preview-toggle" role="group" aria-label="Kích thước màn hình">'+
  '<button type="button" class="btn btn-small '+(state.previewDevice==="mobile"?"btn-outline":"btn-primary")+
  '" data-preview-device="desktop">Desktop</button>'+
  '<button type="button" class="btn btn-small '+(state.previewDevice==="mobile"?"btn-primary":"btn-outline")+
  '" data-preview-device="mobile">Mobile</button></div></div>'+
  '<div class="web-preview-stage"><div class="web-preview-frame '+(state.previewDevice==="mobile"?"is-mobile":"is-desktop")+'">'+
  '<iframe title="Xem trước website AI: '+esc(p.project_slug)+'" sandbox="" referrerpolicy="no-referrer" loading="eager" src="'+esc(frame)+'"></iframe>'+
  '</div></div>'+
  '<p class="small muted">Bản xem trước bị cô lập: không chạy JavaScript, gửi biểu mẫu, tải tài nguyên Internet hoặc xuất bản website. Kiểm tra font, bố cục và nội dung trực quan trước khi duyệt.</p>'+
  '<details class="section web-source-details"><summary>Xem mã nguồn & SHA (nâng cao)</summary>'+
  '<p class="small muted">SHA-256: <span class="mono">'+esc(p.sha256)+'</span></p>'+
  (p.files||[]).map(f=>'<details class="section"><summary>'+esc(f.path)+'</summary>'+
   '<pre class="code-box">'+esc(f.content)+'</pre></details>').join("")+
  '</details>'+
  '<div class="review-feedback"><div class="review-feedback-heading"><div><h3>Chưa ưng? Góp ý để AI sửa</h3>'+
  '<p class="small muted">Mô tả điểm cần thay đổi. AgentForge sẽ tạo kế hoạch phiên bản mới; không sửa hoặc xóa proposal gốc.</p></div></div>'+
  '<label for="website-feedback">Yêu cầu chỉnh sửa</label>'+
  '<textarea id="website-feedback" rows="4" minlength="10" maxlength="360" placeholder="Ví dụ: Làm hero sang trọng hơn, thay tông màu, tăng kích thước ảnh nệm, CTA gọi 0879547988 rõ hơn..."></textarea>'+
  '<div class="review-actions"><button type="button" class="btn btn-outline" data-revise-proposal="'+
  esc(p.proposal_id)+'">Yêu cầu AI chỉnh sửa</button>'+
  '<button type="button" class="btn btn-primary" data-apply-proposal="'+
  esc(p.proposal_id)+'">Duyệt & lưu website local</button></div></div>':
  empty("Chọn một proposal rồi bấm Xem website để thấy giao diện desktop/mobile, không cần đọc mã HTML.");
 return header("PRODUCT BUILDER","Websites",
  "Xem trực quan landing page AI đã tạo, kiểm tra phiên bản mobile và duyệt trước khi lưu file.",
  '<button class="btn btn-primary" data-new-website>+ Tạo website draft</button>')+
 '<div class="callout">Bản xem trước không chạy code AI. Chỉ khi owner bấm duyệt, hệ thống mới ghi website vào máy; không tự triển khai online.</div>'+
 '<div class="section">'+card("Landing page đang chờ duyệt",
   table(["PROJECT","PROPOSAL ID","SHA-256","THAO TÁC"],rows))+'</div>'+
 '<div class="section">'+card("Preview & Approval",preview)+'</div>';
}
function renderAnalytics(){
 const rows=state.data.datasets.map(d=>
 '<tr><td>'+esc(d.dataset)+'</td><td>'+badge(d.synthetic?"SYNTHETIC DEMO":"OWNER SUPPLIED")+
 '</td><td>'+fmt(d.performance_rows)+'</td><td>'+fmt(d.ledger_rows)+'</td></tr>');
 return header("INTELLIGENCE","Intelligence & Analytics",
  "Báo cáo dựa trên dữ liệu đã nhập; source không đồng nghĩa xác minh độc lập.")+
 '<div class="callout warning">Các bộ dữ liệu SYNTHETIC DEMO chỉ dùng thử nghiệm; không được xem là nhu cầu thị trường hay doanh thu thật.</div>'+
 '<div class="section">'+card("S3 Datasets",
 table(["DATASET","PROVENANCE","PERFORMANCE ROWS","LEDGER ROWS"],rows))+'</div>';
}
function renderGrowth(){
 const entries=state.data.growth.map(g=>'<tr><td><button class="link-button" data-detail-growth="'+
 esc(g.campaign)+'">'+esc(g.campaign)+'</button></td><td>'+esc(g.title)+
 '</td><td>'+badge(g.synthetic?"SYNTHETIC DEMO":"OWNER RECORDED")+
 '</td><td>'+fmt(g.lead_total)+'</td><td>'+fmt(g.package_count)+
 '</td><td>'+fmt(g.owner_reported_posts)+'</td><td>'+fmt(g.owner_recorded_net_cash_vnd)+'</td></tr>');
 const create='<form id="campaign-form"><div class="form-field"><label for="campaign-json">Thông tin chiến dịch · JSON</label>'+
 '<textarea id="campaign-json" rows="7" spellcheck="false">'+esc(JSON.stringify({
  campaign:"nem-pilot",title:"Tư vấn nệm",analytics_dataset:"",
  budget_vnd:0,synthetic:false
 },null,2))+'</textarea></div>'+
 '<div class="callout warning">budget_vnd chỉ giới hạn chi phí ghi sổ. Không có quyền chi tiền hoặc tạo tài khoản quảng cáo.</div>'+
 '<div class="form-actions"><button type="submit" class="btn btn-primary">Tạo campaign</button></div></form>';
 const event='<form id="event-form"><div class="form-field"><label for="event-json">Sự kiện business · JSON</label>'+
 '<textarea id="event-json" rows="7" spellcheck="false">'+esc(JSON.stringify({
  kind:"lead_new",data:{campaign:"nem-pilot",channel:"website",consent_confirmed:true}
 },null,2))+'</textarea></div>'+
 '<div class="callout">Chỉ xác nhận consent nếu khách thật sự đồng ý. Không nhập tên, điện thoại, email hoặc thông tin cá nhân vào JSON.</div>'+
 '<div class="form-actions"><button type="submit" class="btn btn-primary">Ghi sự kiện</button></div></form>';
 return header("BUSINESS OPERATIONS","Growth & Revenue",
  "Theo dõi chiến dịch, lead ẩn danh, gói nội dung và các khoản tiền do owner ghi nhận.")+
 '<div class="callout warning">Không có tài khoản mạng xã hội/ngân hàng đã kết nối. Gói ZIP không phải bài đăng; tiền ghi sổ không phải lợi nhuận đã xác minh.</div>'+
 '<div class="section">'+card("Danh sách chiến dịch",
 table(["CAMPAIGN","TÊN","PHÂN LOẠI","LEADS","PACKAGES","OWNER POSTS","NET CASH VND"],entries))+
 '</div><div class="grid-2 grid-even section">'+card("Tạo chiến dịch",create)+
 card("Ghi nhận lead / commission / trạng thái",event)+'</div>';
}
function renderSchedules(){
 const rows=state.data.schedules.map(s=>'<tr><td>'+esc(s.title)+
 '</td><td>'+esc(s.template)+'</td><td>'+badge(s.status)+
 '</td><td>'+esc(s.next_due_utc)+
 '</td><td><button class="btn btn-small btn-outline" data-schedule-status="'+
 esc(s.schedule_id)+'" data-next-status="'+
 (s.status==="PAUSED"?"ACTIVE":"PAUSED")+'">'+
 (s.status==="PAUSED"?"Bật lại":"Tạm dừng")+'</button></td></tr>');
 const readOnly=["campaign.review","growth.review","media.review","website.campaign"];
 const options=readOnly.filter(k=>state.data.templates[k]).map(
  k=>'<option value="'+esc(k)+'">'+esc(k)+'</option>').join("");
 const form='<form id="schedule-form"><div class="form-field"><label for="schedule-title">Tên lịch chạy</label>'+
 '<input id="schedule-title" value="Đánh giá chiến dịch định kỳ" required minlength="3"></div>'+
 '<div class="form-field"><label for="schedule-template">Read-only workflow</label>'+
 '<select id="schedule-template">'+options+'</select></div>'+
 '<div class="form-field"><label for="schedule-input">Inputs · JSON</label>'+
 '<textarea id="schedule-input" rows="4" spellcheck="false">'+
 esc(JSON.stringify({dataset:state.data.datasets?.[0]?.dataset||""}))+'</textarea></div>'+
 '<div class="form-row"><div class="form-field"><label for="schedule-due">Chạy lần đầu (giờ máy)</label>'+
 '<input id="schedule-due" type="datetime-local" required></div>'+
 '<div class="form-field"><label for="schedule-frequency">Lặp lại mỗi (phút)</label>'+
 '<input id="schedule-frequency" type="number" min="60" max="10080" value="1440"></div></div>'+
 '<div class="form-actions"><button class="btn btn-primary" type="submit">Tạo lịch đã duyệt</button>'+
 '<button class="btn btn-outline" data-tick-schedules type="button">Chạy tick thủ công</button></div></form>';
 const h=state.data.daemon;
 return header("SCHEDULER","Local Schedules",
  "Lịch chỉ chạy read-only workflow và lưu slot trước khi bắt đầu. Không tự bật daemon.")+
 '<div class="callout '+(h.fresh?"":"warning")+'">Scheduler: '+
 esc(h.fresh?"Daemon heartbeat mới nhất được ghi nhận":"Không có daemon hoạt động được xác minh")+
 '. Có thể dùng tiến trình ops_daemon riêng khi máy luôn bật.</div>'+
 '<div class="grid-2 grid-even section">'+card("Tạo lịch",form)+card("Cơ chế an toàn",
 '<div class="stack"><div class="goal-tile"><span class="goal-mark">✓</span>'+
 '<div class="goal-main"><strong>Read-only & owner approved</strong>'+
 '<small>Không cấp quyền model, browser hay chi tiền</small></div></div>'+
 '<div class="goal-tile"><span class="goal-mark">◷</span><div class="goal-main">'+
 '<strong>Once-only due slot</strong><small>Không tự replay sau mất điện</small></div></div>'+
 '<div class="goal-tile"><span class="goal-mark">⎔</span><div class="goal-main">'+
 '<strong>Local Windows / desktop</strong><small>Máy tắt thì lịch không thể chạy</small>'+
 '</div></div></div>')+'</div>'+
 '<div class="section">'+card("Lịch đã tạo",table(["TÊN","TEMPLATE","STATUS","NEXT DUE UTC","THAO TÁC"],rows))+'</div>';
}
function renderOperations(){
 const d=state.ops;
 if(!d)return card("System Health","<p class=\"muted\">Chọn Integrations để đọc tình trạng SQLite, backup và scheduler. Không thực thi công việc.</p>");
 const db=Object.entries(d.databases||{}).map(([name,v])=>
 '<tr><td>'+esc(name)+'</td><td>'+badge(v.status)+'</td><td>'+fmt(v.size_bytes)+'</td></tr>');
 const findings=(d.findings||[]).map(f=>
 '<div class="goal-tile"><div class="goal-main"><strong>'+esc(f.rule)+'</strong>'+
 '<small>'+esc(f.severity)+' · '+esc(f.name||"Vận hành local")+'</small></div></div>').join("");
 return card("Local System Health",
  '<div class="callout warning">Backup có dữ liệu nhạy cảm và chưa mã hóa. Chỉ lưu local, không upload công khai. Restore chỉ vào thư mục staging mới.</div>'+
  '<p>Kiểm tra: '+badge(d.status)+' · Backup: '+fmt(d.backup_count)+
  ' · Đang chạy: '+fmt(d.running_goals)+' goals / '+fmt(d.running_tasks)+' tasks</p>'+
  table(["DB","Integrity","Bytes"],db)+
  (findings||'<p class="muted">Không có cảnh báo nào.</p>')+
