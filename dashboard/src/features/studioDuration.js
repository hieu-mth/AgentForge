export const MAX_STUDIO_SECONDS=60;

export function minMotionShots(seconds, output){
  return Math.max(2,Math.ceil(seconds*(output?.fps??24)/(output?.max_frames??49)));
}

export function maxMotionShots(seconds){
  return Math.min(seconds,Math.max(16,Math.ceil(seconds*32/MAX_STUDIO_SECONDS)));
}
