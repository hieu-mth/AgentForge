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
