// Only persisted counters and completed attempt timestamps; no provider price assumptions.
export function productionUsage(drafts){
  const count=drafts.length;
  const sum=field=>drafts.reduce((total,job)=>total+
    (Number.isSafeInteger(job[field])&&job[field]>=0?job[field]:0),0);
  const times=drafts.map(job=>Date.parse(job.attempt_finished_at)-Date.parse(job.attempt_started_at))
    .filter(ms=>Number.isFinite(ms)&&ms>=0).sort((a,b)=>a-b);
  const middle=Math.floor(times.length/2);
  const median=times.length?(times.length%2?times[middle]:(times[middle-1]+times[middle])/2):null;
  return {count,approved:drafts.filter(job=>job.status==='APPROVED').length,
    cloudCalls:sum('cloud_calls'),cloudSeconds:sum('cloud_motion_seconds'),
    medianAttemptSeconds:median===null?null:Math.round(median/1000)};
}
