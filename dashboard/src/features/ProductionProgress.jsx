import {useEffect,useState} from 'react';
import {Progress,Tag,theme} from 'antd';
import {CheckCircleOutlined,ClockCircleOutlined,ExclamationCircleOutlined,FileTextOutlined,
  PictureOutlined,PlayCircleOutlined,RightOutlined,ScissorOutlined,SafetyCertificateOutlined,ThunderboltOutlined} from '@ant-design/icons';
import {productionElapsed,productionProgress} from './studioProgress.js';
import './production-progress.css';
import {draftTitle} from './scriptPresentation.js';
import {groupDraftScenes} from './studioScenes.js';
import {AppTooltip} from '../components/AppTooltip.jsx';

const icons={PLANNING:FileTextOutlined,STORYBOARD:FileTextOutlined,IMAGES:PictureOutlined,
  MOTION:ThunderboltOutlined,RENDER:ScissorOutlined,VERIFY:SafetyCertificateOutlined};
const states={done:'Hoàn thành',active:'Đang xử lý',waiting:'Đang chờ',pending:'Chưa bắt đầu',error:'Lỗi'};

export function ProductionProgress({job,starting,labels,warnings}){
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
  const authored=Boolean(job?.duration_plan?.content_scene_count);
  const planned=job?.duration_plan?.recommended_shot_count;
  const savedShots=job?.storyboard_checkpoint?.shots?.length??0;
  const pendingStoryboard=!job?.board&&Number.isInteger(planned)&&planned>0;
  const groups=groupDraftScenes(job);
  const complete=scene=>Boolean(p.moving?scene.motion_sha:scene.asset);
  const completedScenes=groups.filter(group=>group.shots.every(({scene})=>complete(scene))).length;
  const currentShot=p.scenes[(a?.scene??0)-1]??job?.duration_plan?.shots?.[(a?.scene??0)-1];
  const activityUnit=authored&&currentShot?.content_scene?
    `cảnh ${currentShot.content_scene} · shot ${currentShot.content_shot}/${currentShot.content_shot_count}`:
    `cảnh ${a?.scene}/${p.total}`;
  const title=starting?'Đang gửi yêu cầu':a?.operation==='cast'?'Đang chọn nhân vật':
    a?.operation==='script'?'Đang phân tích kịch bản · '+(authored?activityUnit:'cảnh '+a.scene):
    a?.operation==='image'&&a.scene?'Đang tạo ảnh '+activityUnit:
    a?.operation==='motion'&&a.scene?'Đang tạo chuyển động '+activityUnit:
    p.active?(labels[job?.stage]??labels[status]):(labels[status]??'Đang chuẩn bị bản nháp');
  const spent=productionElapsed(job,p.active,now);
  function renderShot({scene,index},label,compact=false) {
    const current=a?.scene===index+1&&['image','motion'].includes(a?.operation);
    const done=complete(scene);
    const failed=status==='FAILED'&&!done&&job?.failed_scene===index+1;
    const imageStatus=scene.asset?'Đã tạo':current&&a.operation==='image'?'Đang tạo':'Chờ';
    const motionStatus=scene.motion_sha?'Đã xác minh':current&&a.operation==='motion'?'Đang tạo':'Chờ';
    if(compact)return <li key={scene.shot_id??index} data-active={current||undefined} data-error={failed||undefined}>
      <AppTooltip title={<>{!p.directCloud&&<>Ảnh · {imageStatus}</>}{p.moving&&<>{!p.directCloud&&<br/>}Chuyển động · {motionStatus}</>}</>}>
        <span className="production-shot-chip" tabIndex={0}><strong>{label}</strong>
          {done?<CheckCircleOutlined/>:failed?<ExclamationCircleOutlined/>:<span className="production-shot-dot"/>}
        </span>
      </AppTooltip>
      {failed&&<small>Cần xử lý · {warnings[job.error]??job.error}</small>}
    </li>;
    return <li key={scene.shot_id??index} data-active={current||undefined} data-error={failed||undefined}>
      <strong>{label} {done&&<CheckCircleOutlined/>}</strong>
      {!p.directCloud&&<small>Ảnh · {imageStatus}</small>}
      {p.moving&&<small>Chuyển động · {motionStatus}</small>}
      {failed&&<small>Cần xử lý · {warnings[job.error]??job.error}</small>}
    </li>;
  }
  return <section className="production-progress" aria-label="Tiến độ tạo bản nháp" style={{
    '--prod-bg':token.colorBgContainer,'--prod-fill':token.colorFillAlter,'--prod-line':token.colorBorderSecondary,
    '--prod-text':token.colorText,'--prod-muted':token.colorTextSecondary,'--prod-primary':token.colorPrimary,
    '--prod-tint':token.colorPrimaryBg,'--prod-success':token.colorSuccess,'--prod-error':token.colorError,
  }}>
    <header className="production-header">
      <div className="production-title"><span className="production-mark"><PlayCircleOutlined/></span><div>
        <h3>{draftTitle(job)}</h3>
        <div className="production-meta">{job?.brief?.seconds&&<span>{job.brief.seconds} giây</span>}
          {p.total>0&&<span>{authored?
            `${completedScenes}/${job.duration_plan.content_scene_count} cảnh hoàn thành · ${p.moving?p.clips:p.images}/${p.total} shot ${p.moving?'đã xác minh':'đã tạo'}`:
            `${p.moving?p.clips:p.images}/${p.total} cảnh hoàn thành`}</span>}
          {spent&&<span className="production-elapsed"><ClockCircleOutlined aria-hidden="true"/>{spent}</span>}</div>
      </div></div>
      {status&&<Tag color={status==='STORYBOARD_REVIEW'||status==='REVIEW'?'orange':
        p.verified?'success':status==='FAILED'?'error':p.active?'processing':'default'}>{labels[status]??status}</Tag>}
    </header>
    <div className="production-overall" role="status">
      <strong>{title}</strong>{pendingStoryboard
        ?<div className="production-meta">{savedShots}/{planned} shot storyboard đã lưu</div>
        :<Progress percent={p.percent} format={value=>value+'%'}
          status={status==='FAILED'?'exception':p.verified?'success':'normal'}/>}
      {job?.stage==='MOTION'&&!authored&&<small>{p.clips}/{p.total} clip đã xác minh</small>}
      {job?.error&&<p className="production-error"><ExclamationCircleOutlined/> {warnings[job.error]??job.error}</p>}
      {a?.model&&<div className="production-meta">{a.provider==='ollama'?'Ollama':a.provider==='comfyui'?'ComfyUI':a.provider==='chatgpt'?'ChatGPT':a.provider==='ltx_cloud'?'LTX Cloud':a.provider} · {a.model}</div>}
    </div>
    <ol className="production-steps">{p.stages.map(({key,label,state})=>{
      const Icon=state==='done'?CheckCircleOutlined:icons[key];
      return <li key={key} data-state={state} aria-current={state==='active'?'step':undefined}>
        <Icon/><span>{label}<small>{states[state]}</small></span>
      </li>;
    })}</ol>
    {p.scenes.length>0&&<details className="production-scenes" open={groups.length<=6}>
      <summary>Tiến độ từng cảnh</summary>
      {authored?<div className="production-scene-groups">{groups.map(group=>{
        const doneCount=group.shots.filter(({scene})=>complete(scene)).length;
        const active=p.active&&group.shots.some(({index})=>index+1===a?.scene);
        const failed=status==='FAILED'&&group.shots.some(({index})=>index+1===job?.failed_scene);
        return <details className="production-scene-row" key={group.key}>
          <summary className="production-group-heading">
            <RightOutlined aria-hidden="true"/>
            <h4>{group.label}{group.title&&' · '+group.title}</h4>
            <span className="production-group-count" data-state={failed?'error':doneCount===group.shots.length?'done':active?'active':undefined}>
              {failed?<ExclamationCircleOutlined/>:doneCount===group.shots.length?<CheckCircleOutlined/>:null}
              {doneCount}/{group.shots.length} shot
            </span>
          </summary>
          <ul>{group.shots.map(shot=>renderShot(shot,`Shot ${shot.scene.content_shot}`,true))}</ul>
        </details>;
      })}</div>:<ul>{groups.flatMap(group=>group.shots.map(shot=>renderShot(shot,group.label)))}</ul>}
    </details>}
  </section>;
}
