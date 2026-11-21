import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Card,Collapse,Empty,Form,Image,Input,InputNumber,Modal,Select,Space,Tabs,Tag} from 'antd';
import {ReloadOutlined} from '@ant-design/icons';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {requestError} from '../api.js';
import {formatMemory,formatVram} from '../environment_format.js';
import {StudioPreview} from './StudioPreview.jsx';
import {ProductionProgress} from './ProductionProgress.jsx';
import './studio-draft-progress.css';

const API='/api/film/drafts';
const editorKey='agentforge.studio.video-brief.v1';
const briefDefaults={idea:'',seconds:12,motionSeconds:6,scene_count:3,ratio:'9:16',mode:'motion'};
const motionShots={4:2,6:3,15:8,30:15};
const motionMaxShots={4:2,6:3,15:9,30:16};
function savedBrief(){
  try {
    const saved=JSON.parse(localStorage.getItem(editorKey));
    return Object.fromEntries(Object.entries(briefDefaults).map(([key,value])=>[
      key,typeof saved?.[key]===typeof value?saved[key]:value,
    ]));
  } catch {
    return briefDefaults;
  }
}

function scriptAdvice(text,seconds,count){
  const headings=[...text.matchAll(/^[ \t]*(?:cảnh|scene)\s+\d+\b/gim)].length;
  if(headings>count)return 'Kịch bản có '+headings+' cảnh đánh số. Hãy tăng số cảnh hoặc chia kịch bản.';
  const lines=[...text.matchAll(/^[ \t]*(\p{L}[^:\n]{0,27}):[ \t]*(\S[^\n]*)/gmu)]
    .filter(match=>!/^(?:cảnh|scene)\s+\d+/i.test(match[1]));
  const words=lines.reduce((sum,line)=>sum+line[2].trim().split(/\s+/).length,0);
  if(words>seconds*3)return 'Thời lượng có thể không đủ cho các dòng lời thoại. Hãy tăng thời lượng hoặc chia kịch bản.';
  if(text.trim().split(/\s+/).length>seconds*6)
    return 'Kịch bản khá dày so với thời lượng. Cân nhắc tăng thời lượng hoặc chia thành nhiều bản nháp.';
  return null;
}
function draftError(failure) {
  if(failure.code==='draft_storage_unavailable')return failure.message;
  if(failure.code==='draft_not_found')return 'Bản nháp này không còn tồn tại. Bạn có thể tạo bản nháp mới.';
  if(failure.status===404)return 'Backend đang chạy chưa hỗ trợ bản nháp. Hãy khởi động lại AgentForge bằng phiên bản mới rồi thử lại.';
  return requestError(failure);
}
const labels={QUEUED:'Đã tiếp nhận',PLANNING:'Đang lập kế hoạch',STORYBOARD:'Đang viết storyboard',
  STORYBOARD_REVIEW:'Storyboard chờ duyệt',NEEDS_RECONCILIATION:'Cần đối soát',INTERRUPTED:'Đã gián đoạn',
  IMAGES:'Đang tạo ảnh từng cảnh',MOTION:'Đang tạo chuyển động',RENDER:'Đang dựng MP4',VERIFY:'Đang xác minh MP4',
  REVIEW:'Phim hoàn chỉnh · chờ duyệt',RUNNING:'Đang sản xuất',
  FAILED:'Cần xử lý',APPROVED:'Đã duyệt',REJECTED:'Đã từ chối',
  WAITING_RESOURCES:'Chờ tài nguyên',CANCELLED:'Đã hủy'};
