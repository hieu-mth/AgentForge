import {AppTooltip} from '../components/AppTooltip.jsx';
﻿import {useEffect,useRef,useState} from 'react';
import {Alert,App as AntApp,Button,Card,Collapse,Empty,Form,Input,Modal,Select,Space,Tabs,Tag} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {CaretRightFilled,CloseOutlined,DeleteOutlined,FileTextOutlined,PlayCircleOutlined,ReloadOutlined} from '@ant-design/icons';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {requestError} from '../api.js';
import {formatMemory,formatVram} from '../environment_format.js';
import {StudioPreview} from './StudioPreview.jsx';
import {StoryboardReview} from './StoryboardReview.jsx';
import {ProductionProgress} from './ProductionProgress.jsx';
import {ScriptContent} from './ScriptContent.jsx';
import {draftTitle} from './scriptPresentation.js';
import {MAX_STUDIO_SECONDS,storyboardShotLimits,productionMethodOptions,productionMethodLabels,cloudSecondsBounds} from './studioDuration.js';
import './studio-draft-progress.css';

const API='/api/film/drafts';
const editorKey='agentforge.studio.video-brief.v1';
const briefDefaults={idea:'',durationMode:'auto',targetSeconds:12,ratio:'9:16',mode:'motion',routeStrategy:'assigned',cloudSeconds:0};
const videoModes={motion:'Có chuyển động',still:'Ảnh tĩnh (lia và thu phóng)'};
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
  CLOUD_MOTION_RECONCILIATION_REQUIRED:'Có yêu cầu cloud chưa đối soát. Kiểm tra job nhà cung cấp trước khi tiếp tục.',
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
const statusColors={RUNNING:'processing',QUEUED:'blue',STORYBOARD_REVIEW:'orange',REVIEW:'orange',FAILED:'error',
  WAITING_RESOURCES:'warning',APPROVED:'success'};
const draftDate=new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short'});

const draftTimestamp=job=>Number.isFinite(Date.parse(job.updated_at))?job.updated_at:job.created_at;
const draftTime=job=>Date.parse(draftTimestamp(job))||0;

function DraftLabel({job}){
  const title=draftTitle(job);
  const stamp=draftTimestamp(job);
  const date=stamp&&new Date(stamp);
  const status=job.status==='RUNNING'&&!job.worker_active?'Đã gián đoạn':
    labels[job.status==='RUNNING'?job.stage:job.status]??job.status;
  return <div className="draft-row-label">
    <div className="draft-row-heading">
      <AppTooltip title={title}><strong>{title}</strong></AppTooltip>
      <Tag color={job.status==='RUNNING'&&!job.worker_active?'warning':statusColors[job.status]}>{status}</Tag>
    </div>
    <div className="draft-row-meta env-muted">
      {date&&Number.isFinite(date.getTime())&&<time dateTime={stamp}>
        {stamp!==job.created_at?'Cập nhật ':'Tạo '}{draftDate.format(date)}
      </time>}
      {job.brief.seconds&&<span>{job.brief.seconds} giây</span>}
      {job.brief.ratio&&<span>{job.brief.ratio}</span>}
      <span>{videoModes[job.brief.mode==='motion'?'motion':'still']}</span>
      {job.duration_plan?.content_scene_count&&<span>{job.duration_plan.content_scene_count} cảnh · {job.brief.scene_count} shot</span>}
      {job.board&&<span>{job.board.scenes.filter(scene=>job.brief.mode==='motion'?scene.motion_sha:scene.asset).length}/{job.board.scenes.length} {job.brief.mode==='motion'?'clip':'ảnh'}</span>}
    </div>
  </div>;
}

