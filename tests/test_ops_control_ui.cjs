/* Owner operations safety and attention inbox UI regression. */
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const js = fs.readFileSync(path.join(
  __dirname,"..","src","agentforge","control_center_static","app.js"),"utf8");

function overview(mode, attention=[]) {
  const ctx=vm.createContext({
    document:{getElementById(){return null;},addEventListener(){},querySelectorAll(){return [];}},
    window:{scrollTo(){}},console,
  });
  vm.runInContext(js,ctx);
  const data={
    stats:{tasks:1,succeeded:1,waiting_approval:0,skills:24},
    goals:[],tasks:[],daemon:{fresh:false},
    operations:{mode},attention,
  };
  vm.runInContext("state.data = "+JSON.stringify(data),ctx);
  return vm.runInContext("renderOverview()",ctx);
}

test("Owner can pause active system without hiding dashboard",()=>{
  const html=overview("ACTIVE");
  assert.match(html,/data-ops-mode="PAUSED"/);
  assert.match(html,/Tạm dừng hệ thống/);
  assert.match(html,/Cần owner xử lý/);
});
test("Paused system displays fail-closed state and explicit resume action",()=>{
  const html=overview("PAUSED", [{
    kind:"goal",id:"b".repeat(32),title:"Review campaign",
    status:"WAITING_APPROVAL",priority:"HIGH"
  }]);
  assert.match(html,/data-ops-mode="ACTIVE"/);
  assert.match(html,/Đã dừng phân phối nhiệm vụ mới/);
  assert.match(html,/data-detail-goal="b{32}"/);
  assert.match(html,/WAITING_APPROVAL/);
});
test("Owner attention queue HTML escapes titles from local records",()=>{
  const html=overview("ACTIVE", [{
    kind:"goal",id:"a".repeat(32),
    title:'<img src=x onerror=alert("bad")>',
    status:"FAILED",priority:"REVIEW"
  }]);
  assert.match(html,/&lt;img src=x onerror/);
  assert.doesNotMatch(html,/<img src=x onerror=/);
});
