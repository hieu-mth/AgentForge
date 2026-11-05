/* Goal input safety and source-limited Result Viewer regression. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(
  __dirname, "..", "src", "agentforge", "control_center_static", "app.js"), "utf8");

function context(state) {
  const ctx = vm.createContext({
    document: {
      getElementById: () => null, addEventListener() {},
      querySelectorAll() {return [];},
    },
    window: {scrollTo() {}}, console,
  });
  vm.runInContext(source, ctx);
  vm.runInContext("state.data = " + JSON.stringify(state), ctx);
  return ctx;
}

test("Goal form defaults to existing dataset, not demo-example placeholder", () => {
  const ctx = context({
    goals:[], templates:{"campaign.review":["dataset"]},
    datasets:[{dataset:"demo-e0bac50a03",synthetic:true}],
    growth:[]
  });
  const html=vm.runInContext("renderGoals()",ctx);
  assert.match(html,/id="goal-dataset-pick"/);
  assert.match(html,/demo-e0bac50a03/);
  assert.doesNotMatch(html,/demo-example/);
  assert.match(html,/data-preflight-goal/);
  assert.match(html,/DEMO/);
});

test("If there is no dataset the form warns rather than suggesting fake ID", () => {
  const ctx=context({goals:[],templates:{"campaign.review":["dataset"]},
                     datasets:[],growth:[]});
  const html=vm.runInContext("renderGoals()",ctx);
  assert.match(html,/Chưa có dataset/);
  assert.doesNotMatch(html,/demo-example/);
});

test("Completed Goal step offers a direct safe Task Result button", () => {
  const ctx=context({goals:[],templates:{"campaign.review":["dataset"]},
                     datasets:[],growth:[]});
  const id="a".repeat(32);
  vm.runInContext("state.goal = "+JSON.stringify({
    goal_id:"b".repeat(32),title:"Review",template:"campaign.review",
    status:"SUCCEEDED",plan_sha256:"f".repeat(64),
    plan:[{skill_id:"analytics.content_report",worker_id:"analytics_analyst",
           required_permissions:["workspace.read"]}],
    step_runs:[{step_index:0,child_task_id:id,status:"SUCCEEDED"}],
    inputs:{dataset:"demo-valid"},
  }),ctx);
  const html=vm.runInContext("renderGoalDetail()",ctx);
  assert.match(html,new RegExp('data-detail-task="'+id+'"'));
  assert.match(html,/Xem kết quả \/ lỗi/);
});

test("Result Viewer renders synthetic and uncertainty, escapes injected HTML", () => {
  const ctx=context({goals:[],templates:{},datasets:[],growth:[]});
  const result=vm.runInContext("renderResultReport("+JSON.stringify({
    kind:"analytics",
    fields:{dataset:"demo-test",synthetic:true,status:"ANALYZED"},
    metrics:{clicks:22,views:300},
    channels:[{name:"youtube",metrics:{views:300}}],
    signals:[{channel:"youtube",investigation_score_0_100:40}],
    notices:['<img src=x onerror=alert("xss")>'],
    source_count:2,business_verified:false,
  })+")",ctx);
  assert.match(result,/DEMO/);
  assert.match(result,/22/);
  assert.match(result,/Tín hiệu cần kiểm chứng/);
  assert.match(result,/&lt;img src=x onerror/);
  assert.doesNotMatch(result,/<img src=x onerror/);
  assert.match(result,/Doanh thu xác minh độc lập: Không/);
});
