import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isCompanyRequest, modelCallsForPrompt, normalizedRequest, quotaForPrompt,
} from '../src/workspace_quota.js';

const fourRoles = 'Tạo ứng dụng React quản lý cửa hàng demo. Yêu cầu AI Architect lập kiến trúc, AI Developer viết component, QA kiểm tra tĩnh và AI Reviewer phản biện kết quả.';

test('V5 four-role prompt requires three model calls without magic prefix', () => {
  assert.equal(isCompanyRequest(fourRoles), true);
  assert.equal(modelCallsForPrompt(fourRoles), 3);
  assert.equal(modelCallsForPrompt('AI Company V5: làm React app local'), 3);
  assert.equal(modelCallsForPrompt('Công ty AI V5: tạo prototype'), 3);
  assert.equal(normalizedRequest('KIỂM THỬ ĐẦY ĐỦ'), 'kiem thu day du');
});

test('single-role and ordinary website remain one call, not elevated by accident', () => {
  for (const text of [
    'AI Developer: Viết React web app tùy biến',
    'Tạo landing page bán nệm responsive',
    'AI Architect thiết kế phần mềm rồi QA kiểm tra',
    'AI Developer viết mã và AI Reviewer xem lại',
  ]) {
    assert.equal(modelCallsForPrompt(text), 1, text);
  }
});

test('policy cap is checked client-side without changing Owner limits', () => {
  const policy={max_estimated_model_calls:1,website_enabled:true};
  const blocked=quotaForPrompt(fourRoles,policy);
  assert.deepEqual(blocked, {
    required:3,allowed:1,blocked:true,isCompany:true,
  });
  assert.equal(policy.max_estimated_model_calls,1);
  assert.deepEqual(quotaForPrompt(fourRoles,{max_estimated_model_calls:3}),{
    required:3,allowed:3,blocked:false,isCompany:true,
  });
  assert.equal(quotaForPrompt('Tạo landing page cho nệm',policy).blocked,false);
  assert.equal(quotaForPrompt(fourRoles,undefined).blocked,true);
});

test('the UI guard handles an Owner who explicitly turns off prompt model use',()=>{
  assert.deepEqual(quotaForPrompt('Tạo landing page', {max_estimated_model_calls:0}),{
    required:1,allowed:0,blocked:true,isCompany:false,
  });
  assert.equal(quotaForPrompt(fourRoles,{max_estimated_model_calls:2}).blocked,true);
});
