/* Control Center Task History modal regression. No DOM/npm dependencies. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const staticDir = path.join(__dirname, "..", "src", "agentforge",
                            "control_center_static");
const script = fs.readFileSync(path.join(staticDir, "app.js"), "utf8");
const html = fs.readFileSync(path.join(staticDir, "app.html"), "utf8");

function runtime(task, initialView="tasks") {
  const nodes = new Map(), documentListeners = new Map(), calls = [];
  let scrollCount = 0;
  const node = id => {
    if (!nodes.has(id)) {
      const listeners = {};
      nodes.set(id, {
        innerHTML: "", textContent: "", hidden: false,
        open: false, shown: 0, listeners,
        classList: {add() {}, remove() {}, toggle() {}},
        addEventListener(type, fn) {
          (listeners[type] ||= []).push(fn);
        },
        showModal() {this.open = true; this.shown += 1;},
        close() {
          if (!this.open)return;
          this.open = false;
          for (const fn of listeners.close || [])fn({target:this});
        },
      });
    }
    return nodes.get(id);
  };
  const context = vm.createContext({
    document: {
      addEventListener(type, fn) {
        (documentListeners.get(type) || documentListeners.set(type, []).get(type)).push(fn);
      },
      getElementById: node,
      querySelectorAll() {return [];},
    },
    window: {scrollTo() {scrollCount++;}},
    fetch: async route => {
      calls.push(route);
      return {ok:true, text: async () => JSON.stringify(task)};
    },
    console, setTimeout,
  });
  vm.runInContext(script, context, {filename:"app.js"});
  vm.runInContext("state.data = " + JSON.stringify({
    tasks: [{
      task_id:task.task_id, kind:"skill", skill_id:task.skill_id,
      status:task.status, updated_at:"2026-11-05T10:00:00Z",
    }],
    goals:[], templates:{},
  }) + "; state.view=" + JSON.stringify(initialView), context);
  // The existing on-load handler has independent auth/start logic. Stub it
  // while testing the registered modal close handlers.
  vm.runInContext("start = () => {}", context);
  for (const fn of documentListeners.get("DOMContentLoaded") || [])fn();
  vm.runInContext("render()", context);
  return {context, node, calls, getScrollCount:()=>scrollCount};
}

function task(id="a".repeat(32), error="Dataset not found: demo-example") {
  return {
    task_id:id,kind:"skill",skill_id:"analytics.quality_check",
    status:error?"FAILED":"SUCCEEDED",error,
    artifacts:[],events:[{at:"2026-11-05T10:00:00Z",name:"FAILED"}],
  };
}

test("Task ID click opens native modal, no page navigation or forced scroll", async () => {
  const t=task();
  const {context,node,calls,getScrollCount}=runtime(t);
  const before=node("content").innerHTML;
  const click = {target:{
    closest(tag) {
      assert.equal(tag,"button");
      return {disabled:false,dataset:{detailTask:t.task_id}};
    },
  }};
  await vm.runInContext("handleClick",context)(click);
  assert.deepEqual(calls,["/api/tasks/"+t.task_id]);
  assert.equal(vm.runInContext("state.view",context),"tasks");
  assert.equal(getScrollCount(),0);
  assert.equal(node("content").innerHTML,before);
  assert.equal(node("task-dialog").open,true);
  assert.equal(node("task-dialog").shown,1);
  const body=node("task-dialog-body").innerHTML;
  assert.match(body,/analytics\.quality_check/);
  assert.match(body,/Dataset not found: demo-example/);
  assert.match(body,/FAILED/);
  assert.match(body,/Lịch sử sự kiện/);
});

test("Safe error rendering escapes untrusted HTML within modal", async () => {
  const t=task("b".repeat(32),'<img src=x onerror=alert("XSS")>');
  const {context,node}=runtime(t);
  await vm.runInContext("showTask("+JSON.stringify(t.task_id)+")",context);
  const body=node("task-dialog-body").innerHTML;
  assert.match(body,/&lt;img src=x onerror=alert/);
  assert.doesNotMatch(body,/<img src=x onerror=/);
  assert.equal(node("task-dialog").open,true);
});

test("Close button, backdrop and native dialog close reset selected task", async () => {
  const t=task("c".repeat(32));
  const {context,node}=runtime(t);
  await vm.runInContext("showTask("+JSON.stringify(t.task_id)+")",context);
  const dialog=node("task-dialog");
  assert.equal(dialog.open,true);
  const close=node("task-dialog-close").listeners.click[0];
  close();
  assert.equal(dialog.open,false);
  assert.equal(vm.runInContext("state.task",context),null);
  assert.equal(node("task-dialog-body").textContent,"");

  // Opening twice after close must show the new details.
  await vm.runInContext("showTask("+JSON.stringify(t.task_id)+")",context);
  assert.equal(dialog.shown,2);
  dialog.listeners.click[0]({target:dialog});
  assert.equal(dialog.open,false);
  assert.equal(vm.runInContext("state.task",context),null);
  // Browser's native Esc dispatches a close event. Our cleanup is identical.
  await vm.runInContext("showTask("+JSON.stringify(t.task_id)+")",context);
  dialog.close();
  assert.equal(vm.runInContext("state.task",context),null);
});

test("Task can open from Overview without switching page", async () => {
  const t=task("d".repeat(32),null);
  const {context,node,getScrollCount}=runtime(t,"overview");
  await vm.runInContext("showTask("+JSON.stringify(t.task_id)+")",context);
  assert.equal(vm.runInContext("state.view",context),"overview");
  assert.equal(node("task-dialog").open,true);
  assert.equal(getScrollCount(),0);
});

test("Native dialog has accessible title, close control and keyboard behavior", () => {
  assert.match(html,/<dialog id="task-dialog"[^>]*aria-labelledby="task-dialog-title"/);
  assert.match(html,/<h2 id="task-dialog-title">Chi tiết tác vụ<\/h2>/);
  assert.match(html,/id="task-dialog-close"/);
  assert.match(html,/id="task-dialog-body"/);
  assert.match(script,/taskDialog\.addEventListener\("close"/);
});
