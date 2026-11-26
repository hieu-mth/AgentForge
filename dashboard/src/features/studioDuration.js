export const MAX_STUDIO_SECONDS=60;

export function minMotionShots(seconds, output){
  return Math.max(2,Math.ceil(seconds*(output?.fps??24)/(output?.max_frames??49)));
}

export function maxMotionShots(seconds){
  return Math.min(seconds,Math.max(16,Math.ceil(seconds*32/MAX_STUDIO_SECONDS)));
}


// Presets only interpret historical drafts that predate automatic duration.
const historicalMotionShots={4:[2,2],6:[3,3],15:[8,9],30:[15,16]};
export function storyboardShotLimits(job){
  if(!job)return [0,0];
  const {mode,seconds,duration_mode}=job.brief;
  if(mode!=='motion')return [2,Math.min(6,Math.floor(seconds/2))];
  if(!duration_mode)return historicalMotionShots[seconds]??[0,0];
  return [minMotionShots(seconds,job.motion_plan?.output??job.approved_motion?.output),maxMotionShots(seconds)];
}

export const productionMethodLabels={
  assigned:'Theo model đã phân công',auto:'AI chọn phương pháp',
  local:'Local',hybrid:'Kết hợp ảnh local và video cloud',cloud:'Video cloud trực tiếp',
};
export function productionMethodOptions(catalog){
  const advertised=catalog?.production_options?.methods??[{id:'assigned',available:true}];
  return advertised.filter(method=>Object.hasOwn(productionMethodLabels,method.id))
    .map(method=>({value:method.id,label:productionMethodLabels[method.id],disabled:!method.available}));
}
export function cloudSecondsBounds(catalog,method){
  const options=catalog?.production_options;
  if(method==='auto')return {min:options?.auto_min_cloud_seconds??0,max:options?.max_cloud_seconds??240};
  return {min:options?.min_cloud_seconds??12,max:options?.max_cloud_seconds??240};
}
export function cloudSecondsRemainingEstimate(job){
  const plan=job.production_plan;
  if(!plan||plan.method==='local')return 0;
  const durations=plan.billable_durations_seconds??[6,8,10]; // Existing approved plans.
  const fps=job.motion_plan?.output?.fps??job.approved_motion?.output?.fps??24;
  return job.board.scenes.filter(scene=>!scene.motion_job).reduce((n,scene)=>
    n+(durations.find(seconds=>seconds*fps>=scene.frames)??Infinity),0);
}
