import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Card,Collapse,Empty,Form,Input,InputNumber,Modal,Select,Space,Tabs,Tag} from 'antd';
import {ReloadOutlined} from '@ant-design/icons';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {requestError} from '../api.js';
import {formatMemory,formatVram} from '../environment_format.js';
import {StudioPreview} from './StudioPreview.jsx';
import {StoryboardReview} from './StoryboardReview.jsx';
import {ProductionProgress} from './ProductionProgress.jsx';
import './studio-draft-progress.css';

const API='/api/film/drafts';
const editorKey='agentforge.studio.video-brief.v1';
const briefDefaults={idea:'',durationMode:'auto',targetSeconds:12,ratio:'9:16',mode:'motion'};
const motionShots={4:2,6:3,15:8,30:15};
const videoModes={motion:'Có chuyển động',still:'Ảnh tĩnh (lia và thu phóng)'};
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

function draftError(failure) {
  if(failure.code==='draft_storage_unavailable')return failure.message;
  if(failure.code==='draft_not_found')return 'Bản nháp này không còn tồn tại. Bạn có thể tạo bản nháp mới.';
  if(failure.status===404)return 'Backend đang chạy chưa hỗ trợ bản nháp. Hãy khởi động lại AgentForge bằng phiên bản mới rồi thử lại.';
  return requestError(failure);
}
const labels={QUEUED:'Đã tiếp nhận',PLANNING:'Đang lập kế hoạch',STORYBOARD:'Đang viết storyboard',
  STORYBOARD_REVIEW:'Storyboard chờ duyệt',NEEDS_RECONCILIATION:'Cần đối soát',INTERRUPTED:'Đã gián đoạn',
  IMAGES:'Đang tạo ảnh từng cảnh',MOTION:'Đang tạo chuyển động',RENDER:'Đang dựng MP4',VERIFY:'Đang xác minh MP4',
  REVIEW:'Video hoàn chỉnh · chờ duyệt',RUNNING:'Đang sản xuất',
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

const draftTimestamp=job=>Number.isFinite(Date.parse(job.updated_at))?job.updated_at:job.created_at;
const draftTime=job=>Date.parse(draftTimestamp(job))||0;

function DraftLabel({job}){
  const title=job.board?.title||job.brief.idea;
  const stamp=draftTimestamp(job);
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
        {stamp!==job.created_at?'Cập nhật ':'Tạo '}{draftDate.format(date)}
      </time>}
      {job.brief.seconds&&<span>{job.brief.seconds} giây</span>}
      {job.brief.ratio&&<span>{job.brief.ratio}</span>}
      <span>{videoModes[job.brief.mode==='motion'?'motion':'still']}</span>
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
  const manual=(Form.useWatch('durationMode',form)??initialBrief.durationMode)==='manual';
  const {data,reload,setData,...resource}=useResource(API);
  const {data:capacity,reload:refreshCapacity}=useResource(API+'/resources');
  useScreenRefresh(reload);
  const busy=useRef(false);
  const request=useRef(null);
  const filmsRef=useRef(null);
  const [pending,setPending]=useState(false);
  const [scenePreview,setScenePreview]=useState(null);
  const [starting,setStarting]=useState(false);
  const [error,setError]=useState(null);
  const [editor,setEditor]=useState(null);
  const [missing,setMissing]=useState([]);
  const [filter,setFilter]=useState('work');
  const [previewId,setPreviewId]=useState(null);
  const [selectedId,setSelectedId]=useState(null);
  const [storyboardId,setStoryboardId]=useState(null);
  const drafts=Array.isArray(data?.drafts)?data.drafts.filter(job=>!missing.includes(job.id)):[];
  const visibleDrafts=drafts.filter(job=>historyStates.has(job.status)===(filter==='history'))
    .sort((a,b)=>draftTime(b)-draftTime(a));
  const preview=drafts.find(job=>job.id===previewId&&job.video_sha);
  const listError=resource.error?draftError(resource.error):
    data&&!Array.isArray(data.drafts)?'API bản nháp trả dữ liệu không hợp lệ.':null;
  const active=drafts.find(job=>job.status==='RUNNING'&&job.worker_active);
  const featured=selectedId===null?visibleDrafts[0]:visibleDrafts.find(job=>job.id===selectedId);
  const reviewing=drafts.find(job=>job.id===storyboardId&&job.board);
  const canEdit=reviewing?.storyboard_version&&['STORYBOARD_REVIEW','FAILED','REVIEW','APPROVED','REJECTED'].includes(reviewing.status);
  const sceneCount=reviewing?.board.scenes.length;
  const minScenes=reviewing?.brief.mode==='motion'?
    (reviewing.brief.duration_mode?Math.max(2,Math.ceil(reviewing.brief.seconds*24/49)):motionShots[reviewing.brief.seconds]):2;
  const maxScenes=reviewing?.brief.mode==='motion'?
    (reviewing.brief.duration_mode?Math.min(16,reviewing.brief.seconds):motionMaxShots[reviewing.brief.seconds]):
    Math.min(6,Math.floor((reviewing?.brief.seconds??0)/2));
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
      if(result?.id) {
        setData({drafts:[{...result,worker_active:result.worker_active??result.status==='RUNNING'},
          ...drafts.filter(job=>job.id!==result.id)]});
      }
      done?.(result);
      await reload();
    } catch(failure) {
      setError(draftError(failure));
      if(failure.code==='draft_not_found'&&path!=='/start') {
        setMissing(ids=>[...ids,path.split('/')[1]]);
        setEditor(null);
        setStoryboardId(null);
        setSelectedId(null);
      }
      if(path==='/start'&&failure.status>=400&&failure.status<500)request.current=null;
      if(failure.code==='draft_not_found'||!failure.status||
          (path.includes('/storyboard-')&&[400,409].includes(failure.status)))await reload();
    } finally {
      busy.current=false;
      setPending(false);
      setStarting(false);
    }
  }

  function submit(values) {
    const motion=values.mode==='motion';
    const payload={idea:values.idea,mode:values.mode,duration_mode:values.durationMode,
      seconds:values.durationMode==='manual'?values.targetSeconds:null,scene_count:null,
      ratio:motion?'16:9':values.ratio};
    const brief=JSON.stringify(payload);
    if(request.current?.brief!==brief)request.current={brief,id:crypto.randomUUID().replaceAll('-','')};
    return run('/start',{...payload,id:request.current.id},result=>{
      if(!result?.id)return;
      request.current=null;
      form.setFieldsValue(briefDefaults);
      try {
        localStorage.removeItem(editorKey);
        setSaveFailed(false);
      } catch {
        setSaveFailed(true);
      }
      setFilter('work');
      setSelectedId(result.id);
      requestAnimationFrame(()=>filmsRef.current?.scrollIntoView({
        block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',
      }));
    });
  }

  function storyboard(job,action,fields={}){
    return run('/'+job.id+'/storyboard-'+action,{sha256:job.storyboard_sha,...fields});
  }

  return <>
    <Card className="env-panel" title="Tạo video mới"
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
      <div className="draft-form-options">
        <Form.Item className="draft-video-mode" name="mode" label="Kiểu video" rules={[{required:true}]}>
          <Select options={Object.entries(videoModes).map(([value,label])=>({value,label}))}/>
        </Form.Item>
        {!moving&&<Form.Item name="ratio" label="Tỷ lệ khung hình">
          <Select options={['9:16','16:9'].map(value=>({value,label:value}))}/>
        </Form.Item>}
        <Button className="draft-submit" type="primary" htmlType="submit"
          loading={pending} disabled={waiting>0||characterCount>limit}>Tạo storyboard</Button>
      </div>
      <details className="draft-resource-details">
        <summary>Thời lượng · {manual?(values.targetSeconds??'—')+' giây':'AI tự đề xuất'}</summary>
        <Space wrap align="start">
          <Form.Item name="durationMode" label="Cách chọn thời lượng" rules={[{required:true}]}>
            <Select style={{width:180}} options={[{value:'auto',label:'AI tự đề xuất'},{value:'manual',label:'Nhập thủ công'}]}/>
          </Form.Item>
          {manual&&<Form.Item name="targetSeconds" label="Thời lượng"
            rules={[{required:true,type:'integer',min:moving?4:6,max:30}]}>
            <InputNumber min={moving?4:6} max={30} precision={0} suffix="giây"/>
          </Form.Item>}
        </Space>
      </details>
    </Form>
    <p className="env-muted">AI đề xuất số cảnh. Studio tạo ảnh{moving?' và chuyển động':''} sau khi bạn duyệt storyboard.</p>
    </Card>
    <Card ref={filmsRef} className="env-panel studio-drafts-list" title="Video của bạn"
      extra={!listError&&<Button icon={<ReloadOutlined/>} onClick={()=>{reload();refreshCapacity();}}
        loading={resource.loading}>Làm mới</Button>}>
    <details className="draft-resource-details env-muted">
      <summary>Tài nguyên{queued>0&&' · '+queued+' trong hàng đợi'}{waiting>0&&' · '+waiting+' đang chờ'}</summary>
      <Space wrap>
        <span>RAM dùng / khả dụng: {usage(capacity?.ram_total,capacity?.ram_available,formatMemory)}</span>
        <span>VRAM dùng / khả dụng: {usage(capacity?.vram_total_mib,capacity?.vram_free_mib,formatVram)}</span>
      </Space>
    </details>
    {error&&!reviewing&&!editor&&<Alert showIcon type="error" message={error}/>}
    {listError?<Alert showIcon type="error" message="Không đọc được bản nháp"
      description={listError} action={<Button onClick={reload}>Thử lại bản nháp</Button>}/>:
      <ResourceStatus resource={{...resource,loading:resource.loading&&!data&&!starting,data,reload}}
        label="bản nháp"/>}
    {data&&!listError&&<Tabs className="draft-filters" activeKey={filter} onChange={key=>{setFilter(key);setSelectedId(null);}}
      items={[{key:'work',label:'Đang xử lý & chờ duyệt'},{key:'history',label:'Đã kết thúc'}]}/>}
    {!starting&&!resource.loading&&!listError&&data&&visibleDrafts.length===0&&
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={filter==='history'?'Chưa có bản nháp đã kết thúc':'Chưa có bản nháp'}/>}
    {!listError&&starting&&!featured&&<ProductionProgress starting labels={labels} warnings={warnings}/>}
    {visibleDrafts.length>0&&<Collapse className="draft-list" accordion destroyOnHidden
      activeKey={featured?.id??[]} onChange={key=>setSelectedId((Array.isArray(key)?key[0]:key)??'')}
      items={visibleDrafts.map(job=>({key:job.id,
        label:<DraftLabel job={job}/>,
        extra:<Space wrap>
          {job.board&&<Button size="small" type={job.status==='STORYBOARD_REVIEW'?'primary':'default'}
            onKeyDown={event=>event.stopPropagation()}
            onClick={event=>{event.stopPropagation();setSelectedId(job.id);setError(null);setStoryboardId(job.id);}}>Xem storyboard</Button>}
          {job.video_sha&&<Button size="small" onKeyDown={event=>event.stopPropagation()}
            onClick={event=>{event.stopPropagation();setSelectedId(job.id);setPreviewId(job.id);}}>Xem video</Button>}
        </Space>,
        children:<>
          <ProductionProgress job={job} labels={labels} warnings={warnings} busy={pending}
            onCancel={()=>run('/'+job.id+'/cancel',{})}
            onResume={!running?()=>run('/'+job.id+'/resume',{}):null}/>
          {!job.board&&<details><summary>Nội dung video</summary>
            <p className="draft-source-text">{job.brief.idea}</p>
          </details>}
          {!job.storyboard_version&&job.brief.mode!=='motion'&&job.board?.scenes.map((scene,index)=>
            <Button key={index} disabled={running||pending||job.status==='APPROVED'}
              onClick={()=>setEditor({id:job.id,index,scene})}>Sửa cảnh {index+1}</Button>)}
        </>,
      }))}/>}
    </Card>
    {reviewing&&<StoryboardReview key={reviewing.id} job={reviewing} busy={pending||running} error={editor?null:error}
      onClose={()=>setStoryboardId(null)}
      onApprove={()=>run('/'+reviewing.id+'/storyboard-approve',{sha256:reviewing.storyboard_sha},()=>setStoryboardId(null))}
      onEdit={canEdit?(index,scene)=>setEditor({job:reviewing,index,scene}):null}
      onRewrite={canEdit?(index,scene)=>setEditor({job:reviewing,index,scene,rewrite:true}):null}
      onMove={canEdit?(index,target)=>storyboard(reviewing,'move',{index,target}):null}
      onRemove={canEdit&&sceneCount>minScenes?index=>storyboard(reviewing,'remove',{index}):null}
      onAdd={canEdit&&sceneCount<maxScenes?()=>setEditor({job:reviewing,adding:true,index:sceneCount,scene:{}}):null}
      onDuration={canEdit&&reviewing.brief.duration_mode?seconds=>storyboard(reviewing,'duration',{seconds}):null}
      onPreview={(index,sha)=>setScenePreview({id:reviewing.id,index,sha})}/>}
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
      {error&&<Alert showIcon type="error" message={error}/>}
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
          hidden={editor.job.brief.mode!=='motion'} initialValue={editor.adding?videoModes.still:undefined}>
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
