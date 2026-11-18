import test from 'node:test';
import assert from 'node:assert/strict';
import {formatCapacity,formatMemory,formatVram,percentUsed,formatChecked,displayStatus,statusTone} from '../src/environment_format.js';

test('environment never invents missing hardware metrics',()=>{
  assert.equal(formatCapacity(null),'Chưa xác định');
  assert.equal(formatCapacity(undefined),'Chưa xác định');
  assert.equal(formatCapacity(NaN),'Chưa xác định');
  assert.equal(formatCapacity(-3),'Chưa xác định');
  assert.equal(formatVram(null),'—');
  assert.equal(formatVram(0),'0 MB');
  assert.equal(percentUsed(undefined,12288),null);
  assert.equal(percentUsed(12289,12288),null);
  assert.equal(percentUsed(0,0),null);
  assert.equal(formatChecked('not-a-date'),'Chưa có dữ liệu');
});
test('environment resource proportions use genuine free versus total',()=>{
  assert.equal(percentUsed(8,10),20);
  assert.equal(percentUsed(10,10),0);
  assert.equal(percentUsed(0,10),100);
  assert.equal(formatMemory(32*1024**3),'32 GB');
  assert.equal(formatCapacity(500_000_000),'500 MB');
  assert.equal(formatCapacity(1_000_000_000),'1 GB');
  assert.equal(formatVram(12227),'11,94 GB');
  assert.equal(formatVram(8673),'8,47 GB');
  assert.equal(formatVram(512),'512 MB');
  assert.equal(formatCapacity(1_000_190_000_000),'1 TB');
  assert.equal(formatCapacity(696_990_000_000),'696,99 GB');
  assert.equal(formatMemory(31.77*1024**3),'31,77 GB');
  assert.equal(formatMemory(512*1024**2),'512 MB');
  assert.equal(formatMemory(2*1024**4),'2 TB');
  assert.equal(formatCapacity(1_999),'2 KB');
  assert.equal(formatCapacity(0),'0 MB');
  assert.equal(formatMemory(-1),'Chưa xác định');
});
test('degraded ComfyUI is never shown as healthy',()=>{
  assert.equal(statusTone('DEGRADED'),'warn');
  assert.equal(displayStatus('DEGRADED'),'Gián đoạn');
  assert.equal(statusTone('UNAVAILABLE'),'bad');
  assert.equal(statusTone('READY'),'good');
  assert.equal(displayStatus('UNKNOWN'),'Chưa xác minh');
});
