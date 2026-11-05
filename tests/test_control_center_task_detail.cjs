/* Regression: selecting a task must retain details through navigation.
   Uses a tiny fake DOM and Node vm; no browser, npm or third-party packages. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const appPath = path.join(__dirname, "..", "src", "agentforge",
                          "control_center_static", "app.js");
const script = fs.readFileSync(appPath, "utf8");

function runtime(task) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) {
      nodes.set(id, {
        innerHTML: "", textContent: "", hidden: true,
        classList: {add() {}, remove() {}, toggle() {}},
        addEventListener() {},
      });
    }
    return nodes.get(id);
  };
  const calls = [];
  const context = vm.createContext({
    document: {
      addEventListener() {},
      getElementById: node,
      querySelectorAll() {return [];},
    },
    window: {scrollTo() {}},
    fetch: async (route) => {
      calls.push(route);
      return {ok: true, text: async () => JSON.stringify(task)};
    },
    console,
    setTimeout,
  });
  vm.runInContext(script, context, {filename: appPath});
  vm.runInContext("state.data = " + JSON.stringify({
    tasks: [{
      task_id: task.task_id, kind: "skill", skill_id: task.skill_id,
      status: task.status, updated_at: "2026-11-05T10:00:00Z",
    }],
    goals: [],
    templates: {},
  }), context);
  return {context, node, calls};
}

test("Task History click retains a FAILED task and visibly shows its error", async () => {
  const taskId = "a".repeat(32);
  const task = {
    task_id: taskId, kind: "skill", skill_id: "analytics.quality_check",
    status: "FAILED",
    error: "Dataset not found: demo-example",
    artifacts: [], events: [{at: "2026-11-05T10:00:00Z", name: "FAILED"}],
  };
  const {context, node, calls} = runtime(task);
  await vm.runInContext('showTask("' + taskId + '")', context);
  assert.deepEqual(calls, ["/api/tasks/" + taskId]);
  assert.equal(vm.runInContext("state.view", context), "tasks");
  assert.equal(vm.runInContext("state.task.task_id", context), taskId);
  const page = node("content").innerHTML;
  assert.match(page, /Task details/);
  assert.match(page, /analytics\.quality_check/);
  assert.match(page, /Dataset not found: demo-example/);
  assert.match(page, /FAILED/);
});

test("Server-supplied failure text is escaped, never injected as HTML", async () => {
  const task = {
    task_id: "b".repeat(32), kind: "skill",
    skill_id: "analytics.quality_check",
    status: "FAILED", error: '<img src=x onerror=alert("XSS")>',
    events: [], artifacts: [],
  };
  const {context, node} = runtime(task);
  await vm.runInContext('showTask("' + task.task_id + '")', context);
  const page = node("content").innerHTML;
  assert.match(page, /&lt;img src=x onerror=alert/);
  assert.doesNotMatch(page, /<img src=x onerror=/);
});

test("Task details persist after refreshing task list without losing selection", async () => {
  const task = {
    task_id: "c".repeat(32), kind: "skill", skill_id: "analytics.content_report",
    status: "SUCCEEDED", error: null,
    events: [{at: "2026-11-05", name: "SUCCEEDED"}],
    artifacts: [],
  };
  const {context, node} = runtime(task);
  await vm.runInContext('showTask("' + task.task_id + '")', context);
  vm.runInContext("render()", context);
  assert.match(node("content").innerHTML, /Task details/);
  assert.equal(vm.runInContext("state.task.status", context), "SUCCEEDED");
});
