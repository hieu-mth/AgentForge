import test from 'node:test';
import assert from 'node:assert/strict';
import {parseSection, hashFor, groupFor} from '../src/navigation.js';
test('video project navigation and retired workspace',()=>{
  assert.equal(parseSection('#/projects'),'projects');
  assert.equal(groupFor('projects'),'products');
  assert.equal(parseSection('#/workspace'),'overview');
  assert.equal(hashFor('workspace'),'#/overview');
});

import {productionUsage} from '../src/features/productionUsage.js';
test('production usage counts reserved calls and seconds without estimating spend',()=>{
  const start='2026-11-26T00:00:00Z';
  const result=productionUsage([
    {status:'APPROVED',cloud_calls:3,cloud_motion_seconds:12,attempt_started_at:start,attempt_finished_at:'2026-11-26T00:00:20Z'},
    {status:'FAILED',cloud_calls:2,cloud_motion_seconds:6,attempt_started_at:start,attempt_finished_at:'2026-11-26T00:00:40Z'},
    {status:'RUNNING',cloud_calls:1,attempt_started_at:start},
  ]);
  assert.deepEqual(result,{count:3,approved:1,cloudCalls:6,cloudSeconds:18,medianAttemptSeconds:30});
  assert.equal(productionUsage([]).medianAttemptSeconds,null);
});