const warnings={RAM_LOW:'RAM khả dụng không đủ',COMMIT_LOW:'Hạn mức bộ nhớ cam kết không đủ',
  VRAM_LOW:'VRAM khả dụng không đủ',GPU_BUSY:'Một tác vụ local đang sử dụng GPU',
  RAM_UNAVAILABLE:'Không đo được RAM khả dụng',COMMIT_UNAVAILABLE:'Không đo được dư địa commit Windows',
  VRAM_UNAVAILABLE:'Không đo được VRAM khả dụng',
  COMFYUI_QUEUE_BUSY:'ComfyUI còn tác vụ đang chạy hoặc đang chờ.',
  COMFYUI_QUEUE_UNAVAILABLE:'Chưa xác minh được hàng đợi ComfyUI.',
  MOTION_RECONCILIATION_REQUIRED:'Cần đối soát tác vụ chuyển động trước khi nhận GPU.',
  GPU_RESOURCE_FAILURE:'ComfyUI báo lỗi bộ nhớ. Kiểm tra tài nguyên trước khi tiếp tục từ checkpoint.',
  OLLAMA_RESOURCE_OR_SERVER_ERROR:'Ollama trả lỗi máy chủ. Kiểm tra tài nguyên và log trước khi tiếp tục.',
  COMFYUI_LAUNCHER_REQUIRED:'ComfyUI đang tắt và chưa có launcher. Vào Cài đặt → Môi trường & Tài nguyên → Cấu hình launcher, chọn hồ sơ FLUX và thư mục ComfyUI Portable, rồi tiếp tục từ checkpoint.',
  COMFYUI_ENDPOINT_MISMATCH:'Cổng của hồ sơ FLUX khác với launcher đã lưu. Kiểm tra endpoint trong Model Hub, sau đó lưu lại launcher trong Môi trường & Tài nguyên và tiếp tục từ checkpoint.',
  COMFYUI_UNAVAILABLE:'ComfyUI không phản hồi. Kiểm tra trạng thái và launcher tại Cài đặt → Môi trường & Tài nguyên, rồi tiếp tục từ checkpoint.',
  'ComfyUI scene result: COMFYUI_STOPPED':'ComfyUI đã dừng giữa cảnh. Chọn Tiếp tục từ checkpoint để khởi động lại và xử lý cảnh còn thiếu.'};
function usage(total,available,format) {
  if(!Number.isFinite(total)||!Number.isFinite(available)||available<0||available>total)return 'Chưa đo được';
  return format(total-available)+' / '+format(available);
}

const historyStates=new Set(['APPROVED','REJECTED','CANCELLED']);
const statusColors={RUNNING:'processing',QUEUED:'blue',REVIEW:'purple',FAILED:'error',
  WAITING_RESOURCES:'warning',APPROVED:'success'};
const draftDate=new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short'});

function draftPriority(job){
  if(job.worker_active)return 0;
  if(['FAILED','WAITING_RESOURCES','RUNNING'].includes(job.status))return 1;
  return job.status==='REVIEW'?2:3;
}

function DraftLabel({job}){
  const title=job.board?.title||job.brief.idea;
  const stamp=job.created_at||job.updated_at;
  const date=stamp&&new Date(stamp);
  const status=job.status==='RUNNING'&&!job.worker_active?'Đã gián đoạn':
    labels[job.status==='RUNNING'?job.stage:job.status]??job.status;
  return <div className="draft-row-label">
    <div className="draft-row-heading">
      <strong title={title}>{title}</strong>
      <Tag color={job.status==='RUNNING'&&!job.worker_active?'warning':statusColors[job.status]}>{status}</Tag>
    </div>
    <div className="draft-row-meta env-muted">
      {date&&Number.isFinite(date.getTime())&&<time dateTime={stamp}>
        {job.created_at?'Tạo ':'Cập nhật '}{draftDate.format(date)}
      </time>}
      {job.brief.seconds&&<span>{job.brief.seconds} giây</span>}
      {job.brief.ratio&&<span>{job.brief.ratio}</span>}
      <span>{job.brief.mode==='motion'?'Chuyển động LTX':'Ảnh tĩnh pan/zoom'}</span>
      {job.board&&<span>{job.board.scenes.filter(scene=>scene.asset).length}/{job.board.scenes.length} ảnh</span>}
    </div>
  </div>;
}

