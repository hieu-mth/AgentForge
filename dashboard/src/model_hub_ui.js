// Serialize only paths declared by the selected backend adapter.
const getPath=(object,path)=>path.reduce((value,key)=>value?.[key],object);
function setPath(object,path,value){
  let target=object;
  for(const key of path.slice(0,-1))target=target[key]??={};
  target[path.at(-1)]=value;
}
export function optionVariants(adapter){
  return adapter?.profile_schema?.option_variants??[];
}
export function optionValues(adapter,profile){
  const variants=optionVariants(adapter);
  const roots=new Set(variants.flatMap(v=>v.fields.map(f=>f.path[0])));
  const saved=[...roots].filter(key=>Object.hasOwn(profile??{},key));
  const selected=variants.find(v=>{
    const keys=[...new Set(v.fields.map(f=>f.path[0]))];
    return keys.length===saved.length&&keys.every(k=>saved.includes(k));
  })??variants[0];
  const options={};
  for(const variant of variants)for(const field of variant.fields){
    const value=getPath(profile,field.path)??field.default;
    if(value!==undefined)setPath(options,field.path,field.kind==='json'?JSON.stringify(value,null,2):value);
  }
  return {option_variant:selected?.id,adapter_options:options};
}
export function profilePayload(values,adapter) {
  const profile={id:values.id?.trim(),provider:adapter.id,
    model:values.model?.trim(),enabled:values.enabled===true};
  for(const key of Object.keys(adapter.defaults))profile[key]=values[key]?.trim();
  const variants=optionVariants(adapter);
  const selected=variants.find(v=>v.id===values.option_variant);
  if(variants.length&&!selected)throw new Error('Chọn loại cấu hình runtime.');
  for(const field of selected?.fields??[]){
    const raw=getPath(values.adapter_options,field.path);
    if(raw===undefined||raw===null||(typeof raw==='string'&&!raw.trim())){
      if(field.required)throw new Error('Hãy điền '+field.label+'.');
      continue;
    }
    const value=field.kind==='json'?JSON.parse(raw):field.kind==='text'?raw.trim():raw;
    setPath(profile,field.path,value);
  }
  return profile;
}

export const readinessLabels={
  NOT_CHECKED:'Chưa kiểm tra',UNAVAILABLE:'Runtime không khả dụng',
  UNSUPPORTED:'Không hỗ trợ',MISSING_DEPENDENCY:'Thiếu điều kiện',
  METADATA_COMPATIBLE:'Metadata tương thích',
};

const readinessReasons={
  DISABLED:'Hồ sơ đang tắt.',INVALID_ENDPOINT:'Endpoint HTTPS không hợp lệ.',RATE_OR_QUOTA_LIMIT:'API giới hạn lượt gọi hoặc hết quota.',ACCESS_DENIED:'API từ chối quyền truy cập.',MODEL_OR_ENDPOINT_NOT_FOUND:'Không tìm thấy model hoặc endpoint metadata; có thể thử inference riêng.',PAYMENT_REQUIRED:'API yêu cầu thanh toán.',
  COMFYUI_UNAVAILABLE:'Không kết nối được ComfyUI.',UNAVAILABLE:'Không kết nối được runtime local.',
  MODEL_NOT_INSTALLED:'Ollama chưa có model này.',MODEL_UNAVAILABLE:'ComfyUI thiếu một hoặc nhiều weights.',
  WORKFLOW_NODE_UNAVAILABLE:'ComfyUI thiếu node hoặc input của workflow ảnh.',
  GPU_UNAVAILABLE:'Runtime không báo GPU CUDA.',MOTION_ENDPOINT_MISMATCH:'Endpoint không khớp preset Motion.',
  MOTION_WORKFLOW_UNAVAILABLE:'Preset LTX thiếu node, input hoặc weights trong ComfyUI.',
  MOTION_LAUNCHER_REQUIRED:'Chưa đăng ký thư mục Portable cho endpoint Motion.',
  MOTION_WEIGHTS_UNAVAILABLE:'Thiếu checkpoint hoặc encoder LTX đúng tên và kích thước.',
  MEDIA_TOOLS_UNAVAILABLE:'Thiếu FFmpeg hoặc ffprobe.',FLUX_WORKFLOW_REQUIRED:'Cần workflow ảnh ComfyUI tương thích.',
  MOTION_PROFILE_INCOMPATIBLE:'Checkpoint hoặc encoder không khớp adapter chuyển động.',
  TEXT_ADAPTER_REQUIRED:'Chưa có adapter văn bản tương thích.',
  VISION_ADAPTER_UNAVAILABLE:'Chưa có adapter kiểm tra hình ảnh.',
  COMFYUI_TIMEOUT:'ComfyUI phản hồi quá thời gian chờ.',COMFYUI_HTTP_ERROR:'ComfyUI từ chối yêu cầu metadata.',
  AUTH_REQUIRED:'Chưa kết nối hoặc endpoint yêu cầu xác thực.',AUDIO_GENERATION_NOT_PROBED:'Chưa thử sinh âm thanh.',CLOUD_VIDEO_NOT_PROBED:'Chưa thử sinh video cloud.',CLOUD_IMAGE_NOT_PROBED:'Chưa thử sinh ảnh cloud.',HTTP_ERROR:'Endpoint từ chối yêu cầu metadata.',
  INVALID_RESPONSE:'Endpoint trả metadata không hợp lệ.',
  COMFYUI_INVALID_RESPONSE:'ComfyUI trả metadata không hợp lệ.',
};

export const readinessReason=code=>readinessReasons[code]??code;
export function profileCapability(profile) {
  const contracts=profile.capability_contracts??[];
  return (contracts.find(item=>item.runtime_compatible||item.local_runtime_compatible)??contracts.find(item=>item.route_configurable)
    ??contracts.find(item=>item.capability===(profile.provider==='comfyui'?
      (profile.motion_encoder?'film.motion':'image.generate'):'general.text')));
}

export function configurableProfiles(profiles,capability) {
  return profiles.filter(profile=>profile.capability_contracts?.some(
    item=>item.capability===capability&&item.route_configurable===true));
}

export function outputSummary(limits) {
  if(!limits)return null;
  if(limits.resolution)return `${limits.resolution.join(' × ')} px · ${limits.fps} FPS · tối đa ${limits.max_frames} frame/clip`;
  if(limits.size)return limits.size+' · '+(limits.ratios??[]).join(' / ');
  if(limits.max_resolution)return `${limits.min_resolution}–${limits.max_resolution} px mỗi cạnh · tối đa ${limits.max_steps} bước`;
  return limits.format==='structured_json'?'JSON có cấu trúc':limits.format;
}
