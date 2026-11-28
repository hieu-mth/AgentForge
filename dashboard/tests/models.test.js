import test from 'node:test';
import assert from 'node:assert/strict';
import { configurableProfiles, outputSummary, profileCapability, profilePayload, optionValues, readinessLabels } from '../src/model_hub_ui.js';
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
test('profile option fields follow advertised variant without inspecting graph class or provider name',()=>{
  const adapter={id:'future_runtime',defaults:{base_url:''},profile_schema:{option_variants:[
    {id:'metadata',fields:[]},
    {id:'image',fields:[
      {path:['custom_image','workflow'],kind:'json',required:true,label:'Graph'},
      {path:['custom_image','max_steps'],kind:'integer',default:4,required:true,label:'Steps'},
    ]},
    {id:'video',fields:[{path:['encoder'],kind:'text',required:true,label:'Encoder'},{path:['video'],kind:'json',required:true,label:'Video'}]},
  ]}};
  const saved={id:'fixture',model:'alternate.safetensors',enabled:true,base_url:'http://127.0.0.1:8188',
    custom_image:{workflow:{38:{class_type:'CheckpointLoaderSimple'}},max_steps:7}};
  const form={...saved,...optionValues(adapter,saved)};
  assert.equal(form.option_variant,'image');
  form.adapter_options.encoder='should not leak';
  assert.deepEqual(profilePayload(form,adapter),{...saved,provider:adapter.id});
  assert.deepEqual(profilePayload({...form,option_variant:'metadata'},adapter),
    {id:saved.id,model:saved.model,enabled:true,base_url:saved.base_url,provider:adapter.id});
  assert.throws(()=>profilePayload({...form,option_variant:'video'},adapter),/Hãy điền/);
  assert.throws(()=>profilePayload({...form,option_variant:'unknown'},adapter),/Chọn loại/);
  assert.deepEqual(profilePayload({...form,option_variant:'video',adapter_options:{encoder:' C:/encoder.safetensors ',video:'{"format":"test"}'}},adapter),
    {id:saved.id,model:saved.model,enabled:true,base_url:saved.base_url,provider:adapter.id,encoder:'C:/encoder.safetensors',video:{format:'test'}});
});
test('single metadata variant does not require a hidden selector value',()=>{
  const adapter={id:'fixture',defaults:{base_url:''},profile_schema:{option_variants:[{id:'metadata',fields:[]}]}};
  assert.deepEqual(profilePayload({id:'fixture',model:'test',enabled:true,base_url:'http://127.0.0.1:8188'},adapter),
    {id:'fixture',model:'test',provider:'fixture',enabled:true,base_url:'http://127.0.0.1:8188'});
});
test('Owner settings deep-link includes Model Hub',()=>{
  assert.equal(groupFor('models'),'settings');
  assert.equal(hashFor('models'),'#/models');
  assert.equal(parseSection('#/models'),'models');
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

import { productionMethodOptions, cloudSecondsBounds, durationBounds, storyboardShotLimits, cloudSecondsRemainingEstimate } from '../src/features/studioDuration.js';
test('production options follow backend capability snapshot rather than version names',()=>{
  const hub={production_options:{methods:[{id:'assigned',available:false},{id:'auto',available:true},
    {id:'cloud',available:true},{id:'hybrid',available:false}],min_cloud_seconds:12,
    max_cloud_seconds:240,auto_min_cloud_seconds:12,duration_bounds:{motion:{min:5,max:55}}}};
  assert.deepEqual(productionMethodOptions(hub).map(x=>[x.value,x.disabled]),
    [['assigned',true],['auto',false],['cloud',false],['hybrid',true]]);
  assert.deepEqual(cloudSecondsBounds(hub,'auto'),{min:12,max:240});
  assert.deepEqual(durationBounds(hub,'motion'),{min:5,max:55});
  assert.equal(durationBounds({},'motion'),null);
  assert.equal(cloudSecondsBounds({},'cloud'),null);
  assert.deepEqual(storyboardShotLimits({brief:{mode:'motion',seconds:15}}),[0,0]);
  assert.deepEqual(storyboardShotLimits({editor_constraints:{layout_editable:true,min_scenes:3,max_scenes:12}}),[3,12]);
  assert.equal(cloudSecondsRemainingEstimate({cloud_seconds_remaining:14}),14);
  assert.equal(cloudSecondsRemainingEstimate({}),null);
  assert.equal(cloudSecondsRemainingEstimate({cloud_seconds_remaining:0}),0);
});

test('planning-only method stays selectable and is distinguished from execution readiness',()=>{
  const [option]=productionMethodOptions({production_options:{methods:[{id:'cloud',available:true,execution_ready:false}]}});
  assert.equal(option.disabled,false);
  assert.match(option.label,/Chỉ lập storyboard/);
});
