import {useEffect,useState} from 'react';
import {Button,Progress,Space,Tag,theme} from 'antd';
import {CheckCircleOutlined,ClockCircleOutlined,ExclamationCircleOutlined,FileTextOutlined,
  PictureOutlined,PlayCircleOutlined,ScissorOutlined,SafetyCertificateOutlined,ThunderboltOutlined} from '@ant-design/icons';
import {productionProgress} from './studioProgress.js';
import './production-progress.css';

const icons={PLANNING:FileTextOutlined,STORYBOARD:FileTextOutlined,IMAGES:PictureOutlined,
  MOTION:ThunderboltOutlined,RENDER:ScissorOutlined,VERIFY:SafetyCertificateOutlined};
const states={done:'Hoàn thành',active:'Đang xử lý',waiting:'Đang chờ',pending:'Chưa bắt đầu',error:'Lỗi'};

function elapsed(start,end){
  const seconds=Math.max(0,Math.floor((end-Date.parse(start))/1000));
  return Number.isFinite(seconds)?Math.floor(seconds/60)+' phút '+seconds%60+' giây':null;
}

export function ProductionProgress({job,starting,labels,warnings,onCancel,onResume,busy}){
  const {token}=theme.useToken();
  const p=productionProgress(job);
  const [now,setNow]=useState(()=>Date.now());
  useEffect(()=>{
    if(!p.active)return;
    setNow(Date.now());
    const timer=setInterval(()=>setNow(Date.now()),1000);
    return ()=>clearInterval(timer);
  },[p.active,job?.id]);
  const status=job?.status;
  const a=job?.activity;
  const title=starting?'Đang gửi yêu cầu':a?.operation==='cast'?'Đang chọn nhân vật':
    a?.operation==='script'?'Đang phân tích kịch bản · cảnh '+a.scene:
    a?.operation==='image'&&a.scene?'Đang tạo ảnh cảnh '+a.scene+'/'+p.total:
    a?.operation==='motion'&&a.scene?'Đang tạo chuyển động cảnh '+a.scene+'/'+p.total:
    p.active?(labels[job?.stage]??labels[status]):(labels[status]??'Đang chuẩn bị bản nháp');
  const spent=job&&elapsed(job.started_at??job.created_at,p.active?now:Date.parse(job.updated_at));
  const canResume=['QUEUED','WAITING_RESOURCES','INTERRUPTED','NEEDS_RECONCILIATION','FAILED'].includes(status);
  return <section className="production-progress" aria-label="Tiến độ tạo bản nháp" style={{
    '--prod-bg':token.colorBgContainer,'--prod-fill':token.colorFillAlter,'--prod-line':token.colorBorderSecondary,
    '--prod-text':token.colorText,'--prod-muted':token.colorTextSecondary,'--prod-primary':token.colorPrimary,
    '--prod-tint':token.colorPrimaryBg,'--prod-success':token.colorSuccess,'--prod-error':token.colorError,
  }}>
    <header className="production-header">
      <div className="production-title"><span className="production-mark"><PlayCircleOutlined/></span><div>
        <h3>{job?.board?.title??job?.brief?.idea??'Đang chuẩn bị bản nháp'}</h3>
        <div className="production-meta">{job?.brief?.seconds&&<span>{job.brief.seconds} giây</span>}
          {p.total>0&&<span>{p.moving?p.clips:p.images}/{p.total} cảnh hoàn thành</span>}
          {spent&&<span><ClockCircleOutlined/> {spent}</span>}</div>
      </div></div>
      {status&&<Tag color={p.verified?'success':status==='FAILED'?'error':p.active?'processing':'default'}>{labels[status]??status}</Tag>}
    </header>
    <div className="production-overall" role="status">
      <strong>{title}</strong><Progress percent={p.percent} format={value=>value+'%'}
        status={status==='FAILED'?'exception':p.verified?'success':'normal'}/>
      {job?.stage==='MOTION'&&<small>{p.clips}/{p.total} clip đã xác minh</small>}
      {job?.error&&<p className="production-error"><ExclamationCircleOutlined/> {warnings[job.error]??job.error}</p>}
      {a?.model&&<div className="production-meta">{a.provider==='ollama'?'Ollama':a.provider==='comfyui'?'ComfyUI':a.provider} · {a.model}</div>}
    </div>
    <ol className="production-steps">{p.stages.map(({key,label,state})=>{
      const Icon=state==='done'?CheckCircleOutlined:icons[key];
      return <li key={key} data-state={state} aria-current={state==='active'?'step':undefined}>
        <Icon/><span>{label}<small>{states[state]}</small></span>
      </li>;
    })}</ol>
    {p.scenes.length>0&&<details className="production-scenes" open={p.scenes.length<=6}>
      <summary>Tiến độ từng cảnh</summary>
      <ul>{p.scenes.map((scene,i)=>{
        const current=a?.scene===i+1&&['image','motion'].includes(a?.operation);
        const done=p.moving?scene.motion_sha:scene.asset;
        const failed=status==='FAILED'&&!done&&job?.failed_scene===i+1;
        return <li key={scene.shot_id??i} data-active={current||undefined} data-error={failed||undefined}>
          <strong>Cảnh {String(i+1).padStart(2,'0')} {done&&<CheckCircleOutlined/>}</strong>
          <small>Ảnh · {scene.asset?'Đã tạo':current&&a.operation==='image'?'Đang tạo':'Chờ'}</small>
          {p.moving&&<small>Motion · {scene.motion_sha?'Đã xác minh':current&&a.operation==='motion'?'Đang tạo':'Chờ'}</small>}
          {failed&&<small>Cần xử lý · {warnings[job.error]??job.error}</small>}
        </li>;
      })}</ul>
    </details>}
    <Space wrap>{onCancel&&['QUEUED','RUNNING','WAITING_RESOURCES'].includes(status)&&
      <Button size="small" disabled={busy} onClick={onCancel}>Hủy tác vụ</Button>}
      {onResume&&canResume&&<Button size="small" disabled={busy} onClick={onResume}>Tiếp tục từ checkpoint</Button>}
    </Space>
  </section>;
}
