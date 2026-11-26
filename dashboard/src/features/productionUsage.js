// Only persisted counters and completed attempt timestamps; no provider price assumptions.
export function productionUsage(drafts){
  const count=drafts.length;
  const counter=field=>{
    const values=drafts.map(job=>job[field]).filter(value=>Number.isSafeInteger(value)&&value>=0);
    return {total:values.length?values.reduce((total,value)=>total+value,0):null,samples:values.length};
  };
  const calls=counter('cloud_calls');
  const seconds=counter('cloud_motion_seconds');
  const times=drafts.filter(job=>job.status!=='RUNNING'&&
    typeof job.attempt_started_at==='string'&&typeof job.attempt_finished_at==='string')
    .map(job=>Date.parse(job.attempt_finished_at)-Date.parse(job.attempt_started_at))
    .filter(ms=>Number.isFinite(ms)&&ms>=0).sort((a,b)=>a-b);
  const middle=Math.floor(times.length/2);
  const median=times.length?(times.length%2?times[middle]:(times[middle-1]+times[middle])/2):null;
  return {count,approved:drafts.filter(job=>job.status==='APPROVED').length,
    cloudCalls:calls.total,cloudCallSamples:calls.samples,
    cloudSeconds:seconds.total,cloudSecondSamples:seconds.samples,
    medianAttemptSeconds:median===null?null:Math.round(median/1000),attemptSamples:times.length};
}
