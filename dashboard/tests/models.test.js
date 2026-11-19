import test from 'node:test';
import assert from 'node:assert/strict';
import { exposureFor, profilePayload } from '../src/model_hub_ui.js';
import { groupFor, hashFor, parseSection } from '../src/navigation.js';

test('cloud and config-only media always show explicit risk',()=>{
  assert.match(exposureFor({provider:'anthropic'}),/Cloud/);
  assert.match(exposureFor({provider:'comfyui'}),/chưa chạy model/);
  assert.match(exposureFor({provider:'ollama'}),/chưa tự gọi inference/);
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
