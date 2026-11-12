// Owner overview selectors. All counts are scoped to the bounded bootstrap snapshot.
const VALID_DATE = /^\d{4}-\d{2}-\d{2}/;
export function dateKey(value) {
  if (typeof value !== 'string' || !VALID_DATE.test(value)) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0,10);
}
export function buildOverview(data, now=new Date()) {
  const tasks=Array.isArray(data?.tasks)?data.tasks:[];
  const goals=Array.isArray(data?.goals)?data.goals:[];
  const attention=Array.isArray(data?.attention)?data.attention:[];
  const reviews=Array.isArray(data?.autopilot_reviews?.items)?data.autopilot_reviews.items:[];
  const videos=Array.isArray(data?.local_video?.items)?data.local_video.items:[];
  const waitingGoals=goals.filter(x=>x.status==='WAITING_APPROVAL');
  const waitingReviews=reviews.filter(x=>x.decision==='PENDING');
  const waitingVideos=videos.filter(x=>x.status==='VIDEO_READY');
  const issues=[
    ...attention.map(x=>({id:'attention:'+x.kind+':'+x.id,kind:x.kind,
      title:x.title||'Cần kiểm tra',status:x.status,priority:x.priority,
      section:x.kind==='goal'?'goals':x.kind==='schedules'?'schedules':'tasks'})),
    ...tasks.filter(x=>x.status==='FAILED').map(x=>({id:'attention:task:'+x.task_id,\n      kind:'task',title:x.skill_id||'Tác vụ lỗi',status:'FAILED',priority:'REVIEW',section:'tasks'})),\n    ...waitingReviews.map(x=>({id:'review:'+x.job_id,kind:'review',
      title:'Bản nháp AI chờ duyệt',status:'PENDING',priority:'HIGH',section:'reviews'})),
    ...waitingVideos.map(x=>({id:'video:'+x.production_id,kind:'video',
      title:'Video chờ Owner xem',status:'VIDEO_READY',priority:'HIGH',section:'reviews'})),
  ];
  const unique=[...new Map(issues.map(x=>[x.id,x])).values()];
  unique.sort((a,b)=>(a.priority==='HIGH'?0:1)-(b.priority==='HIGH'?0:1));
  const today=dateKey(now.toISOString());
  const recent=[...tasks].sort((a,b)=>String(b.updated_at||b.created_at||'').localeCompare(
    String(a.updated_at||a.created_at||''))).slice(0,8);
  const dayKeys=Array.from({length:7},(_,i)=>{
    const d=new Date(now);d.setDate(d.getDate()-(6-i));return dateKey(d.toISOString());
  });
  const trend=dayKeys.map(day=>({day,
    succeeded:tasks.filter(t=>dateKey(t.updated_at||t.created_at)===day&&t.status==='SUCCEEDED').length,
    failed:tasks.filter(t=>dateKey(t.updated_at||t.created_at)===day&&
      ['FAILED','INTERRUPTED'].includes(t.status)).length}));
  return {
    counts:{running:tasks.filter(x=>x.status==='RUNNING').length,
      waiting:waitingGoals.length+waitingReviews.length+waitingVideos.length,
      doneToday:tasks.filter(x=>x.status==='SUCCEEDED'&&dateKey(x.updated_at||x.created_at)===today).length,
      problems:tasks.filter(x=>['FAILED','INTERRUPTED'].includes(x.status)).length+
        goals.filter(x=>['FAILED','INTERRUPTED'].includes(x.status)).length},
    issues:unique,recent,trend,scope:{tasks:tasks.length,goals:goals.length,
      reviews:reviews.length,videos:videos.length},
  };
}
