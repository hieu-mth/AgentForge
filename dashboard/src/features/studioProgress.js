export const productionStages = [
  ['PLANNING','Phân tích kịch bản'],['STORYBOARD','Tạo storyboard'],
  ['IMAGES','Tạo hình ảnh'],['MOTION','Tạo chuyển động'],
  ['RENDER','Dựng video'],['VERIFY','Xác minh kết quả'],
];

const verifiedStatuses=new Set(['REVIEW','APPROVED','REJECTED']);
const blockedStatuses=new Set(['WAITING_RESOURCES','STORYBOARD_REVIEW','INTERRUPTED','NEEDS_RECONCILIATION','QUEUED','CANCELLED']);

export function productionElapsed(job,active,now) {
  const sample=job?.resources?.findLast(point=>point.before?.checked_at&&point.after?.checked_at);
  const start=job?.attempt_started_at??(active?job?.started_at:sample?.before.checked_at);
  const end=active?now:Date.parse(job?.attempt_finished_at??sample?.after.checked_at);
  const seconds=Math.floor((end-Date.parse(start))/1000);
  if(!Number.isFinite(seconds)||seconds<0)return null;
  const hours=Math.floor(seconds/3600),minutes=Math.floor(seconds/60)%60;
  const label=[hours&&hours+' giờ',minutes&&minutes+' phút',seconds%60+' giây'].filter(Boolean).join(' ');
  return !active&&!job.attempt_finished_at?'Bước gần nhất · '+label:label;
}

export function productionProgress(job) {
  const scenes=job?.board?.scenes??[];
  const moving=job?.brief?.mode==='motion';
  const directCloud=moving&&job?.production_plan?.method==='cloud';
  const total=scenes.length||job?.brief?.scene_count||0;
  const images=scenes.filter(scene=>scene.asset&&total).length;
  const clips=scenes.filter(scene=>scene.motion_sha&&total).length;
  const verified=Boolean(verifiedStatuses.has(job?.status)&&job?.video_sha&&
    (!job.storyboard_version||job.receipt_sha));
  const stage=job?.stage;
  const encoded=stage==='VERIFY'||verified;
  const planned=Boolean(job?.plan||job?.board||stage==='STORYBOARD');
  const done={PLANNING:planned,STORYBOARD:Boolean(job?.board),IMAGES:total>0&&images===total,
    MOTION:total>0&&clips===total,RENDER:encoded,VERIFY:verified};
  const status=job?.status;
  const active=status==='RUNNING'&&job?.worker_active!==false;
  const stages=productionStages.filter(([key])=>(key!=='MOTION'||moving)&&(key!=='IMAGES'||!directCloud)).map(([key,label])=>({
    key,label,state:key===stage&&status==='FAILED'?'error':
      key===stage&&blockedStatuses.has(status)&&status!=='CANCELLED'?'waiting':
      done[key]?'done':key===stage&&active?'active':'pending',
  }));
  const completed=Number(planned)+Number(Boolean(job?.board))+(directCloud?0:images)+(moving?clips:0)+Number(encoded)+Number(verified);
  return {stages,images,clips,total,verified,moving,directCloud,scenes,active,
    percent:verified?100:Math.min(99,Math.floor(100*completed/(4+total*(moving&&!directCloud?2:1))))};
}
