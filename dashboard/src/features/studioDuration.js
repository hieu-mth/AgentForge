export const MAX_STUDIO_SECONDS=60;

export function maxMotionShots(seconds){
  return Math.min(seconds,Math.max(16,Math.ceil(seconds*32/MAX_STUDIO_SECONDS)));
}
