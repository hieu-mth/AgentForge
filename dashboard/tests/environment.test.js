import test from 'node:test';
import assert from 'node:assert/strict';
import {formatGiB,formatMiB,percentUsed,formatChecked,displayStatus,statusTone} from '../src/environment_format.js';

test('environment never invents missing hardware metrics',()=>{
  assert.equal(formatGiB(null),'Chưa xác định');
  assert.equal(formatGiB(undefined),'Chưa xác định');
  assert.equal(formatGiB(NaN),'Chưa xác định');
  assert.equal(formatGiB(-3),'Chưa xác định');
  assert.equal(formatMiB(null),'—');
  assert.equal(formatMiB(0),'0 MiB');
  assert.equal(percentUsed(undefined,12288),null);
  assert.equal(percentUsed(12289,12288),null);
  assert.equal(percentUsed(0,0),null);
  assert.equal(formatChecked('not-a-date'),'Chưa có dữ liệu');
});
test('environment resource proportions use genuine free versus total',()=>{
  assert.equal(percentUsed(8,10),20);
  assert.equal(percentUsed(10,10),0);
  assert.equal(percentUsed(0,10),100);
  assert.equal(formatGiB(32*1024**3),'32 GiB');
});
test('degraded ComfyUI is never shown as healthy',()=>{
  assert.equal(statusTone('DEGRADED'),'warn');
  assert.equal(displayStatus('DEGRADED'),'Gián đoạn');
  assert.equal(statusTone('UNAVAILABLE'),'bad');
  assert.equal(statusTone('READY'),'good');
  assert.equal(displayStatus('UNKNOWN'),'Chưa xác minh');
});
