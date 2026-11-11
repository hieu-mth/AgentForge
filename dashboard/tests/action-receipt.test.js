import test from 'node:test';
import assert from 'node:assert/strict';
import { actionWithRefresh } from '../src/action_receipt.js';

test('a committed receipt survives a failed dashboard refresh without replay',async()=>{
  const receipt={goal_id:'abc',status:'PLAN_CREATED'};
  let posts=0,refreshes=0;
  const warnings=[];
  const actual=await actionWithRefresh(async()=>{posts++;return receipt;},
    async()=>{refreshes++;throw new Error('GET failed');},
    error=>warnings.push(error.message));
  assert.strictEqual(actual,receipt);
  assert.equal(posts,1);
  assert.equal(refreshes,1);
  assert.deepEqual(warnings,['GET failed']);
});
test('a failed POST does not report success or run GET',async()=>{
  let refreshed=false,notified=false;
  await assert.rejects(()=>actionWithRefresh(
    async()=>{throw new Error('write rejected')},
    async()=>{refreshed=true},()=>{notified=true}),/write rejected/);
  assert.equal(refreshed,false);assert.equal(notified,false);
});
test('receipt is returned normally when refresh succeeds or is disabled',async()=>{
  const receipt={status:'SUCCEEDED'};
  assert.strictEqual(await actionWithRefresh(async()=>receipt,async()=>{}),receipt);
  assert.strictEqual(await actionWithRefresh(async()=>receipt,null),receipt);
});
