import {useState} from 'react';
import {Alert,Button,Image,Input,Modal,Segmented,Select,Space,Tag} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {ScriptContent} from './ScriptContent.jsx';
import {draftTitle} from './scriptPresentation.js';
import {groupDraftScenes} from './studioScenes.js';
import {MAX_STUDIO_SECONDS} from './studioDuration.js';
import './storyboard-review.css';

export function StoryboardReview({job,busy,error,onClose,onApprove,onEdit,onRewrite,onAdd,onMove,onRemove,onPreview,onDuration,onRegenerate,onVisualReview,onAudio,onContinuity,onAudioDirect}){
  const [shot,setShot]=useState(null);
  const [seconds,setSeconds]=useState(null);
  const [view,setView]=useState('scenes');
  const [engine,setEngine]=useState(job.audio_plan?.engine??'none');
  const [voice,setVoice]=useState(job.audio_plan?.voice_name??'');
  const [voices,setVoices]=useState(job.audio_plan?.voices??{});
  const scenes=job.board.scenes;
  const index=Math.max(0,scenes.findIndex((s,i)=>(s.shot_id??i)===shot));
  const scene=scenes[index];
  const reviewing=job.status==='STORYBOARD_REVIEW';
  const review=job.visual_reviews?.[scene?.shot_id];
  const visualReview=review?.video_sha===job.video_sha&&review?.storyboard_sha===job.storyboard_sha?review:null;
  const authoredScenes=job.duration_plan?.content_scene_count;
  const creativeScenes=job.duration_plan?.creative_plan?.scenes;
  const creativeCount=creativeScenes?.reduce((sum,entry)=>sum+entry.creative_shots.length,0);
  const groups=groupDraftScenes(job);
  const activeGroup=groups.find(group=>group.shots.some(shot=>shot.index===index));
  const countLabel=creativeCount?`${authoredScenes} cảnh · ${creativeCount} góc quay · ${scenes.length} segment`:
    authoredScenes?`${authoredScenes} cảnh · ${scenes.length} shot`:`${scenes.length} cảnh`;
  return <Modal open centered width={1080} rootClassName="storyboard-review" title={draftTitle(job)}
    onCancel={onClose} footer={<div className="storyboard-footer">
      <div><strong>{job.brief.seconds} giây · {countLabel}{job.storyboard_version&&' · Phiên bản '+job.storyboard_version}</strong>
        {reviewing&&<div className="env-muted">Duyệt phiên bản này để tạo ảnh{job.brief.mode==='motion'?' và chuyển động':''} tuần tự cho {scenes.length} {authoredScenes?'shot':'cảnh'}.</div>}
      </div>
      <Space wrap><Button onClick={onClose}>{reviewing?'Xem sau':'Đóng'}</Button>
        {reviewing&&<Button type="primary" disabled={busy} onClick={onApprove}>Duyệt và bắt đầu sản xuất</Button>}
      </Space>
    </div>}>
    {error&&<Alert type="error" showIcon message={error}/>}
    {reviewing&&job.deferred_media_binding&&<Alert type="info" showIcon
      message="Storyboard chưa khóa model media"
      description="Bạn có thể xem và chỉnh nội dung trước khi đăng ký model ảnh hoặc video. Khi duyệt sản xuất, hệ thống kiểm tra và khóa các model media đang được phân công. Timeline hiện vẫn theo giới hạn I2V."/>}
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
      {onContinuity&&<div className="storyboard-context">
        <h3>Liên tục chuyển động</h3>
        <p>AI chọn chuyển cảnh, đổi góc hoặc tiếp nối từ frame cuối thực tế. Thay đổi kế hoạch sẽ cần duyệt lại.</p>
        <Button disabled={busy} onClick={onContinuity}>AI lập liên tục chuyển động</Button>
      </div>}
      <h3>Âm thanh</h3>
      <p>{job.audio_plan?.format==='directed.v1'?'AI Audio Director · '+job.audio_plan.cues.length+' cue':
        job.audio_plan?'Lời thoại từ phụ đề · '+job.audio_plan.engine:'Không có lời thoại tự động'}</p>
      {job.audio_plan?.format==='directed.v1'&&<div className="storyboard-context">
        {job.audio_plan.cues.map((cue,i)=><p key={i}>{cue.kind} · Cảnh {scenes.findIndex(s=>s.shot_id===cue.shot_id)+1}
          {' · frame '+cue.start_frame+'–'+cue.end_frame+' · '+cue.gain_db+' dB · '+(cue.text||cue.asset)}
          {cue.voice?' · '+cue.voice:''}</p>)}
        {job.audio_plan.unresolved.map((item,i)=><Alert key={i} type="warning" showIcon message={item.detail}/>)}
      </div>}
      {onAudio&&<div className="storyboard-context">
        <p className="env-muted">AI lập lời thoại, thuyết minh, nhạc, môi trường và hiệu ứng từ thư viện WAV local. Chỉ thực thi sau khi duyệt. Không tự tải model hoặc tài sản.</p>
        <Space wrap>
          <Select aria-label="Nguồn lời thoại" value={engine} onChange={setEngine} options={[
            {value:'none',label:'Không lời thoại'},{value:'windows',label:'Windows SAPI'},
            {value:'piper',label:'Piper local'},{value:'cloud',label:'Speech cloud (Model Hub)'},
          ]}/>
          {engine!=='none'&&<Input aria-label="Tên voice local" value={voice} maxLength={100}
            onChange={e=>setVoice(e.target.value)} placeholder={engine==='piper'?'voice.onnx':engine==='cloud'?'Mã voice cloud':'Voice mặc định nếu để trống'}/>}
          <Button disabled={busy||engine==='cloud'||engine==='piper'&&!voice}
            onClick={()=>onAudio(engine,engine==='none'?'':voice)}>{engine==='none'?'Tắt âm thanh':'Chỉ đọc phụ đề'}</Button>
          {onAudioDirect&&<Button type="primary" disabled={busy||engine==='none'||['cloud','piper'].includes(engine)&&!voice}
            onClick={()=>onAudioDirect(engine,voice,voices)}>AI lập kế hoạch âm thanh</Button>}
        </Space>
        {engine!=='none'&&Object.entries(job.cast??{}).map(([id,character])=><p key={id}>
          <label>{character.name} · voice riêng <Input value={voices[id]??''} maxLength={100}
            onChange={e=>setVoices(old=>({...old,[id]:e.target.value}))} placeholder="Để trống dùng voice mặc định"/></label>
        </p>)}
      </div>}
      <h3>Nội dung video</h3>
      <ScriptContent text={job.brief.idea}/>
      {!!job.storyboard_history?.length&&<>
        <h3>Phiên bản trước</h3>
        {job.storyboard_history.map(entry=><p key={entry.sha256}>Phiên bản {entry.storyboard.version} · {entry.storyboard.scenes.length} cảnh{entry.video_sha?' · Có MP4 đã lưu':''}</p>)}
      </>}
    </section>:<div className="storyboard-layout">
      <nav aria-label="Danh sách cảnh" className="storyboard-scenes">
        {groups.map(group=><div className={authoredScenes?'storyboard-scene-group storyboard-authored-group':'storyboard-scene-group'} key={group.key}>
          {authoredScenes&&<header><h4>{group.title??group.label}</h4>
            {group.title&&<span>{group.label}</span>}</header>}
          <div className={authoredScenes?'storyboard-shot-strip':undefined}>
          {group.shots.map(({scene:item,index:i})=><button key={item.shot_id??i} type="button" aria-pressed={index===i}
            aria-label={item.creative_shot?`${group.label} · Góc ${item.creative_shot} · Segment ${item.segment}/${item.segment_count}`:
              authoredScenes?`${group.label} · Shot ${item.content_shot}/${item.content_shot_count}`:undefined}
            onClick={()=>setShot(item.shot_id??i)}>
            <div className="storyboard-shot-meta">
              <strong>{item.creative_shot?`Góc ${item.creative_shot} · Segment ${item.segment}/${item.segment_count}`:
                authoredScenes?`Shot ${item.content_shot}`:group.label}</strong>
              <span>{Number(item.seconds.toFixed(2)).toLocaleString('vi-VN')} giây</span>
            </div>
            {!authoredScenes&&<span>{item.description}</span>}
          </button>)}
          </div>
        </div>)}
        {onAdd&&<Button disabled={busy} onClick={onAdd}>Thêm cảnh</Button>}
      </nav>
      {scene&&<article key={scene.shot_id??index} className="storyboard-detail">
        <header className="storyboard-scene-title"><h3>{scene.creative_shot?
          `${activeGroup.label} · Góc ${scene.creative_shot} · Segment ${scene.segment}/${scene.segment_count}`:scene.content_scene?
          `${activeGroup.label} · Shot ${scene.content_shot}/${scene.content_shot_count}`:'Cảnh '+(index+1)}</h3>
          <span>{Number(scene.seconds.toFixed(2)).toLocaleString('vi-VN')} giây</span>
        </header>
        <p>{scene.shot_description??scene.description}</p>
        {scene.creative_camera&&<p className="env-muted">Góc máy · {scene.creative_camera}</p>}
        {scene.shot_reason&&!authoredScenes&&<p className="env-muted">{scene.shot_reason}</p>}
        {scene.continuity_plan&&<div className="storyboard-context">
          <strong>{({CUT:'Chuyển cảnh',CAMERA_CHANGE:'Đổi góc',CONTINUE:'Tiếp nối frame cuối'})[scene.continuity_plan.transition]}</strong>
          <p>Bắt đầu: {scene.continuity_plan.start_state}</p><p>Kết thúc: {scene.continuity_plan.end_state}</p>
          {scene.continuity_plan.transition==='CONTINUE'&&<p className="env-muted">Ảnh bên dưới là ảnh dự kiến; clip dùng frame cuối đã xác minh của cảnh trước.</p>}
        </div>}
        {scene.asset&&<div className="storyboard-image"><Image loading="lazy" alt={'Ảnh cảnh '+(index+1)}
          src={'/api/film/drafts/'+job.id+'/scene-'+index+'?v='+scene.asset}/></div>}
        {activeGroup?.original&&<div className="storyboard-original-scene"><ScriptContent text={activeGroup.original}/></div>}
        {!!scene.character_ids?.length&&<Space wrap>{scene.character_ids.map(id=><Tag key={id}>{job.cast?.[id]?.name??id}</Tag>)}</Space>}
        {(scene.scene_notes||scene.continuity||job.board.continuity)&&<p>{scene.scene_notes||scene.continuity||job.board.continuity}</p>}
        {scene.caption&&<p><strong>Phụ đề</strong><br/>{scene.caption}</p>}
        {scene.script_range&&!activeGroup?.original&&<details><summary>Kịch bản gốc</summary>
          <ScriptContent text={Array.from(job.brief.idea).slice(...scene.script_range).join('')}/>
        </details>}
        <details><summary>Chi tiết AI</summary>
          <p><strong>Prompt ảnh</strong><br/>{scene.image_prompt}</p>
          {scene.motion_prompt&&<p><strong>Prompt chuyển động</strong><br/>{scene.motion_prompt}</p>}
          {scene.audio&&<p><strong>Âm thanh dự kiến</strong><br/>{scene.audio}</p>}
        </details>
        {visualReview&&<Alert showIcon type={visualReview.verdict==='FAIL'?'warning':'info'}
          message={'AI đánh giá frame mẫu · '+({PASS:'Mẫu phù hợp',FAIL:'Có lỗi',UNCERTAIN:'Chưa đủ bằng chứng'}[visualReview.verdict]??visualReview.verdict)}
          description={<div><p>{visualReview.summary}</p>{visualReview.issues.map((issue,i)=><p key={i}>• {issue}</p>)}
            {visualReview.repair_hint&&<p><strong>Gợi ý sửa:</strong> {visualReview.repair_hint}</p>}
            <p className="env-muted">{visualReview.model_id} · Chỉ đánh giá frame mẫu, không thay thế duyệt video.</p></div>}/>}
        <Space wrap className="storyboard-actions">
          {onVisualReview&&<Button disabled={busy} onClick={()=>onVisualReview(index)}>AI đánh giá cảnh</Button>}
          {onEdit&&<Button disabled={busy} onClick={()=>onEdit(index,scene)}>Sửa cảnh</Button>}
          {onRewrite&&<Button disabled={busy} onClick={()=>onRewrite(index,scene)}>AI viết lại</Button>}
          {onMove&&index>0&&<Button disabled={busy} onClick={()=>onMove(index,index-1)}>Đưa lên</Button>}
          {onMove&&index+1<scenes.length&&<Button disabled={busy} onClick={()=>onMove(index,index+1)}>Đưa xuống</Button>}
          {onRemove&&<Button danger disabled={busy} onClick={()=>onRemove(index)}>Bỏ cảnh</Button>}
          {onRegenerate&&scene.asset&&<Button disabled={busy} onClick={()=>onRegenerate(index,'image')}>Tạo lại ảnh{job.brief.mode==='motion'?' và chuyển động':''}</Button>}
          {onRegenerate&&scene.motion_sha&&job.brief.mode==='motion'&&<Button disabled={busy} onClick={()=>onRegenerate(index,'motion')}>Tạo lại chuyển động</Button>}
          {scene.motion_sha&&<Button onClick={()=>onPreview(index,scene.motion_sha)}>Xem chuyển động</Button>}
        </Space>
      </article>}
    </div>}
  </Modal>;
}
