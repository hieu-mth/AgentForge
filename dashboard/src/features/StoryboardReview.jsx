import {useState} from 'react';
import {Alert,Button,Image,Modal,Segmented,Space,Tag} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {ScriptContent} from './ScriptContent.jsx';
import {MAX_STUDIO_SECONDS} from './studioDuration.js';
import './storyboard-review.css';

export function StoryboardReview({job,busy,error,onClose,onApprove,onEdit,onRewrite,onAdd,onMove,onRemove,onPreview,onDuration}){
  const [shot,setShot]=useState(null);
  const [seconds,setSeconds]=useState(null);
  const [view,setView]=useState('scenes');
  const scenes=job.board.scenes;
  const index=Math.max(0,scenes.findIndex((s,i)=>(s.shot_id??i)===shot));
  const scene=scenes[index];
  const reviewing=job.status==='STORYBOARD_REVIEW';
  const authoredScenes=job.duration_plan?.content_scene_count;
  const countLabel=authoredScenes?`${authoredScenes} cảnh · ${scenes.length} shot`:`${scenes.length} cảnh`;
  const shotLabel=(item,i)=>item.content_scene?
    `Cảnh ${item.content_scene} · Shot ${item.content_shot}/${item.content_shot_count}`:
    'Cảnh '+String(i+1).padStart(2,'0');
  return <Modal open centered width={1080} rootClassName="storyboard-review" title={job.board.title}
    onCancel={onClose} footer={<div className="storyboard-footer">
      <div><strong>{job.brief.seconds} giây · {countLabel}{job.storyboard_version&&' · Phiên bản '+job.storyboard_version}</strong>
        {reviewing&&<div className="env-muted">Duyệt phiên bản này để tạo ảnh{job.brief.mode==='motion'?' và chuyển động':''} tuần tự cho {scenes.length} {authoredScenes?'shot':'cảnh'}.</div>}
      </div>
      <Space wrap><Button onClick={onClose}>{reviewing?'Xem sau':'Đóng'}</Button>
        {reviewing&&<Button type="primary" disabled={busy} onClick={onApprove}>Duyệt và bắt đầu sản xuất</Button>}
      </Space>
    </div>}>
    {error&&<Alert type="error" showIcon message={error}/>}
    <div className="storyboard-toolbar">
      <Segmented aria-label="Chế độ xem storyboard" value={view} onChange={setView}
        options={[{label:'Các cảnh',value:'scenes'},{label:'Nội dung & phiên bản',value:'source'}]}/>
    </div>
    {view==='source'?<section className="storyboard-source" aria-label="Nội dung video và phiên bản">
      {job.duration_plan&&<div className="storyboard-context">
        <p>{authoredScenes?'Thời lượng kịch bản':'AI đề xuất'} <strong>{job.duration_plan.estimated_duration_seconds} giây</strong> ·
          {' '+countLabel}. Timeline hiện tại <strong>{job.brief.seconds} giây</strong>.</p>
        <p className="env-muted">{job.duration_plan.duration_reasoning}</p>
        {onDuration&&<Space wrap>
          <NumberField aria-label="Thời lượng storyboard" min={job.brief.mode==='motion'?4:6} max={MAX_STUDIO_SECONDS}
            precision={0} value={seconds??job.brief.seconds} onChange={setSeconds} suffix="giây"/>
          <Button disabled={busy||seconds===null||seconds===job.brief.seconds} onClick={()=>onDuration(seconds)}>Cập nhật thời lượng</Button>
        </Space>}
      </div>}
      <h3>Nội dung video</h3>
      <ScriptContent text={job.brief.idea}/>
      {!!job.storyboard_history?.length&&<>
        <h3>Phiên bản trước</h3>
        {job.storyboard_history.map(entry=><p key={entry.sha256}>Phiên bản {entry.storyboard.version} · {entry.storyboard.scenes.length} cảnh{entry.video_sha?' · Có MP4 đã lưu':''}</p>)}
      </>}
    </section>:<div className="storyboard-layout">
      <nav aria-label="Danh sách cảnh" className="storyboard-scenes">
        {scenes.map((item,i)=><button key={item.shot_id??i} type="button" aria-pressed={index===i}
          onClick={()=>setShot(item.shot_id??i)}>
          <strong>{shotLabel(item,i)} · {Number(item.seconds.toFixed(2)).toLocaleString('vi-VN')} giây</strong>
          <span>{item.description}</span>
        </button>)}
        {onAdd&&<Button disabled={busy} onClick={onAdd}>Thêm cảnh</Button>}
      </nav>
      {scene&&<article key={scene.shot_id??index} className="storyboard-detail">
        <header className="storyboard-scene-title"><h3>{scene.content_scene?shotLabel(scene,index):'Cảnh '+(index+1)}</h3>
          <span>{Number(scene.seconds.toFixed(2)).toLocaleString('vi-VN')} giây</span>
        </header>
        <p>{scene.description}</p>
        {scene.shot_reason&&<p className="env-muted">{scene.shot_reason}</p>}
        {scene.asset&&<div className="storyboard-image"><Image loading="lazy" alt={'Ảnh cảnh '+(index+1)}
          src={'/api/film/drafts/'+job.id+'/scene-'+index+'?v='+scene.asset}/></div>}
        {!!scene.character_ids?.length&&<Space wrap>{scene.character_ids.map(id=><Tag key={id}>{job.cast?.[id]?.name??id}</Tag>)}</Space>}
        {(scene.scene_notes||scene.continuity||job.board.continuity)&&<p>{scene.scene_notes||scene.continuity||job.board.continuity}</p>}
        {scene.caption&&<p><strong>Phụ đề</strong><br/>{scene.caption}</p>}
        {scene.script_range&&<details><summary>Kịch bản gốc</summary>
          <ScriptContent text={Array.from(job.brief.idea).slice(...scene.script_range).join('')}/>
        </details>}
        <details><summary>Chi tiết AI</summary>
          <p><strong>Prompt ảnh</strong><br/>{scene.image_prompt}</p>
          {scene.motion_prompt&&<p><strong>Prompt chuyển động</strong><br/>{scene.motion_prompt}</p>}
          {scene.audio&&<p><strong>Âm thanh dự kiến</strong><br/>{scene.audio}</p>}
        </details>
        <Space wrap className="storyboard-actions">
          {onEdit&&<Button disabled={busy} onClick={()=>onEdit(index,scene)}>Sửa cảnh</Button>}
          {onRewrite&&<Button disabled={busy} onClick={()=>onRewrite(index,scene)}>AI viết lại</Button>}
          {onMove&&index>0&&<Button disabled={busy} onClick={()=>onMove(index,index-1)}>Đưa lên</Button>}
          {onMove&&index+1<scenes.length&&<Button disabled={busy} onClick={()=>onMove(index,index+1)}>Đưa xuống</Button>}
          {onRemove&&<Button danger disabled={busy} onClick={()=>onRemove(index)}>Bỏ cảnh</Button>}
          {scene.motion_sha&&<Button onClick={()=>onPreview(index,scene.motion_sha)}>Xem chuyển động</Button>}
        </Space>
      </article>}
    </div>}
  </Modal>;
}
