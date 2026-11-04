/* AgentForge Control Center V1 — no libraries, no CDN, no client storage.
   The browser never determines permissions. Server-side owner gates are final. */
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v === null || v === undefined ? "—" : v)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
const state = {csrf:null, data:null, view:"overview", goal:null, task:null, memory:null};
const viewNames = {overview:"Tổng quan",goals:"Goals & Phê duyệt",tasks:"Task History",
 skills:"AI Workforce",analytics:"Intelligence",growth:"Growth & Revenue",
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
 const color=s==="SUCCEEDED"||s==="VALID"||s==="ACTIVE"?"success":
 ["WAITING_APPROVAL","REVIEW_REQUIRED","PLANNED","APPROVED","READY_FOR_OWNER_UPLOAD"].includes(s)?"warning":
 ["FAILED","INTERRUPTED"].includes(s)?"danger":
 s==="RUNNING"?"blue":"muted";
 return '<span class="pill pill-'+color+'">'+esc(s)+'</span>';
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
function renderOverview(){
 const d=state.data,s=d.stats;
 const metrics=[
 ["Tổng nhiệm vụ",s.tasks,"S1 · Task History","≡"],
 ["Đã hoàn thành",s.succeeded,"Trên những task hiển thị","✓"],
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
 '</small></div>'+badge(g.status)+'<button type="button" class="btn btn-small btn-outline" data-detail-goal="'+
 esc(g.goal_id)+'">Xem</button></div>').join("");
 const recent=d.tasks.slice(0,6).map(t=>
 '<tr><td><button class="link-button" data-detail-task="'+esc(t.task_id)+'">'+
 short(t.task_id)+'</button></td><td>'+esc(t.skill_id)+'</td><td>'+badge(t.status)+
 '</td><td>'+esc(String(t.updated_at||"").replace("T"," ").slice(0,19))+'</td></tr>');
 const h=d.daemon;
 const engine=h.fresh?'DAEMON ACTIVE':'MANUAL / OFFLINE';
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
 '</td><td>'+badge(g.status)+'</td><td>'+fmt(g.current_step)+'</td></tr>');
}
function renderGoals(){
 const templates=Object.keys(state.data.templates);
 const selected=templates.includes("campaign.review")?"campaign.review":templates[0];
 const templateOptions=templates.map(k=>'<option value="'+esc(k)+'">'+esc(k)+'</option>').join("");
 const form='<form id="goal-form"><div class="form-field"><label for="goal-title">Tên mục tiêu</label>'+
 '<input id="goal-title" required minlength="3" maxlength="160" value="Review campaign" /></div>'+
 '<div class="form-field"><label for="goal-template">Workflow có sẵn</label>'+
 '<select id="goal-template">'+templateOptions+'</select></div>'+
 '<div class="form-field"><label for="goal-json">Đầu vào · JSON</label>'+
 '<textarea id="goal-json" rows="5" spellcheck="false">{"dataset":"demo-example"}</textarea></div>'+
 '<div class="form-row"><div class="form-field"><label for="goal-model-cap">Max model calls (ước tính)</label>'+
 '<input id="goal-model-cap" type="number" min="0" max="3" value="0"></div>'+
 '<div class="form-field"><label for="goal-process-cap">Max external process runs</label>'+
 '<input id="goal-process-cap" type="number" min="0" max="3" value="0"></div></div>'+
 '<div class="callout">Đề xuất không tự thực thi. Bạn phải xem kế hoạch, đối chiếu SHA rồi duyệt. Các thao tác ghi hoặc external tiếp tục yêu cầu grant riêng.</div>'+
 '<div class="form-actions"><button type="submit" class="btn btn-primary">Tạo kế hoạch</button></div></form>';
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
  return '<li class="step"><span class="step-num">'+(i+1)+'</span><div class="step-text"><strong>'+
   esc(step.skill_id)+'</strong><small>'+esc(step.worker_id)+' · '+
   esc((step.required_permissions||[]).join(", ")||"read_only")+
   '</small></div>'+badge(executed?executed.status:"NOT_STARTED")+'</li>';
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
 esc(g.template)+' · '+short(g.goal_id)+'</div></div>'+badge(g.status)+'</div>'+
 '<p class="small muted" style="margin-top:12px">SHA-256 kế hoạch (bắt buộc khớp)</p>'+
 '<div class="mono callout">'+esc(g.plan_sha256)+'</div>'+
 '<ol class="step-list">'+stepRows+'</ol>'+approve+permissions+
 '<details class="section"><summary class="small muted">Xem đầy đủ inputs và plan để kiểm tra</summary>'+
 '<pre class="code-box">'+esc(JSON.stringify({inputs:g.inputs,plan:g.plan},null,2))+'</pre></details>';
}
function renderTasks(){
 const rows=state.data.tasks.map(t=>
 '<tr><td><button class="link-button" data-detail-task="'+esc(t.task_id)+'">'+
 short(t.task_id)+'</button></td><td>'+esc(t.kind)+'</td><td>'+esc(t.skill_id)+
 '</td><td>'+badge(t.status)+'</td><td>'+esc(String(t.updated_at||"").slice(0,19))+
 '</td></tr>');
 const selected=state.task?
 '<div class="section">'+card("Task details",
  '<div class="detail-header"><h2>'+short(state.task.task_id)+'</h2>'+badge(state.task.status)+'</div>'+
  '<p class="small muted">'+esc(state.task.skill_id)+'</p>'+
  '<div class="callout">Artifacts: '+esc((state.task.artifacts||[]).join(", ")||"None")+'</div>'+
  table(["AT","EVENT"],(state.task.events||[]).map(x=>
   '<tr><td>'+esc(x.at)+'</td><td>'+esc(x.name)+'</td></tr>')))+
 '</div>':"";
 return header("AUDIT TRAIL","Task History",
  "Mọi skill được gọi thông qua S1 đều có trạng thái, bằng chứng và log sự kiện.")+
 card("Các tác vụ gần đây",table(["TASK ID","LOẠI","SKILL","TRẠNG THÁI","UPDATED UTC"],rows))+
 selected;
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
 '<textarea id="schedule-input" rows="4" spellcheck="false">{"dataset":"demo-example"}</textarea></div>'+
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
function renderIntegrations(){
 const cards=state.data.connectors.map(c=>
 '<div class="channel-card"><div class="channel-mark">⎔</div><div class="channel-name">'+
 esc(c.name)+'</div>'+badge(c.status)+
 '<p>Chưa có OAuth/API token và quyền từ nền tảng. AgentForge không báo cáo đã upload hoặc nhận tiền.</p>'+
 '<span class="channel-foot">Handoff: owner thực hiện · Verified: No</span></div>').join("");
 return header("CHANNEL READINESS","Integrations",
  "Các kết nối cần tài khoản chính chủ và quyền API chính thức trước khi tự động vận hành.")+
 '<div class="callout warning">Công cụ đã có thể chuẩn bị video/upload kit và quản lý chiến dịch. Chưa có connector trực tiếp tới YouTube, TikTok, ngân hàng hay cổng affiliate. Trạng thái CONNECTED không được suy đoán.</div>'+
 '<div class="grid-3 section">'+cards+'</div>'+
 '<div class="section">'+card("Điều kiện cho tích hợp thực tế",
 '<div class="stack"><div class="goal-tile"><span class="goal-mark">1</span><div class="goal-main"><strong>Owner sở hữu tài khoản</strong><small>Tự xác thực theo điều khoản nền tảng; không đưa mật khẩu vào chat hoặc SQLite.</small></div></div>'+
 '<div class="goal-tile"><span class="goal-mark">2</span><div class="goal-main"><strong>OAuth / Scope tối thiểu</strong><small>Chỉ các API và quyền đã được nhà cung cấp cấp phép.</small></div></div>'+
 '<div class="goal-tile"><span class="goal-mark">3</span><div class="goal-main"><strong>Publish gate + tài chính thực</strong><small>Review content, chống đăng trùng, nhận receipt, kiểm soát chi phí provider và đối soát.</small></div></div></div>')+'</div>';
}
function renderMemory(){
 const rows=(state.memory||[]).map(m=>
 '<tr><td>'+esc(m.key)+'</td><td>'+esc(m.note)+'</td><td>'+
 esc(m.evidence_ref)+'</td><td>'+fmt(m.revision)+'</td></tr>');
 const form='<form id="memory-form"><div class="form-field"><label for="memory-key">Memory key</label>'+
 '<input id="memory-key" placeholder="marketing.goal" required></div>'+
 '<div class="form-field"><label for="memory-note">Ghi chú</label>'+
 '<textarea id="memory-note" maxlength="600" required></textarea></div>'+
 '<div class="form-field"><label for="memory-evidence">Evidence reference</label>'+
 '<input id="memory-evidence" placeholder="owner:decision-1" required></div>'+
 '<div class="form-actions"><button class="btn btn-primary" type="submit">Lưu ghi chú owner</button></div></form>';
 return header("OWNER KNOWLEDGE","Owner Memory",
  "Ghi chú do owner quản lý và có evidence reference. Không phải bộ nhớ tự học hoặc kho mật khẩu.")+
 '<div class="callout warning">Chỉ lưu thông tin không nhạy cảm. SQLite local chưa được mã hóa. Không nhập token, số điện thoại khách, tài khoản hay mật khẩu.</div>'+
 '<div class="split section">'+card("Lưu quyết định",form)+
 card("Ghi chú đã lưu",table(["KEY","NỘI DUNG","EVIDENCE","REV"],rows))+'</div>';
}
function render(){
 if(!state.data)return;
 $("page-crumb").textContent=viewNames[state.view]||"Tổng quan";
 $("nav-wait").textContent=String(state.data.goals.filter(g=>g.status==="WAITING_APPROVAL").length);
 document.querySelectorAll(".nav-link").forEach(x=>x.classList.toggle(
  "active",x.dataset.view===state.view));
 const output={overview:renderOverview,goals:renderGoals,tasks:renderTasks,
  skills:renderSkills,analytics:renderAnalytics,growth:renderGrowth,
  schedules:renderSchedules,integrations:renderIntegrations,memory:renderMemory};
 $("content").innerHTML=(output[state.view]||renderOverview)();
 if(state.view==="goals"){
  const t=$("goal-template");
  t.addEventListener("change",()=>{const required=state.data.templates[t.value]||[];
   const values={};required.forEach(k=>{values[k]=({
    dataset:"demo-example",campaign:"nem-shorts",slug:"nem-tu-van",
    title:"Tư vấn nệm",scenes:[],run_id:"0".repeat(32),
    topic:"Nghiên cứu nhu cầu nệm",audience:"Khách hàng",goal:"Tư vấn",
    description:"Lời khuyên cơ bản khi lựa chọn nệm.",rights_attested:true}
   )[k]||"";});
   $("goal-json").value=JSON.stringify(values,null,2);
  });
 }
}
function selectView(view){
 if(!viewNames[view])return;
 state.view=view;state.task=null;
 $("sidebar")?.classList.remove("open");$("mobile-overlay").hidden=true;
 if(view==="memory"){
  api("/api/memory").then(m=>{state.memory=m;render();})
   .catch(e=>notice(e.message,true));
 }
 render();window.scrollTo({top:0,behavior:"smooth"});
}
async function showGoal(id){
 try{state.goal=await api("/api/goals/"+encodeURIComponent(id));selectView("goals");}
 catch(e){notice(e.message,true);}
}
async function showTask(id){
 try{state.task=await api("/api/tasks/"+encodeURIComponent(id));selectView("tasks");}
 catch(e){notice(e.message,true);}
}
function formJson(id){try{return JSON.parse($(id).value);}catch{throw Error("JSON không hợp lệ trong "+id);}}
async function mutate(path,payload,success){
 const result=await api(path,"POST",payload);
 notice(success||"Đã thực hiện");
 await refresh();return result;
}
async function handleClick(event){
 const button=event.target.closest("button");
 if(!button||button.disabled)return;
 if(button.dataset.view){selectView(button.dataset.view);return;}
 try{
  if(button.dataset.detailGoal){await showGoal(button.dataset.detailGoal);return;}
  if(button.dataset.detailTask){await showTask(button.dataset.detailTask);return;}
  if(button.dataset.detailGrowth){
    const x=await api("/api/growth/"+encodeURIComponent(button.dataset.detailGrowth));
    notice("Report: "+x.campaign+" · "+x.status);return;
  }
  const goalId=button.dataset.approveGoal||button.dataset.runGoal||
               button.dataset.resumeGoal;
  if(goalId){
    if(!state.goal||state.goal.goal_id!==goalId)await showGoal(goalId);
    const g=state.goal;
    if(button.dataset.approveGoal){
      if(!confirm("Duyệt kế hoạch SHA-256:\n"+g.plan_sha256+"\n\nDuyệt KHÔNG tự chạy task."))return;
      await mutate("/api/goals/"+goalId+"/approve",{ack:"APPROVE",
        plan_sha256:g.plan_sha256},"Đã duyệt plan");await showGoal(goalId);return;
    }
    const action=button.dataset.runGoal?"run":"resume";
    const grants=[...document.querySelectorAll('input[name="grant"]:checked')].map(i=>i.value);
    const sensitive=grants.some(g=>["model.invoke","network.search","network.read",
     "process.run","browser.run"].includes(g))||g.plan?.some(x=>
     x.required_permissions?.some(p=>["model.invoke","network.search","network.read",
      "process.run","browser.run"].includes(p)));
    if(sensitive&&!state.data.external_actions_enabled)throw Error(
     "External tools đang bị khóa. Khởi động server với --allow-external-tools nếu bạn quyết định cấp quyền.");
    if(!confirm("Thực thi Goal "+goalId.slice(0,12)+"?\nGrants: "+
     (grants.join(", ")||"read-only")+"\nLệnh chạy sẽ được lưu vào Task History."))return;
    if(sensitive&&!confirm("XÁC NHẬN LẦN HAI: Có thể dùng model, mạng, browser hoặc FFmpeg với quyền đã chọn?"))return;
    const request={ack:action.toUpperCase(),plan_sha256:g.plan_sha256,grants,
     confirm_model_call:$("confirm-model").checked,
     confirm_browser_run:$("confirm-browser").checked,
     confirm_external_run:$("confirm-process").checked,
     ack_external:sensitive?"AUTHORIZE_EXTERNAL_TOOLS":""};
    const out=await mutate("/api/goals/"+goalId+"/"+action,request,
      "Goal: "+action+" → "+(action==="run"?"đã xử lý":"đã tiếp tục"));
    notice("Trạng thái: "+out.status);await showGoal(goalId);return;
  }
  if(button.dataset.tickSchedules!==undefined){
   if(!confirm("Chạy thủ công những lịch read-only đã tới hạn?"))return;
   const x=await mutate("/api/schedules/tick",{ack:"TICK"},"Scheduler tick hoàn thành");
   notice("Đã claim "+x.claimed.length+" lịch.");return;
  }
  if(button.dataset.scheduleStatus){
   const next=button.dataset.nextStatus;
   if(!confirm(next+" lịch này?"))return;
   await mutate("/api/schedules/"+button.dataset.scheduleStatus+"/status",
    {status:next,ack:next},"Đã đổi trạng thái lịch");return;
  }
 }catch(e){notice(e.message,true);}
}
async function handleSubmit(event){
 const id=event.target.id;
 if(!["goal-form","schedule-form","campaign-form","event-form","memory-form"].includes(id))return;
 event.preventDefault();
 const submit=event.target.querySelector('button[type="submit"]');
 if(submit)submit.disabled=true;
 try{
  if(id==="goal-form"){
   const out=await mutate("/api/goals/propose",{
    ack:"PROPOSE",title:$("goal-title").value,
    template:$("goal-template").value,inputs:formJson("goal-json"),
    max_model_calls:Number($("goal-model-cap").value),
    max_external_runs:Number($("goal-process-cap").value)
   },"Đã tạo kế hoạch; hãy kiểm tra SHA trước khi duyệt");
   await showGoal(out.goal_id);
  }else if(id==="schedule-form"){
   const due=new Date($("schedule-due").value);
   if(Number.isNaN(due.getTime()))throw Error("Chọn thời điểm hợp lệ");
   await mutate("/api/schedules/create",{
    ack:"SCHEDULE",title:$("schedule-title").value,
    template:$("schedule-template").value,inputs:formJson("schedule-input"),
    next_due:due.toISOString(),
    frequency_minutes:Number($("schedule-frequency").value)
   },"Đã tạo lịch read-only");
  }else if(id==="campaign-form"){
   const data=formJson("campaign-json");
   if(!confirm("Tạo campaign local, không chi tiền và không đăng bài?"))return;
   await mutate("/api/campaigns/create",
    {ack:"CREATE_CAMPAIGN",data},"Đã tạo campaign");
  }else if(id==="event-form"){
   const data=formJson("event-json");
   if(!confirm("Xác nhận đã có quyền/consent và dữ liệu là do owner nhập?"))return;
   await mutate("/api/campaigns/event",
    {ack:"RECORD_EVENT",kind:data.kind,data:data.data},"Đã ghi sự kiện local");
  }else{
   await mutate("/api/memory/set",{ack:"SAVE_NOTE",key:$("memory-key").value,
    note:$("memory-note").value,evidence_ref:$("memory-evidence").value},
    "Đã lưu evidence note");
   state.memory=await api("/api/memory");render();
  }
 }catch(e){notice(e.message,true);}
 finally{if(submit)submit.disabled=false;}
}
document.addEventListener("DOMContentLoaded",()=>{
 $("login-form").addEventListener("submit",async e=>{
  e.preventDefault();
  try{
   const response=await api("/api/login","POST",{code:$("owner-code").value});
   state.csrf=response.csrf;$("owner-code").value="";
   state.data=await api("/api/bootstrap");showShell();
  }catch(err){$("login-feedback").textContent=err.message;}
 });
 $("refresh").addEventListener("click",refresh);
 $("logout").addEventListener("click",async()=>{
  try{await api("/api/logout","POST",{});}catch{}
  showLogin();
 });
 $("menu-toggle").addEventListener("click",()=>{
  $("sidebar").classList.toggle("open");
  $("mobile-overlay").hidden=!$("sidebar").classList.contains("open");
 });
 $("mobile-overlay").addEventListener("click",()=>{
  $("sidebar").classList.remove("open");$("mobile-overlay").hidden=true;
 });
 document.addEventListener("click",handleClick);
 document.addEventListener("submit",handleSubmit);
 start();
});
