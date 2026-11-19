// View-only helpers; backend is the authority for all model/route mutations.
export const PROVIDERS = Object.freeze([
  {value:'ollama',label:'Ollama (local text)'},
  {value:'anthropic',label:'Anthropic-compatible cloud (env only)'},
  {value:'comfyui',label:'ComfyUI (local media · cấu hình)' },
]);
export function exposureFor(profile) {
  if(!profile) return 'Chưa chọn model';
  if(profile.provider==='anthropic') return 'Cloud: gửi dữ liệu ra ngoài và có thể phát sinh phí; mỗi lượt chạy vẫn cần quyền Owner.';
  if(profile.provider==='comfyui') return 'GPU/ComfyUI: mới lưu cấu hình, chưa chạy model, chưa tải checkpoint.';
  return 'Ollama local: chỉ lưu cấu hình, chưa tự gọi inference.';
}
export function profilePayload(values) {
  const base={id:values.id?.trim(),provider:values.provider,
    model:values.model?.trim(),enabled:values.enabled===true};
  if(values.provider==='anthropic'){
    base.base_url_env=values.base_url_env?.trim();
    base.api_key_env=values.api_key_env?.trim();
  }else{
    base.base_url=values.base_url?.trim();
  }
  return base;
}
