import test from 'node:test';
import assert from 'node:assert/strict';
import { profilePayload } from '../src/model_hub_ui.js';
import { groupFor, hashFor, parseSection } from '../src/navigation.js';

test('profile form never sends unrelated fields or token values',()=>{
  const cloud=profilePayload({
    id:'  team_cloud ',provider:'anthropic',model:' claude-test ',
    api_key_env:' ANTHROPIC_AUTH_TOKEN ',base_url_env:' ANTHROPIC_BASE_URL ',
    base_url:'http://evil.example',secret:'should-not-leak',enabled:true,
  },{id:'anthropic',defaults:{base_url_env:'',api_key_env:''}});
  assert.deepEqual(cloud,{
    id:'team_cloud',provider:'anthropic',model:'claude-test',
    api_key_env:'ANTHROPIC_AUTH_TOKEN',base_url_env:'ANTHROPIC_BASE_URL',
    enabled:true,
  });
  const local=profilePayload({id:'studio_local',provider:'comfyui',
    model:'wan2.2_5b',enabled:false,base_url:'http://127.0.0.1:8188',
    api_key_env:'SHOULD_NEVER_STORE'},{id:'comfyui',defaults:{base_url:''}});
  assert.equal(local.base_url,'http://127.0.0.1:8188');
  assert.equal(local.enabled,false);
  assert.ok(!('api_key_env' in local));
});
test('FLUX workflow is sent only for an advertising ComfyUI backend',()=>{
  const values={id:'flux_schnell_gguf',model:'flux1-schnell-Q4_K_S.gguf',enabled:true,
    base_url:'http://127.0.0.1:8188',flux_enabled:true,flux_settings:{
      workflow:'{"38":{"class_type":"UnetLoaderGGUF"}}',max_resolution:1024,max_steps:4,
      timeout_seconds:180,output_dir:'visuals',api_key:'fixture-key',
    }};
  const adapter={id:'comfyui',defaults:{base_url:''}};
  assert.ok(!('flux' in profilePayload(values,adapter)));
  assert.deepEqual(profilePayload(values,{...adapter,flux_workflow_max_bytes:16000}).flux,{
    workflow:{38:{class_type:'UnetLoaderGGUF'}},max_resolution:1024,max_steps:4,
    timeout_seconds:180,output_dir:'visuals',
  });
});

test('Owner settings deep-link includes Model Hub',()=>{
  assert.equal(groupFor('models'),'settings');
  assert.equal(hashFor('models'),'#/models');
  assert.equal(parseSection('#/models'),'models');
});
