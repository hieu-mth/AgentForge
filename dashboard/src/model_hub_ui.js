// Serialize only fields declared by the selected backend adapter.
export function profilePayload(values,adapter) {
  const profile={id:values.id?.trim(),provider:adapter.id,
    model:values.model?.trim(),enabled:values.enabled===true};
  for(const key of Object.keys(adapter.defaults))profile[key]=values[key]?.trim();
  if(adapter.id==='comfyui'&&adapter.flux_workflow_max_bytes&&values.flux_enabled) {
    const {workflow,max_resolution,max_steps,timeout_seconds,output_dir}=values.flux_settings;
    profile.flux={workflow:JSON.parse(workflow),max_resolution,max_steps,timeout_seconds,output_dir};
  } else if(adapter.id==='comfyui'&&adapter.motion_encoder_supported&&values.motion_encoder?.trim()) {
    profile.motion_encoder=values.motion_encoder.trim();
  }
  return profile;
}

export const readinessLabels={
  NOT_CHECKED:'Chưa kiểm tra',UNAVAILABLE:'Runtime không khả dụng',
  UNSUPPORTED:'Không hỗ trợ',MISSING_DEPENDENCY:'Thiếu điều kiện',
  METADATA_COMPATIBLE:'Metadata tương thích',
};

const readinessReasons={
  DISABLED:'Hồ sơ đang tắt.',CLOUD_PREFLIGHT_UNSUPPORTED:'Chưa xác minh kết nối. Kiểm tra chỉ hỗ trợ runtime local.',
  COMFYUI_UNAVAILABLE:'Không kết nối được ComfyUI.',UNAVAILABLE:'Không kết nối được runtime local.',
  MODEL_NOT_INSTALLED:'Ollama chưa có model này.',MODEL_UNAVAILABLE:'ComfyUI thiếu một hoặc nhiều weights.',
  WORKFLOW_NODE_UNAVAILABLE:'ComfyUI thiếu node hoặc input của workflow FLUX.',
  GPU_UNAVAILABLE:'Runtime không báo GPU CUDA.',MOTION_ENDPOINT_MISMATCH:'Endpoint không khớp preset Motion.',
  MOTION_WORKFLOW_UNAVAILABLE:'Preset LTX thiếu node, input hoặc weights trong ComfyUI.',
  MOTION_LAUNCHER_REQUIRED:'Chưa đăng ký thư mục Portable cho endpoint Motion.',
  MOTION_WEIGHTS_UNAVAILABLE:'Thiếu checkpoint hoặc encoder LTX đúng tên và kích thước.',
  MEDIA_TOOLS_UNAVAILABLE:'Thiếu FFmpeg hoặc ffprobe.',FLUX_WORKFLOW_REQUIRED:'Cần workflow FLUX GGUF tương thích.',
  MOTION_PROFILE_INCOMPATIBLE:'Checkpoint hoặc encoder không khớp adapter chuyển động.',
  LOCAL_TEXT_ADAPTER_REQUIRED:'Tác vụ văn bản local cần adapter Ollama.',
  VISION_ADAPTER_UNAVAILABLE:'Chưa có adapter kiểm tra hình ảnh.',
  COMFYUI_TIMEOUT:'ComfyUI phản hồi quá thời gian chờ.',COMFYUI_HTTP_ERROR:'ComfyUI từ chối yêu cầu metadata.',
  AUTH_REQUIRED:'Endpoint yêu cầu xác thực.',HTTP_ERROR:'Endpoint từ chối yêu cầu metadata.',
  INVALID_RESPONSE:'Endpoint trả metadata không hợp lệ.',
  COMFYUI_INVALID_RESPONSE:'ComfyUI trả metadata không hợp lệ.',
};

export const readinessReason=code=>readinessReasons[code]??code;
export function profileCapability(profile) {
  const contracts=profile.capability_contracts??[];
  return (contracts.find(item=>item.local_runtime_compatible)??contracts.find(item=>item.route_configurable)
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
  if(limits.max_resolution)return `${limits.min_resolution}–${limits.max_resolution} px mỗi cạnh · tối đa ${limits.max_steps} bước`;
  return limits.format==='structured_json'?'JSON có cấu trúc':limits.format;
}
