import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Card,Collapse,Empty,Form,Image,Input,InputNumber,Modal,Select,Space,Tabs,Tag} from 'antd';
import {ReloadOutlined} from '@ant-design/icons';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {requestError} from '../api.js';
import {formatMemory,formatVram} from '../environment_format.js';
import {StudioPreview} from './StudioPreview.jsx';
import './studio-draft-progress.css';

const API='/api/film/drafts';
const editorKey='agentforge.studio.video-brief.v1';
const briefDefaults={idea:'',seconds:12,scene_count:3,ratio:'9:16',mode:'motion'};
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
  IMAGES:'Đang tạo ảnh từng cảnh',MOTION:'Đang tạo chuyển động',RENDER:'Đang dựng và kiểm tra MP4',REVIEW:'Phim hoàn chỉnh · chờ duyệt',
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

const allStages=[['PLANNING','Lập kế hoạch'],['STORYBOARD','Storyboard'],['IMAGES','Tạo ảnh'],['MOTION','Tạo chuyển động'],['RENDER','Dựng MP4']];
const providers={ollama:'Ollama',comfyui:'ComfyUI'};
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

function DraftProgress({job,starting}) {
  const activity=job?.activity;
  const stages=allStages.filter(([key])=>key!=='MOTION'||job?.brief?.mode==='motion');
  const current=stages.findIndex(([key])=>key===job?.stage);
  const scenes=job?.board?.scenes??[];
  const completed=scenes.filter(scene=>scene.asset).length;
  const title=starting?'Đang gửi yêu cầu':activity?.operation==='cast'?'Đang chọn nhân vật':
    activity?.operation==='script'?'Đang phân tích kịch bản · cảnh '+activity.scene:
    activity?.operation==='image'&&activity.scene? 'Đang tạo ảnh cảnh '+activity.scene+'/'+scenes.length:
    activity?.operation==='motion'&&activity.scene? 'Đang tạo chuyển động cảnh '+activity.scene+'/'+scenes.length:
    labels[job?.stage]??'Đang chuẩn bị bản nháp';
  return <section className="draft-progress" aria-label="Tiến độ tạo bản nháp">
    <div className="draft-progress-now" role="status">
      <span className="draft-progress-spinner" aria-hidden="true"/>
      <div>
        <strong>{title}</strong>
        {activity?.model&&<div className="env-muted env-break">
          {providers[activity.provider]??activity.provider} · {activity.model}
        </div>}
        {activity?.operation==='render'&&<div className="env-muted">FFmpeg · Kiểm tra đầu ra MP4</div>}
        {job?.stage==='IMAGES'&&<div className="env-muted">{completed}/{scenes.length} ảnh đã sẵn sàng</div>}
        {job?.stage==='MOTION'&&<div className="env-muted">{scenes.filter(scene=>scene.motion_sha).length}/{scenes.length} clip đã xác minh</div>}
      </div>
    </div>
    <ol className="draft-progress-steps">
      {stages.map(([key,label],index)=><li key={key}
        className={index<current?'is-complete':index===current?'is-current':undefined}
        aria-current={index===current?'step':undefined}>{label}</li>)}
    </ol>
  </section>;
}

