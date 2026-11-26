// The backend owns timeline constraints and cloud seconds calculations.
export function storyboardShotLimits(job){
  const limits=job?.editor_constraints;
  return limits?.layout_editable?[limits.min_scenes,limits.max_scenes]:[0,0];
}

export function durationBounds(catalog,mode){
  return catalog?.production_options?.duration_bounds?.[mode]??null;
}

export const productionMethodLabels={
  assigned:'Theo model đã phân công',auto:'AI chọn phương pháp',
  local:'Local',hybrid:'Kết hợp ảnh local và video cloud',cloud:'Video cloud trực tiếp',
};
export function productionMethodOptions(catalog){
  const advertised=catalog?.production_options?.methods??[{id:'assigned',available:true}];
  return advertised.filter(method=>Object.hasOwn(productionMethodLabels,method.id))
    .map(method=>({value:method.id,label:productionMethodLabels[method.id]+(method.available&&method.execution_ready===false?' · Chỉ lập storyboard':''),disabled:!method.available}));
}
export function cloudSecondsBounds(catalog,method){
  const options=catalog?.production_options;
  const min=method==='auto'?options?.auto_min_cloud_seconds:options?.min_cloud_seconds;
  const max=options?.max_cloud_seconds;
  return Number.isInteger(min)&&Number.isInteger(max)&&min<=max?{min,max}:null;
}
export function cloudSecondsRemainingEstimate(job){
  return job?.cloud_seconds_remaining??null;
}