export function StudioDrafts({mutate,onCharacters}) {
  const {modal}=AntApp.useApp();
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
  const hub=useResource('/api/model-hub');
  useScreenRefresh(()=>Promise.all([reload(),hub.reload()]));
  const method=values.routeStrategy??'assigned';
  const methodOptions=productionMethodOptions(hub.data);
  const cloudBounds=cloudSecondsBounds(hub.data,method);
  const needsCloudBudget=['auto','hybrid','cloud'].includes(method);
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
  const [sourceId,setSourceId]=useState(null);
  const drafts=Array.isArray(data?.drafts)?data.drafts.filter(job=>!missing.includes(job.id)):[];
  const visibleDrafts=drafts.filter(job=>historyStates.has(job.status)===(filter==='history'))
    .sort((a,b)=>draftTime(b)-draftTime(a));
  const preview=drafts.find(job=>job.id===previewId&&job.video_sha);
  const listError=resource.error?draftError(resource.error):
    data&&!Array.isArray(data.drafts)?'API bản nháp trả dữ liệu không hợp lệ.':null;
  const active=drafts.find(job=>job.status==='RUNNING'&&job.worker_active);
  const featured=selectedId===null?visibleDrafts[0]:visibleDrafts.find(job=>job.id===selectedId);
  const reviewing=drafts.find(job=>job.id===storyboardId&&job.board);
  const sourceDraft=drafts.find(job=>job.id===sourceId);
  const canEdit=reviewing?.storyboard_version&&['STORYBOARD_REVIEW','FAILED','REVIEW'].includes(reviewing.status);
  const canChangeLayout=canEdit&&!reviewing.duration_plan?.content_scene_count;
  const sceneCount=reviewing?.board.scenes.length;
  const [minScenes,maxScenes]=storyboardShotLimits(reviewing);
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
        const remaining=drafts.filter(job=>job.id!==result.id);
        setData({drafts:result.deleted?remaining:[
          {...result,worker_active:result.worker_active??result.status==='RUNNING'},...remaining]});
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

  function draftAction(job) {
    const canDelete=['CANCELLED','FAILED','STORYBOARD_REVIEW'].includes(job.status)&&
      !job.video_sha&&!job.storyboard_history?.some(entry=>entry.video_sha);
    const canCancel=['QUEUED','RUNNING','WAITING_RESOURCES'].includes(job.status)||
      (job.status==='INTERRUPTED'&&job.stage!=='MOTION');
    if(!canCancel&&!canDelete)return null;
    const label=canDelete?'Xóa bản nháp':'Hủy tác vụ';
    return <AppTooltip title={label}><Button size="small" type="text" danger disabled={pending}
      className={canDelete?'draft-icon-action draft-danger-action draft-delete-action':'draft-icon-action draft-danger-action'}
      aria-label={label} icon={canDelete?<DeleteOutlined/>:<CloseOutlined/>}
      onKeyDown={event=>event.stopPropagation()} onClick={event=>{
        event.stopPropagation();
        modal.confirm({
          title:label+'?',
          content:canDelete?'Bản nháp và các tệp riêng của nó sẽ bị xóa vĩnh viễn.':
            'Yêu cầu dừng tác vụ. Khi đã hủy, bạn có thể xóa bản nháp.',
          okText:label,cancelText:'Giữ lại',okButtonProps:{danger:true},
          onOk:()=>run('/'+job.id+(canDelete?'/delete':'/cancel'),{},result=>{
            if(result?.deleted&&featured?.id===job.id)setSelectedId(null);
          }),
        });
      }}/></AppTooltip>;
  }

  function draftViews(job) {
    const views=[
      {key:'storyboard',available:job.board,label:'Xem storyboard',icon:<FileTextOutlined/>,open:()=>{
        setError(null);
        setStoryboardId(job.id);
      }},
      {key:'video',available:job.video_sha,label:'Xem video',icon:<PlayCircleOutlined/>,open:()=>setPreviewId(job.id)},
    ].filter(view=>view.available);
    return <>
      {views.map(view=><AppTooltip key={view.key} title={view.label}>
        <Button size="small" type="text" icon={view.icon} aria-label={view.label}
          className={view.key==='video'?'draft-icon-action draft-preview-action draft-video-action':
            'draft-icon-action draft-preview-action'}
          onKeyDown={event=>event.stopPropagation()} onClick={event=>{
            event.stopPropagation();
            setSelectedId(job.id);
            view.open();
          }}/>
      </AppTooltip>)}
      {draftAction(job)}
    </>;
  }

  function submit(values) {
    const motion=values.mode==='motion';
    const payload={idea:values.idea,mode:values.mode,duration_mode:values.durationMode,
      seconds:values.durationMode==='manual'?values.targetSeconds:null,scene_count:null,
      ratio:motion?'16:9':values.ratio};
    if(motion&&values.routeStrategy&&values.routeStrategy!=='assigned')Object.assign(payload,{route_strategy:values.routeStrategy,max_cloud_seconds:values.cloudSeconds??0});
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
      {moving&&<details className="draft-resource-details">
        <summary>Phương pháp sản xuất · {productionMethodLabels[method]??'Chưa chọn'}</summary>
        <Space wrap align="start">
          <Form.Item name="routeStrategy" label="Phương pháp" rules={[{validator:(_,value)=>
            methodOptions.some(option=>option.value===value&&!option.disabled)?Promise.resolve():
              Promise.reject(new Error('Phương pháp chưa có model video tương thích. Kiểm tra Model AI.'))}]}>
            <Select style={{width:280,maxWidth:'100%'}} loading={hub.loading} options={methodOptions}/>
          </Form.Item>
          {needsCloudBudget&&<Form.Item name="cloudSeconds" label="Tối đa giây video cloud" rules={[{required:true,type:'integer',...cloudBounds}]}>
            <NumberField min={cloudBounds.min} max={cloudBounds.max} precision={0} suffix="giây"/>
          </Form.Item>}
        </Space>
        {hub.error&&<Alert type="warning" showIcon message="Chưa đọc được phương pháp sản xuất" action={<Button onClick={hub.reload}>Thử lại</Button>}/>}
        <p className="env-muted">Có thể lập storyboard theo model video đã đăng ký dù chưa cấp quyền tạo media hoặc FFmpeg. Khi duyệt mới kiểm tra đầy đủ quyền, cấu hình và công cụ. Cloud có thể tính phí cả phần clip bị cắt.</p>
      </details>}
      <details className="draft-resource-details">
        <summary>Thời lượng · {manual?(values.targetSeconds??'—')+' giây':'AI tự đề xuất'}</summary>
        <Space wrap align="start">
          <Form.Item name="durationMode" label="Cách chọn thời lượng" rules={[{required:true}]}>
            <Select style={{width:180}} options={[{value:'auto',label:'AI tự đề xuất'},{value:'manual',label:'Nhập thủ công'}]}/>
          </Form.Item>
          {manual&&<Form.Item name="targetSeconds" label="Thời lượng"
            rules={[{required:true,type:'integer',min:moving?4:6,max:MAX_STUDIO_SECONDS}]}>
            <NumberField min={moving?4:6} max={MAX_STUDIO_SECONDS} precision={0} suffix="giây"/>
          </Form.Item>}
        </Space>
      </details>
    </Form>
    <p className="env-muted">AI đề xuất số cảnh. Studio tạo {moving?'video theo phương pháp đã chọn':'ảnh'} sau khi bạn duyệt storyboard.</p>
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
        extra:<div className="draft-row-actions">
          {['QUEUED','WAITING_RESOURCES','INTERRUPTED','NEEDS_RECONCILIATION','FAILED'].includes(job.status)&&
            <AppTooltip title="Tiếp tục từ checkpoint"><Button size="small" type="text" className="draft-icon-action"
              disabled={pending||running} icon={<CaretRightFilled/>}
              aria-label="Tiếp tục từ checkpoint"
              onKeyDown={event=>event.stopPropagation()}
              onClick={event=>{
                event.stopPropagation();
                setSelectedId(job.id);
                const shot=job.board?.scenes?.[job.failed_scene-1];
                const retryJob=job.stage==='MOTION'&&['FAILED','WAITING_RESOURCES'].includes(job.status)
                  &&!shot?.motion_sha&&shot?.motion_job;
                if(retryJob){
                  modal.confirm({
                    title:'Thử lại shot chuyển động bị lỗi?',
                    content:'Studio sẽ tạo lần chạy mới cho shot lỗi và tiếp tục từ checkpoint. Các ảnh và clip đã xác minh được dùng lại.',
                    okText:'Thử lại và tiếp tục',
                    cancelText:'Để sau',
                    onOk:()=>run('/'+job.id+'/resume',{retry_motion_job:retryJob}),
                  });
                }else{
                  run('/'+job.id+'/resume',{});
                }
              }}/></AppTooltip>}
          {draftViews(job)}
        </div>,
        children:<>
          <ProductionProgress job={job} labels={labels} warnings={warnings}/>
          {!job.board&&<Button type="default" aria-label="Xem nội dung video" icon={<FileTextOutlined/>}
            onClick={()=>setSourceId(job.id)}>
            Xem nội dung video
          </Button>}
          {!historyStates.has(job.status)&&!job.storyboard_version&&job.brief.mode!=='motion'&&job.board?.scenes.map((scene,index)=>
            <Button key={index} disabled={running||pending}
              onClick={()=>setEditor({id:job.id,index,scene})}>Sửa cảnh {index+1}</Button>)}
        </>,
      }))}/>}
    </Card>
    {reviewing&&<StoryboardReview key={reviewing.id} job={reviewing} modelRoutes={hub.data?.routes} busy={pending||running} error={editor?null:error}
      onClose={()=>setStoryboardId(null)}
      onApprove={()=>run('/'+reviewing.id+'/storyboard-approve',{sha256:reviewing.storyboard_sha},()=>setStoryboardId(null))}
      onEdit={canEdit?(index,scene)=>setEditor({job:reviewing,index,scene}):null}
      onRewrite={canEdit?(index,scene)=>setEditor({job:reviewing,index,scene,rewrite:true}):null}
      onRegenerate={canEdit&&reviewing.status==='REVIEW'&&reviewing.video_sha?(index,scope)=>modal.confirm({
        title:'Tạo lại cảnh '+(index+1)+'?',
        content:scope==='motion'?'Giữ ảnh; làm lại chuyển động cảnh này và các cảnh tiếp nối phụ thuộc nếu có. Cần duyệt storyboard mới trước khi chạy.':
          'Tạo lại ảnh, chuyển động và các cảnh tiếp nối phụ thuộc nếu có. Giữ cảnh độc lập và phiên bản cũ. Cần duyệt storyboard mới trước khi chạy.',
        okText:'Tạo phiên bản mới',cancelText:'Để sau',
        onOk:()=>storyboard(reviewing,'regenerate',{index,scope}),
      }):null}
      onContinuity={canEdit&&reviewing.brief.mode==='motion'?()=>modal.confirm({
        title:'AI lập lại liên tục chuyển động?',content:'AI sẽ chọn kiểu nối từng cảnh. Các cảnh thay đổi và cảnh phụ thuộc cần tạo lại; giữ phiên bản cũ. Model cloud có thể tính phí theo ngân sách production.',
        okText:'Lập kế hoạch',cancelText:'Hủy',onOk:()=>storyboard(reviewing,'continuity'),
      }):null}
      onAudioDirect={canEdit?(engine,voice_name,voices,generate_audio)=>modal.confirm({
        title:'AI lập kế hoạch âm thanh?',content:'Model storyboard lập các cue. Nếu chọn speech cloud, khi sản xuất lời thoại sẽ gửi đến endpoint đã gán và tính vào ngân sách production. Nhạc/hiệu ứng ưu tiên WAV local; nếu bật sinh cloud, prompt âm thanh sẽ được gửi đến model đã gán và có thể tính phí.',
        okText:'Lập kế hoạch',cancelText:'Hủy',onOk:()=>storyboard(reviewing,'audio-direct',{engine,voice_name,voices,generate_audio}),
      }):null}
      onAudio={canEdit?(engine,voice_name)=>storyboard(reviewing,'audio',{engine,voice_name}):null}
      onMove={canChangeLayout?(index,target)=>storyboard(reviewing,'move',{index,target}):null}
      onRemove={canChangeLayout&&sceneCount>minScenes?index=>storyboard(reviewing,'remove',{index}):null}
      onAdd={canChangeLayout&&sceneCount<maxScenes?()=>setEditor({job:reviewing,adding:true,index:sceneCount,scene:{}}):null}
      onDuration={canChangeLayout&&reviewing.brief.duration_mode?seconds=>storyboard(reviewing,'duration',{seconds}):null}
      onVisualReviewBatch={reviewing.status==='REVIEW'&&reviewing.video_sha?()=>modal.confirm({
        title:'Đánh giá các cảnh chưa kiểm tra?',content:'Tối đa 8 lượt AI. Nếu dùng cloud, frame mẫu sẽ được gửi đến provider đã chọn và tính vào ngân sách.',
        okText:'Đánh giá',cancelText:'Hủy',onOk:()=>run('/'+reviewing.id+'/visual-review-batch',{sha256:reviewing.storyboard_sha,video_sha:reviewing.video_sha,max_reviews:8,allow_cloud:true}),
      }):null}
      onQualityRepair={reviewing.status==='REVIEW'&&reviewing.video_sha?()=>modal.confirm({
        title:'AI đề xuất sửa các cảnh lỗi?',content:'Tối đa 2 cảnh mỗi production. AI sửa prompt, giữ kịch bản và tạo phiên bản mới. Model cloud có thể tính phí. Không tự render trước duyệt.',
        okText:'Đề xuất sửa',cancelText:'Hủy',onOk:()=>storyboard(reviewing,'quality-repair',{video_sha:reviewing.video_sha,max_repairs:2,allow_cloud:true}),
      }):null}
      onVisualReview={reviewing.status==='REVIEW'&&reviewing.video_sha?index=>modal.confirm({
        title:'AI đánh giá cảnh '+(index+1)+'?',
        content:'AgentForge sẽ lấy frame mẫu từ video đã xác minh và gọi model Kiểm tra chất lượng hình ảnh đã phân công. Nếu dùng cloud, ảnh và mô tả cảnh sẽ được gửi đến endpoint đã cấu hình và có thể tính phí. Kết quả chỉ là gợi ý.',
        okText:'Đánh giá bằng AI',cancelText:'Hủy',
        onOk:()=>run('/'+reviewing.id+'/visual-review',{index,sha256:reviewing.storyboard_sha,
          video_sha:reviewing.video_sha,allow_cloud:true}),
      }):null}
      onPreview={(index,sha)=>setScenePreview({id:reviewing.id,index,sha})}/>}
    {sourceDraft&&<Modal open centered width={760} rootClassName="script-reader" title="Nội dung video"
      onCancel={()=>setSourceId(null)} footer={<Button onClick={()=>setSourceId(null)}>Đóng</Button>}>
      <ScriptContent text={sourceDraft.brief.idea}/>
    </Modal>}
    {scenePreview&&<Modal open title={'Chuyển động cảnh '+(scenePreview.index+1)} footer={null}
      onCancel={()=>setScenePreview(null)}>
      <StudioPreview key={scenePreview.sha} initiallyOpen label="Xem clip chuyển động" filename="motion.mp4"
        url={API+'/'+scenePreview.id+'/motion-'+scenePreview.index+'?v='+scenePreview.sha}/>
    </Modal>}
    {preview&&<Modal open title={draftTitle(preview)} footer={null}
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
      <Form layout="vertical" initialValues={{...editor.scene,description:editor.scene.shot_description??editor.scene.description}} onFinish={values=>editor.job?
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
