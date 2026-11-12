import test from 'node:test';
import assert from 'node:assert/strict';
import {formatVietnamDateTime} from '../src/date_format.js';
test('UTC microsecond timestamp renders as Vietnam time',()=>{
  assert.equal(formatVietnamDateTime('2026-11-11T10:31:19.524740+00:00'),'17:31 · 11/11/2026');
});
test('timezone rollover is correct',()=>{
  assert.equal(formatVietnamDateTime('2026-11-11T20:00:00Z'),'03:00 · 12/11/2026');
});
test('invalid and absent timestamps are safe',()=>{
  assert.equal(formatVietnamDateTime(null),'Chưa có thời gian');
  assert.equal(formatVietnamDateTime('invalid'),'Thời gian không hợp lệ');
});