export function StudioDrafts({mutate,onCharacters}) {
  const [form]=Form.useForm();
  const [initialBrief]=useState(savedBrief);
  const [saveFailed,setSaveFailed]=useState(false);
  const values=Form.useWatch([],form)??initialBrief;
  const moving=(Form.useWatch('mode',form)??initialBrief.mode)==='motion';
  const limit=20000;
  const characterCount=Array.from(values.idea??'').length;
  const advice=scriptAdvice(values.idea??'',moving?2*(values.scene_count??3):values.seconds,values.scene_count);
  const {data,reload,setData,...resource}=useResource(API);
  const {data:capacity,reload:refreshCapacity}=useResource(API+'/resources');
  useScreenRefresh(reload);
  const busy=useRef(false);
  const request=useRef(null);
  const [pending,setPending]=useState(false);
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
    const payload={...values,...(motion?{seconds:values.scene_count*2,ratio:'16:9'}:{}),motion_approved:motion};
    function start(){
      const brief=JSON.stringify(payload);
      if(request.current?.brief!==brief)request.current={brief,id:crypto.randomUUID().replaceAll('-','')};
      return run('/start',{...payload,id:request.current.id},()=>{request.current=null;setFilter('work');});
    }
    if(!motion)return start();
    Modal.confirm({title:'Duyệt chạy GPU cho phim động',
      content:`Tối đa ${values.scene_count} ảnh FLUX và ${values.scene_count} lượt LTX 49 frame, chạy tuần tự. Phim ${payload.seconds} giây, 16:9. LTX cần RAM trống 12 GiB, dư địa commit Windows 20 GiB và VRAM trống 8 GiB trước mỗi lượt. Tác vụ dừng nếu một cảnh lỗi.`,
      okText:'Duyệt và tạo phim',cancelText:'Quay lại',onOk:start});
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
        <Form.Item name="scene_count" label="Số cảnh" rules={[{required:true,type:'integer',min:2,max:moving?3:6}]}>
          <InputNumber min={2} max={moving?3:6}/>
        </Form.Item>
        {!moving&&<Form.Item name="ratio" label="Tỷ lệ khung hình">
          <Select options={['9:16','16:9'].map(value=>({value,label:value}))}/>
        </Form.Item>}
        <Button className="draft-submit" type="primary" htmlType="submit"
          loading={pending} disabled={waiting>0||characterCount>limit}>Tạo bản nháp</Button>
      </div>
    </Form>
    {moving&&<p className="env-muted">16:9 · Hai giây mỗi cảnh · Dùng ảnh FLUX và tạo chuyển động bằng LTX.</p>}
    {(starting||running)&&<DraftProgress job={active} starting={starting&&!active}/>}
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
        {['RUNNING','FAILED','QUEUED','WAITING_RESOURCES'].includes(job.status)&&!job.worker_active&&<Button size="small" disabled={pending||running}
          onClick={()=>run('/'+job.id+'/resume',{})}>Tiếp tục từ checkpoint</Button>}
        {['RUNNING','QUEUED','WAITING_RESOURCES'].includes(job.status)&&<Button size="small"
          disabled={pending} onClick={()=>run('/'+job.id+'/cancel',{})}>Hủy tác vụ</Button>}
        {!job.board?.scenes.some(scene=>scene.script_range)?<p className="draft-source-text">
          <strong>Nội dung video</strong><br/>{job.brief.idea}
        </p>:null}
        {job.plan&&<p>{job.plan}</p>}
        {job.board&&<ul className="studio-shot-list">{job.board.scenes.map((scene,index)=><li key={index}>
          <strong>Cảnh {index+1} · {scene.seconds} giây</strong>
          <p>{scene.description}</p>
          {scene.script_range&&<details>
            <summary>Kịch bản gốc của cảnh</summary>
            <p className="draft-source-text">{Array.from(job.brief.idea).slice(...scene.script_range).join('')}</p>
          </details>}
          {scene.character_ids.map(id=><Tag key={id}>{job.cast[id]?.name}</Tag>)}
          <p className="env-muted">Âm thanh dự kiến: {scene.audio}</p>
          {scene.asset&&<Image width={180} loading="lazy" alt={'Ảnh cảnh '+(index+1)}
            src={API+'/'+job.id+'/scene-'+index+'?v='+scene.asset}/>}
          {job.brief.mode==='motion'?<div>
            {scene.asset&&<Tag>Đã tạo ảnh</Tag>}
            {scene.motion_sha&&<Tag color="green">Đã xác minh clip chuyển động</Tag>}
          </div>:<div><Button size="small" disabled={running||pending||job.status==='APPROVED'}
            onClick={()=>setEditor({id:job.id,index,scene})}>Sửa cảnh / tạo lại ảnh</Button></div>}
        </li>)}</ul>}
      </>,
    }))}/>}
    </Card>
    {preview&&<Modal open title={preview.board?.title||'Xem bản nháp MP4'} footer={null}
      onCancel={()=>setPreviewId(null)}>
      <StudioPreview key={preview.video_sha} url={API+'/'+preview.id+'/preview?v='+preview.video_sha}
        filename="draft.mp4" label="Xem bản nháp MP4" initiallyOpen reviewActions={preview.status==='REVIEW'?<>
        <Button type="primary" disabled={pending}
          onClick={()=>run('/'+preview.id+'/approve',{sha256:preview.video_sha},()=>setPreviewId(null))}>Duyệt bản nháp</Button>
        <Button danger disabled={pending}
          onClick={()=>run('/'+preview.id+'/reject',{sha256:preview.video_sha},()=>setPreviewId(null))}>Từ chối</Button>
      </>:null}/>
    </Modal>}
    {editor&&<Modal open title={'Sửa cảnh '+(editor.index+1)} footer={null}
      onCancel={()=>setEditor(null)}>
      <Form layout="vertical" initialValues={editor.scene} onFinish={values=>run(
        '/'+editor.id+'/edit',{...values,index:editor.index},()=>setEditor(null))}>
        <Form.Item name="description" label="Nội dung cảnh" rules={[{required:true,whitespace:true}]}>
          <Input.TextArea maxLength={350}/>
        </Form.Item>
        <Form.Item name="image_prompt" label="Prompt ảnh" rules={[{required:true,whitespace:true}]}>
          <Input.TextArea maxLength={600}/>
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={pending}>Lưu cảnh</Button>
      </Form>
    </Modal>}
  </>;
}
