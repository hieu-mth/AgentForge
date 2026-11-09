import test from 'node:test';
import assert from 'node:assert/strict';
import { compatibleProfiles, exposureFor, profilePayload, KIND_LABELS,
  STATUS_LABELS } from '../src/model_hub_ui.js';
import { groupFor, hashFor, parseSection } from '../src/navigation.js';

const profiles=[
  {id:'local_primary',provider:'ollama',enabled:true},
  {id:'cloud_primary',provider:'anthropic',enabled:true},
  {id:'video',provider:'comfyui',enabled:true},
  {id:'disabled',provider:'ollama',enabled:false},
];

test('route capability prevents selecting a video engine for coding',()=>{
  assert.deepEqual(compatibleProfiles({kind:'text'},profiles).map(p=>p.id),
    ['local_primary','cloud_primary']);
  assert.deepEqual(compatibleProfiles({kind:'video'},profiles).map(p=>p.id),
    ['video']);
  assert.deepEqual(compatibleProfiles({kind:'image'},profiles).map(p=>p.id),
    ['video']);
  assert.deepEqual(compatibleProfiles({kind:'rules'},profiles),[]);
});
test('cloud and config-only media always show explicit risk',()=>{
  assert.match(exposureFor(profiles[1]),/Cloud/);
  assert.match(exposureFor(profiles[2]),/chưa chạy model/);
  assert.match(exposureFor(profiles[0]),/chưa tự gọi inference/);
  assert.match(STATUS_LABELS.CONFIG_ONLY,/chưa nối runtime/);
  assert.match(STATUS_LABELS.DETERMINISTIC,/không cần AI/);
  assert.equal(KIND_LABELS.rules,'Python rules');
});
test('profile form never sends unrelated fields or token values',()=>{
  const cloud=profilePayload({
    id:'  team_cloud ',provider:'anthropic',model:' claude-test ',
    api_key_env:' ANTHROPIC_AUTH_TOKEN ',base_url_env:' ANTHROPIC_BASE_URL ',
    base_url:'http://evil.example',secret:'should-not-leak',enabled:true,
  });
  assert.deepEqual(cloud,{
    id:'team_cloud',provider:'anthropic',model:'claude-test',
    api_key_env:'ANTHROPIC_AUTH_TOKEN',base_url_env:'ANTHROPIC_BASE_URL',
    enabled:true,
  });
  const local=profilePayload({id:'studio_local',provider:'comfyui',
    model:'wan2.2_5b',enabled:false,base_url:'http://127.0.0.1:8188',
    api_key_env:'SHOULD_NEVER_STORE'});
  assert.equal(local.base_url,'http://127.0.0.1:8188');
  assert.equal(local.enabled,false);
  assert.ok(!('api_key_env' in local));
});
test('Owner settings deep-link includes Model Hub',()=>{
  assert.equal(groupFor('models'),'settings');
  assert.equal(hashFor('models'),'#/models');
  assert.equal(parseSection('#/models'),'models');
});
