import test from 'node:test';
import assert from 'node:assert/strict';
import { configurableProfiles, outputSummary, profileCapability, profilePayload, readinessLabels } from '../src/model_hub_ui.js';
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

test('LTX encoder is sent only for a compatible ComfyUI adapter',()=>{
  const values={id:'motion_profile',model:'ltxv-2b-0.9.8-distilled-fp8.safetensors',
    enabled:true,base_url:'http://127.0.0.1:8188',motion_encoder:' C:/models/t5.safetensors '};
  const adapter={id:'comfyui',defaults:{base_url:''}};
  assert.ok(!('motion_encoder' in profilePayload(values,adapter)));
  assert.equal(profilePayload(values,{...adapter,motion_encoder_supported:true}).motion_encoder,
    'C:/models/t5.safetensors');
});

test('routing follows revision catalog contracts and preserves cloud configuration-only routes',()=>{
  const cloud={id:'cloud',capability_contracts:[
    {capability:'general.text',route_configurable:true,local_runtime_compatible:false},
    {capability:'film.motion',route_configurable:false},
  ]};
  const disabled={id:'disabled',capability_contracts:[
    {capability:'general.text',route_configurable:false,local_runtime_compatible:true},
  ]};
  assert.deepEqual(configurableProfiles([disabled,cloud],'general.text'),[cloud]);
  assert.deepEqual(configurableProfiles([disabled,cloud],'film.motion'),[]);
  assert.equal(profileCapability(cloud).capability,'general.text');
  assert.equal(outputSummary({resolution:[512,288],fps:24,max_frames:49}),'512 × 288 px · 24 FPS · tối đa 49 frame/clip');
  assert.equal(readinessLabels.METADATA_COMPATIBLE,'Metadata tương thích');
});

import { productionMethodOptions, cloudSecondsBounds, storyboardShotLimits, cloudSecondsRemainingEstimate } from '../src/features/studioDuration.js';
test('production options follow backend capability snapshot rather than version names',()=>{
  const hub={production_options:{methods:[{id:'assigned',available:false},{id:'auto',available:true},
    {id:'cloud',available:true},{id:'hybrid',available:false}],min_cloud_seconds:12,
    max_cloud_seconds:240,auto_min_cloud_seconds:12}};
  assert.deepEqual(productionMethodOptions(hub).map(x=>[x.value,x.disabled]),
    [['assigned',true],['auto',false],['cloud',false],['hybrid',true]]);
  assert.deepEqual(cloudSecondsBounds(hub,'auto'),{min:12,max:240});
  assert.deepEqual(storyboardShotLimits({brief:{mode:'motion',seconds:15}}),[8,9]);
  assert.deepEqual(storyboardShotLimits({brief:{mode:'motion',seconds:24,duration_mode:'auto'},
    motion_plan:{output:{fps:24,max_frames:240}}}),[3,16]);
  assert.equal(cloudSecondsRemainingEstimate({production_plan:{method:'cloud',billable_durations_seconds:[6,8,10]},
    motion_plan:{output:{fps:24}},board:{scenes:[{frames:145},{frames:240,motion_job:'done'},{frames:48}]}}),14);
});

test('planning-only method stays selectable and is distinguished from execution readiness',()=>{
  const [option]=productionMethodOptions({production_options:{methods:[{id:'cloud',available:true,execution_ready:false}]}});
  assert.equal(option.disabled,false);
  assert.match(option.label,/Chỉ lập storyboard/);
});
