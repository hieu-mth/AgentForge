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