export function StudioDrafts({mutate,onCharacters}) {
  const [form]=Form.useForm();
  const [initialBrief]=useState(savedBrief);
  const [saveFailed,setSaveFailed]=useState(false);
  const values=Form.useWatch([],form)??initialBrief;
  const moving=(Form.useWatch('mode',form)??initialBrief.mode)==='motion';
  const limit=20000;
  const characterCount=Array.from(values.idea??'').length;
  const selectedSeconds=values.motionSeconds??6;
  const advice=scriptAdvice(values.idea??'',moving?selectedSeconds:values.seconds,
    moving?motionShots[selectedSeconds]:values.scene_count);
  const {data,reload,setData,...resource}=useResource(API);
  const {data:capacity,reload:refreshCapacity}=useResource(API+'/resources');
  useScreenRefresh(reload);
  const busy=useRef(false);
  const request=useRef(null);
  const [pending,setPending]=useState(false);
  const [scenePreview,setScenePreview]=useState(null);
  const [starting,setStarting]=useState(false);
  const [error,setError]=useState(null);
  const [editor,setEditor]=useState(null);
  const [missing,setMissing]=useState([]);
  const [filter,setFilter]=useState('work');
  const [previewId,setPreviewId]=useState(null);
  const drafts=Array.isArray(data?.drafts)?data.drafts.filter(job=>!missing.includes(job.id)):[];
  const visibleDrafts=drafts.filter(job=>historyStates.has(job.status)===(filter==='history'))
    .sort((a,b)=>draftPriority(a)-draftPriority(b));
  const preview=drafts.find(job=>job.id===previewId&&job.video_sha);
  const listError=resource.error?draftError(resource.error):
    data&&!Array.isArray(data.drafts)?'API bản nháp trả dữ liệu không hợp lệ.':null;
  const active=drafts.find(job=>job.status==='RUNNING'&&job.worker_active);
  const featured=active??visibleDrafts[0];
  const running=!listError&&Boolean(active);
  const queued=drafts.filter(job=>job.status==='QUEUED').length;
  const waiting=drafts.filter(job=>job.status==='WAITING_RESOURCES').length;
  useEffect(()=>{
    if(!running&&!waiting&&!queued)return;
    const timer=setInterval(refreshCapacity,15000);
    return ()=>clearInterval(timer);
  },[running,waiting,queued,refreshCapacity]);
  useEffect(()=>{
    if((!running&&(!queued||waiting))||resource.loading||listError)return;
    const timer=setTimeout(reload,2500);
    return ()=>clearTimeout(timer);
  },[reload,running,queued,waiting,resource.loading,listError]);

  async function run(path,body,done) {
    if(busy.current)return;
    busy.current=true;
    setPending(true);
    setStarting(path==='/start'||path.endsWith('/resume'));
    setError(null);
    try {
      const result=await mutate(API+path,body,{inlineError:true});
      if(result?.id&&result.status==='RUNNING'&&(path==='/start'||path.endsWith('/resume'))) {
        setData({drafts:[{...result,worker_active:true},...drafts.filter(job=>job.id!==result.id)]});
      }
      done?.();
      await reload();
    } catch(failure) {
      setError(draftError(failure));
      if(failure.code==='draft_not_found'&&path!=='/start') {
        setMissing(ids=>[...ids,path.split('/')[1]]);
        setEditor(null);
      }
      if(path==='/start'&&failure.status>=400&&failure.status<500)request.current=null;
      if(failure.code==='draft_not_found'||!failure.status)await reload();
    } finally {
      busy.current=false;
      setPending(false);
      setStarting(false);
    }
  }

  function submit(values) {
    const motion=values.mode==='motion';
    const payload={idea:values.idea,mode:values.mode,seconds:motion?values.motionSeconds:values.seconds,
      scene_count:motion?motionShots[values.motionSeconds]:values.scene_count,ratio:motion?'16:9':values.ratio};
    const brief=JSON.stringify(payload);
    if(request.current?.brief!==brief)request.current={brief,id:crypto.randomUUID().replaceAll('-','')};
    return run('/start',{...payload,id:request.current.id},()=>{request.current=null;setFilter('work');});
  }

  function storyboard(job,action,fields={}){
    return run('/'+job.id+'/storyboard-'+action,{sha256:job.storyboard_sha,...fields});
  }

  function approveStoryboard(job){
    const motion=job.brief.mode==='motion';
    Modal.confirm({title:'Duyệt storyboard và chạy production',
      content:`${job.brief.scene_count} cảnh, tối đa ${job.brief.scene_count} lượt FLUX${motion?' và LTX':''}, chạy tuần tự. Phim ${job.brief.seconds} giây. Tác vụ dừng khi lỗi hoặc thiếu tài nguyên.`,
      okText:'Duyệt và tạo phim',cancelText:'Quay lại',onOk:()=>storyboard(job,'approve')});
  }

  return <>
    <Card className="env-panel" title="Tạo video từ ý tưởng"
      extra={<Button onClick={onCharacters}>Thư viện nhân vật</Button>}>
    <Form form={form} layout="vertical" onFinish={submit} initialValues={initialBrief}
      onValuesChange={(_,next)=>{
        try {
          localStorage.setItem(editorKey,JSON.stringify(next));
          setSaveFailed(false);
        } catch {
          setSaveFailed(true);
        }
      }}>
      <Form.Item className="draft-editor-field" label="Nội dung video" name="idea"
        rules={[{required:true,whitespace:true,message:'Nhập ý tưởng hoặc kịch bản video.'},
          {validator:(_,value)=>Array.from(value??'').length<=limit?Promise.resolve():
            Promise.reject(new Error('Nội dung vượt giới hạn '+limit.toLocaleString('vi-VN')+' ký tự.'))}]}
        extra={<span className="draft-editor-count">
          {characterCount.toLocaleString('vi-VN')} / {limit.toLocaleString('vi-VN')} ký tự
        </span>}>
        <Input.TextArea autoSize={{minRows:7,maxRows:20}} spellCheck={false}
          placeholder="Mô tả ý tưởng hoặc nhập kịch bản bạn muốn AI thực hiện..."/>
      </Form.Item>
      {saveFailed&&<Alert type="warning" showIcon message="Trình duyệt không lưu được nội dung để khôi phục khi tải lại."/>}
      {advice&&<Alert type="warning" showIcon message={advice}/>}
      <div className="draft-form-options">
        <Form.Item name="mode" label="Kiểu video" rules={[{required:true}]}>
          <Select onChange={value=>{if(value==='motion'&&form.getFieldValue('scene_count')>3)form.setFieldValue('scene_count',3);}}
            options={[{value:'motion',label:'Phim chuyển động LTX'},{value:'still',label:'Ảnh tĩnh pan/zoom'}]}/>
        </Form.Item>
        {!moving&&<Form.Item name="seconds" label="Thời lượng (giây)" rules={[{required:true,type:'integer',min:6,max:60}]}>
          <InputNumber min={6} max={60}/>
        </Form.Item>}
        {moving?<Form.Item name="motionSeconds" label="Thời lượng phim" rules={[{required:true}]}>
          <Select options={Object.keys(motionShots).map(value=>({value:Number(value),label:value+' giây'}))}/>
        </Form.Item>:<Form.Item name="scene_count" label="Số cảnh" rules={[{required:true,type:'integer',min:2,max:6}]}>
          <InputNumber min={2} max={6}/>
        </Form.Item>}
        {!moving&&<Form.Item name="ratio" label="Tỷ lệ khung hình">
          <Select options={['9:16','16:9'].map(value=>({value,label:value}))}/>
        </Form.Item>}
        <Button className="draft-submit" type="primary" htmlType="submit"
          loading={pending} disabled={waiting>0||characterCount>limit}>Tạo storyboard</Button>
      </div>
    </Form>
    {moving&&<p className="env-muted">16:9 · {selectedSeconds===30?'AI chọn 15–16 cảnh':motionShots[selectedSeconds]+' cảnh'} · Tạo ảnh và chuyển động sau khi duyệt storyboard.</p>}
    {!listError&&(starting||featured)&&<ProductionProgress job={featured} starting={starting&&!active}
      labels={labels} warnings={warnings} busy={pending}
      onCancel={featured?()=>run('/'+featured.id+'/cancel',{}):null}
      onResume={featured&&!running?()=>run('/'+featured.id+'/resume',{}):null}/>}
    {!listError&&waiting>0&&<Alert showIcon type="warning" message="Bản nháp đang chờ tài nguyên"
      description={[...new Set(drafts.filter(job=>job.status==='WAITING_RESOURCES').map(job=>warnings[job.error]??job.error).filter(Boolean))].join(' · ')}/>}
    <details className="draft-resource-details env-muted">
      <summary>Tài nguyên{queued>0&&' · '+queued+' trong hàng đợi'}{waiting>0&&' · '+waiting+' đang chờ'}</summary>
      <Space wrap>
        <span>RAM dùng / khả dụng: {usage(capacity?.ram_total,capacity?.ram_available,formatMemory)}</span>
        <span>VRAM dùng / khả dụng: {usage(capacity?.vram_total_mib,capacity?.vram_free_mib,formatVram)}</span>
      </Space>
    </details>
    </Card>
    <Card className="env-panel studio-drafts-list" title="Bản nháp"
      extra={!listError&&<Button icon={<ReloadOutlined/>} onClick={()=>{reload();refreshCapacity();}}
        loading={resource.loading}>Làm mới</Button>}>
    {error&&<Alert showIcon type="error" message={error}/>}
    {listError?<Alert showIcon type="error" message="Không đọc được bản nháp"
      description={listError} action={<Button onClick={reload}>Thử lại bản nháp</Button>}/>:
      <ResourceStatus resource={{...resource,loading:resource.loading&&!data&&!starting,data,reload}}
        label="bản nháp"/>}
    {data&&!listError&&<Tabs className="draft-filters" activeKey={filter} onChange={setFilter}
      items={[{key:'work',label:'Đang xử lý & chờ duyệt'},{key:'history',label:'Đã kết thúc'}]}/>}
    {!starting&&!resource.loading&&!listError&&data&&visibleDrafts.length===0&&
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={filter==='history'?'Chưa có bản nháp đã kết thúc':'Chưa có bản nháp'}/>}
    {visibleDrafts.length>0&&<Collapse className="draft-list" accordion destroyOnHidden items={visibleDrafts.map(job=>({key:job.id,
      label:<DraftLabel job={job}/>,
      extra:job.video_sha&&<Button size="small" onKeyDown={event=>event.stopPropagation()}
        onClick={event=>{event.stopPropagation();setPreviewId(job.id);}}>Xem bản nháp MP4</Button>,
      children:<>
        {job.error&&<Alert showIcon type={job.status==='WAITING_RESOURCES'?'warning':'error'}
          message={warnings[job.error]??job.error}/>}
        {job.id!==featured?.id&&['RUNNING','FAILED','QUEUED','WAITING_RESOURCES','INTERRUPTED','NEEDS_RECONCILIATION'].includes(job.status)&&!job.worker_active&&<Button size="small" disabled={pending||running}
          onClick={()=>run('/'+job.id+'/resume',{})}>Tiếp tục từ checkpoint</Button>}
        {job.id!==featured?.id&&['RUNNING','QUEUED','WAITING_RESOURCES'].includes(job.status)&&<Button size="small"
          disabled={pending} onClick={()=>run('/'+job.id+'/cancel',{})}>Hủy tác vụ</Button>}
        {!job.board?.scenes.some(scene=>scene.script_range)?<p className="draft-source-text">
          <strong>Nội dung video</strong><br/>{job.brief.idea}
        </p>:null}
        {job.plan&&<p>{job.plan}</p>}
        {job.storyboard_version&&job.board&&<Space wrap>
          <Tag>Storyboard v{job.storyboard_version}</Tag>
          {job.status==='STORYBOARD_REVIEW'&&<Button type="primary" disabled={pending||running}
            onClick={()=>approveStoryboard(job)}>Duyệt storyboard</Button>}
          {job.status==='STORYBOARD_REVIEW'&&(job.brief.mode==='motion'?
            job.board.scenes.length<motionMaxShots[job.brief.seconds]:
            job.board.scenes.length<Math.min(6,Math.floor(job.brief.seconds/2)))&&
            <Button disabled={pending||running} onClick={()=>setEditor({job,adding:true,index:job.board.scenes.length,scene:{}})}>Thêm cảnh</Button>}
        </Space>}
        {!!job.storyboard_history?.length&&<details>
          <summary>Lịch sử storyboard</summary>
          <ul>{job.storyboard_history.map(entry=><li key={entry.sha256}>
            Phiên bản {entry.storyboard.version} · {entry.storyboard.scenes.length} cảnh
            {entry.video_sha?' · Có MP4 đã lưu':''}
          </li>)}</ul>
        </details>}
        {job.board&&<ul className="studio-shot-list">{job.board.scenes.map((scene,index)=><li key={scene.shot_id??index}>
          <strong>Cảnh {index+1} · {Number(scene.seconds.toFixed(2)).toLocaleString('vi-VN')} giây</strong>
          <p>{scene.description}</p>
          {job.storyboard_version&&<details>
            <summary>Prompt và tính liên tục</summary>
            <p>Ảnh · {scene.image_prompt}</p><p>Chuyển động · {scene.motion_prompt}</p>
            <p>{scene.continuity??job.board.continuity}</p>
            {scene.scene_notes&&<p>{scene.scene_notes}</p>}
            {scene.caption&&<p>Phụ đề · {scene.caption}</p>}
          </details>}
          {scene.script_range&&<details>
            <summary>Kịch bản gốc của cảnh</summary>
            <p className="draft-source-text">{Array.from(job.brief.idea).slice(...scene.script_range).join('')}</p>
          </details>}
          {scene.character_ids.map(id=><Tag key={id}>{job.cast[id]?.name}</Tag>)}
          <p className="env-muted">Âm thanh dự kiến: {scene.audio}</p>
          {scene.asset&&<Image width={180} loading="lazy" alt={'Ảnh cảnh '+(index+1)}
            src={API+'/'+job.id+'/scene-'+index+'?v='+scene.asset}/>}
          {job.storyboard_version||job.brief.mode==='motion'?<div>
            {scene.asset&&<Tag>Đã tạo ảnh</Tag>}
            {scene.motion_sha&&<Tag color="green">Đã xác minh clip chuyển động</Tag>}
            {scene.motion_sha&&<Button size="small"
              onClick={()=>setScenePreview({id:job.id,index,sha:scene.motion_sha})}>Xem chuyển động</Button>}
            {job.storyboard_version&&['STORYBOARD_REVIEW','FAILED','REVIEW','APPROVED','REJECTED'].includes(job.status)&&
              <Space size="small" wrap>
                <Button size="small" disabled={pending||running} onClick={()=>setEditor({job,index,scene})}>Sửa cảnh</Button>
                <Button size="small" disabled={pending||running} onClick={()=>setEditor({job,index,scene,rewrite:true})}>AI viết lại</Button>
                {index>0&&<Button size="small" disabled={pending||running}
                  onClick={()=>storyboard(job,'move',{index,target:index-1})}>Đưa lên</Button>}
                {(job.brief.mode==='motion'?job.board.scenes.length>motionShots[job.brief.seconds]:
                  job.board.scenes.length>2)&&<Button size="small" danger disabled={pending||running}
                  onClick={()=>storyboard(job,'remove',{index})}>Bỏ cảnh</Button>}
              </Space>}
          </div>:<div><Button size="small" disabled={running||pending||job.status==='APPROVED'}
            onClick={()=>setEditor({id:job.id,index,scene})}>Sửa cảnh / tạo lại ảnh</Button></div>}
        </li>)}</ul>}
      </>,
    }))}/>}
    </Card>
    {scenePreview&&<Modal open title={'Chuyển động cảnh '+(scenePreview.index+1)} footer={null}
      onCancel={()=>setScenePreview(null)}>
      <StudioPreview key={scenePreview.sha} initiallyOpen label="Xem clip chuyển động" filename="motion.mp4"
        url={API+'/'+scenePreview.id+'/motion-'+scenePreview.index+'?v='+scenePreview.sha}/>
    </Modal>}
    {preview&&<Modal open title={preview.board?.title||'Xem bản nháp MP4'} footer={null}
      onCancel={()=>setPreviewId(null)}>
      <StudioPreview key={preview.video_sha} url={API+'/'+preview.id+'/preview?v='+preview.video_sha}
        filename="draft.mp4" label="Xem bản nháp MP4" initiallyOpen reviewActions={preview.status==='REVIEW'?<>
        <Button type="primary" disabled={pending}
          onClick={()=>run('/'+preview.id+'/approve',{sha256:preview.video_sha},()=>setPreviewId(null))}>Duyệt bản nháp</Button>
        <Button danger disabled={pending}
          onClick={()=>run('/'+preview.id+'/reject',{sha256:preview.video_sha},()=>setPreviewId(null))}>Từ chối</Button>
      </>:null}/>
      {preview.receipt_sha&&<Space wrap>
        <Tag>Kỹ thuật đã xác minh</Tag><Tag>Hình ảnh chờ kiểm tra</Tag>
        <a href={API+'/'+preview.id+'/receipt'}>Tải biên nhận</a>
        {preview.subtitle_sha&&<a href={API+'/'+preview.id+'/captions'}>Tải phụ đề SRT</a>}
      </Space>}
    </Modal>}
    {editor&&<Modal open title={(editor.rewrite?'AI viết lại cảnh ':editor.adding?'Thêm cảnh ':'Sửa cảnh ')+(editor.index+1)} footer={null}
      onCancel={()=>setEditor(null)}>
      <Form layout="vertical" initialValues={editor.scene} onFinish={values=>editor.job?
        run('/'+editor.job.id+'/storyboard-'+(editor.rewrite?'rewrite':editor.adding?'add':'edit'),
          {...values,index:editor.index,sha256:editor.job.storyboard_sha},()=>setEditor(null)):
        run('/'+editor.id+'/edit',{...values,index:editor.index},()=>setEditor(null))}>
        {editor.rewrite?<Form.Item label="Yêu cầu viết lại" name="feedback" rules={[{required:true,whitespace:true}]}>
          <Input.TextArea maxLength={350}/>
        </Form.Item>:<>
        <Form.Item name="description" label="Nội dung cảnh" rules={[{required:true,whitespace:true}]}>
          <Input.TextArea maxLength={350}/>
        </Form.Item>
        <Form.Item name="image_prompt" label="Prompt ảnh" rules={[{required:true,whitespace:true}]}>
          <Input.TextArea maxLength={600}/>
        </Form.Item>
        {editor.job&&<Form.Item name="motion_prompt" label="Prompt chuyển động" rules={[{required:true,whitespace:true}]}
          hidden={editor.job.brief.mode!=='motion'} initialValue={editor.adding?'Ảnh tĩnh pan/zoom':undefined}>
          <Input.TextArea maxLength={600}/>
        </Form.Item>}
        {editor.job&&<>
          <Form.Item name="scene_notes" label="Bối cảnh, trang phục, đạo cụ và góc máy">
            <Input.TextArea maxLength={240}/>
          </Form.Item>
          <Form.Item name="caption" label="Phụ đề của cảnh"><Input maxLength={220}/></Form.Item>
        </>}
        </>}
        <Button type="primary" htmlType="submit" loading={pending}>Lưu cảnh</Button>
      </Form>
    </Modal>}
  </>;
}
