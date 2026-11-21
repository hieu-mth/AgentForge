import {useState} from 'react';
import {Alert,Button,Image,Modal,Space,Tag} from 'antd';
import './storyboard-review.css';

export function StoryboardReview({job,busy,error,onClose,onApprove,onEdit,onRewrite,onAdd,onMove,onRemove,onPreview}){
  const [shot,setShot]=useState(null);
  const scenes=job.board.scenes;
  const index=Math.max(0,scenes.findIndex((s,i)=>(s.shot_id??i)===shot));
  const scene=scenes[index];
  const reviewing=job.status==='STORYBOARD_REVIEW';
  return <Modal open width={1000} rootClassName="storyboard-review" title={job.board.title}
    onCancel={onClose} footer={<div className="storyboard-footer">
      <div><strong>{job.brief.seconds} giây · {scenes.length} cảnh{job.storyboard_version&&' · Phiên bản '+job.storyboard_version}</strong>
        {reviewing&&<div className="env-muted">Duyệt phiên bản này để tạo ảnh{job.brief.mode==='motion'?' và chuyển động':''} tuần tự cho {scenes.length} cảnh.</div>}
      </div>
      <Space wrap><Button onClick={onClose}>{reviewing?'Xem sau':'Đóng'}</Button>
        {reviewing&&<Button type="primary" disabled={busy} onClick={onApprove}>Duyệt và bắt đầu sản xuất</Button>}
      </Space>
    </div>}>
    {error&&<Alert type="error" showIcon message={error}/>}
    <details className="storyboard-context"><summary>Nội dung video và phiên bản</summary>
      <p className="draft-source-text">{job.brief.idea}</p>
      {job.storyboard_history?.map(entry=><p key={entry.sha256}>Phiên bản {entry.storyboard.version} · {entry.storyboard.scenes.length} cảnh{entry.video_sha?' · Có MP4 đã lưu':''}</p>)}
    </details>
    <div className="storyboard-layout">
      <nav aria-label="Danh sách cảnh" className="storyboard-scenes">
        {scenes.map((item,i)=><button key={item.shot_id??i} type="button" aria-pressed={index===i}
          onClick={()=>setShot(item.shot_id??i)}>
          <strong>Cảnh {String(i+1).padStart(2,'0')} · {Number(item.seconds.toFixed(2)).toLocaleString('vi-VN')} giây</strong>
          <span>{item.description}</span>
        </button>)}
        {onAdd&&<Button disabled={busy} onClick={onAdd}>Thêm cảnh</Button>}
      </nav>
      {scene&&<article className="storyboard-detail">
        <h3>Cảnh {index+1}</h3><p>{scene.description}</p>
        {scene.asset&&<Image width={180} loading="lazy" alt={'Ảnh cảnh '+(index+1)}
          src={'/api/film/drafts/'+job.id+'/scene-'+index+'?v='+scene.asset}/>}
        {!!scene.character_ids?.length&&<Space wrap>{scene.character_ids.map(id=><Tag key={id}>{job.cast?.[id]?.name??id}</Tag>)}</Space>}
        {(scene.scene_notes||scene.continuity||job.board.continuity)&&<p>{scene.scene_notes||scene.continuity||job.board.continuity}</p>}
        {scene.caption&&<p><strong>Phụ đề</strong><br/>{scene.caption}</p>}
        {scene.script_range&&<details><summary>Kịch bản gốc</summary>
          <p className="draft-source-text">{Array.from(job.brief.idea).slice(...scene.script_range).join('')}</p>
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
    </div>
  </Modal>;
}
