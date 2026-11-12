import test from 'node:test';
import assert from 'node:assert/strict';
import { buildOverview } from '../src/overview_data.js';

test('missing bootstrap does not invent activity or attention',()=>{
  const s=buildOverview(null,new Date('2026-11-12T10:00:00Z'));
  assert.deepEqual(s.counts,{running:0,waiting:0,doneToday:0,problems:0});
  assert.deepEqual(s.issues,[]);
  assert.deepEqual(s.recent,[]);
});
test('owner inbox combines distinct sources and routes to real pages',()=>{
  const s=buildOverview({
    tasks:[{task_id:'t1',skill_id:'media.copy',status:'RUNNING',updated_at:'2026-11-12T09:00:00Z'},
      {task_id:'t2',skill_id:'web.create',status:'FAILED',updated_at:'2026-11-11T09:00:00Z'}],
    goals:[{goal_id:'g1',status:'WAITING_APPROVAL'}],
    attention:[{kind:'goal',id:'g1',status:'WAITING_APPROVAL',priority:'HIGH',title:'Duyệt kế hoạch'}],
    autopilot_reviews:{items:[{job_id:'j1',decision:'PENDING'}]},
    local_video:{items:[{production_id:'p1',status:'VIDEO_READY'}]},
  },new Date('2026-11-12T10:00:00Z'));
  assert.equal(s.counts.running,1);
  assert.equal(s.counts.waiting,3);
  assert.equal(s.counts.problems,1);
  assert.deepEqual(s.issues.map(x=>x.section),['goals','reviews','reviews','tasks']);
  assert.equal(s.trend.length,7);
  assert.equal(s.recent[0].task_id,'t1');
});
test('sample scope never implies full historical totals',()=>{
  const s=buildOverview({tasks:[{task_id:'a',status:'SUCCEEDED',updated_at:'2026-11-12T08:00:00Z'}]},
    new Date('2026-11-12T10:00:00Z'));
  assert.equal(s.scope.tasks,1);
  assert.equal(s.counts.doneToday,1);
});
