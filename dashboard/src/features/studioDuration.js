// The backend owns timeline constraints and cloud seconds calculations.
export const videoModes={motion:'Có chuyển động',still:'Ảnh tĩnh (lia và thu phóng)'};
export function storyboardShotLimits(job){
  const limits=job?.editor_constraints;
  return limits?.layout_editable?[limits.min_scenes,limits.max_scenes]:[0,0];
}

export function durationBounds(catalog,mode){
  return catalog?.production_options?.duration_bounds?.[mode]??null;
}

export const productionMethodLabels={
  assigned:'Theo model đã phân công',auto:'AI chọn phương pháp',
  local:'Video local',hybrid:'Video từ ảnh (cloud)',cloud:'Video từ kịch bản (cloud)',
};
export function cloudSecondsRemainingEstimate(job){
  return job?.cloud_seconds_remaining??null;
}
