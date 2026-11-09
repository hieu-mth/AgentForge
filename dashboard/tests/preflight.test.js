import test from 'node:test';
import assert from 'node:assert/strict';
import { preflightTone, preflightLabel } from '../src/ops_preflight_ui.js';
test('environment checks never claim model/GPU health',()=>{
  assert.equal(preflightLabel('READY_LOCAL_UNVERIFIED'),'Sẵn sàng local (chưa thử model)');
  assert.match(preflightLabel('AVAILABLE_UNVERIFIED'),/chưa xác minh/);
  assert.equal(preflightTone('BLOCKED'),'error');
  assert.equal(preflightTone('NEEDS_SETUP'),'warning');
  assert.equal(preflightTone('READY'),'success');
  assert.equal(preflightLabel('OWNER_REVIEW_REQUIRED'),'Chờ nghiệm thu máy thật');
});
