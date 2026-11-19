import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Card,Collapse,Empty,Form,Image,Input,InputNumber,Modal,Select,Space,Tag} from 'antd';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {requestError} from '../api.js';
import {StudioPreview} from './StudioPreview.jsx';

const API='/api/film/drafts';
function draftError(failure) {
  if(failure.code==='draft_storage_unavailable')return failure.message;
  if(failure.code==='draft_not_found')return 'Bản nháp này không còn tồn tại. Bạn có thể tạo bản nháp mới.';
  if(failure.status===404)return 'Backend đang chạy chưa hỗ trợ bản nháp. Hãy khởi động lại AgentForge bằng phiên bản mới rồi thử lại.';
  return requestError(failure);
}
const labels={QUEUED:'Đã tiếp nhận',PLANNING:'Đang lập kế hoạch',STORYBOARD:'Đang viết storyboard',
  IMAGES:'Đang tạo ảnh từng cảnh',RENDER:'Đang dựng và kiểm tra MP4',REVIEW:'Chờ Owner duyệt',
  FAILED:'Cần xử lý',APPROVED:'Đã duyệt',REJECTED:'Đã từ chối'};

export function StudioDrafts({mutate,onCharacters}) {
  const {data,reload,...resource}=useResource(API);
  useScreenRefresh(reload);
  const busy=useRef(false);
  const request=useRef(null);
  const [pending,setPending]=useState(false);
  const [error,setError]=useState(null);
  const [editor,setEditor]=useState(null);
  const [missing,setMissing]=useState([]);
  const drafts=Array.isArray(data?.drafts)?data.drafts.filter(job=>!missing.includes(job.id)):[];
  const listError=resource.error?draftError(resource.error):
    data&&!Array.isArray(data.drafts)?'API bản nháp trả dữ liệu không hợp lệ.':null;
  const running=!listError&&drafts.some(job=>job.status==='RUNNING'&&job.worker_active);
  useEffect(()=>{
    if(!running||resource.loading)return;
    const timer=setTimeout(reload,2500);
    return ()=>clearTimeout(timer);
  },[reload,running,resource.loading]);

  async function run(path,body,done) {
    if(busy.current)return;
    busy.current=true;
    setPending(true);
    setError(null);
    try {
      await mutate(API+path,body,{inlineError:true});
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
    }
  }

  function submit(values) {
    const brief=JSON.stringify(values);
    if(request.current?.brief!==brief)request.current={brief,id:crypto.randomUUID().replaceAll('-','')};
    return run('/start',{...values,id:request.current.id},()=>{request.current=null;});
  }

  return <Card className="env-panel" title="Tạo video từ ý tưởng"
    extra={!listError&&<Button onClick={reload}>Tải lại bản nháp</Button>}>
    <Form layout="vertical" onFinish={submit} initialValues={{seconds:12,scene_count:3,ratio:'9:16'}}>
      <Form.Item label="Ý tưởng video" name="idea" rules={[{required:true,whitespace:true}]}>
        <Input.TextArea rows={3} maxLength={500}
          placeholder="Một chú mèo cam khám phá khu rừng phép thuật…"/>
      </Form.Item>
      <Space wrap>
        <Form.Item name="seconds" label="Thời lượng (giây)" rules={[{required:true,type:'integer',min:6,max:60}]}>
          <InputNumber min={6} max={60}/>
        </Form.Item>
        <Form.Item name="scene_count" label="Số cảnh" rules={[{required:true,type:'integer',min:2,max:6}]}>
          <InputNumber min={2} max={6}/>
        </Form.Item>
        <Form.Item name="ratio" label="Tỷ lệ khung hình">
          <Select options={['9:16','16:9'].map(value=>({value,label:value}))}/>
        </Form.Item>
        <Form.Item label=" ">
          <Button type="primary" htmlType="submit" loading={pending} disabled={running}>Tạo bản nháp</Button>
        </Form.Item>
      </Space>
    </Form>
    <p className="env-muted">Bản nháp dùng ảnh tĩnh với pan/zoom, không có nhạc. Tính nhất quán của nhân vật dựa trên prompt.</p>
    <Button type="link" onClick={onCharacters}>Thư viện nhân vật</Button>
    {error&&<Alert showIcon type="error" message={error}/>}
    {listError?<Alert showIcon type="error" message="Không đọc được bản nháp"
      description={listError} action={<Button onClick={reload}>Thử lại bản nháp</Button>}/>:
      <ResourceStatus resource={{...resource,data,reload}} label="bản nháp"/>}
    {!resource.loading&&!listError&&data&&drafts.length===0&&
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Chưa có bản nháp"/>}
    {drafts.length>0&&<Collapse items={drafts.map(job=>({key:job.id,
      label:<Space wrap><span>{job.board?.title??job.brief.idea}</span>
        <Tag>{job.status==='RUNNING'&&!job.worker_active?'Đã gián đoạn':
          labels[job.status==='RUNNING'?job.stage:job.status]??job.status}</Tag>
        {job.board&&<span>{job.board.scenes.filter(scene=>scene.asset).length}/{job.board.scenes.length} ảnh</span>}
      </Space>,
      children:<>
        {job.error&&<Alert showIcon type="error" message={job.error}/>}
        {['RUNNING','FAILED'].includes(job.status)&&!job.worker_active&&<Button size="small" disabled={pending||running}
          onClick={()=>run('/'+job.id+'/resume',{})}>Tiếp tục từ checkpoint</Button>}
        {job.plan&&<p>{job.plan}</p>}
        {job.board&&<ul className="studio-shot-list">{job.board.scenes.map((scene,index)=><li key={index}>
          <strong>Cảnh {index+1} · {scene.seconds} giây</strong>
          <p>{scene.description}</p>
          {scene.character_ids.map(id=><Tag key={id}>{job.cast[id]?.name}</Tag>)}
          <p className="env-muted">Âm thanh dự kiến: {scene.audio}</p>
          {scene.asset&&<Image width={180} alt={'Ảnh cảnh '+(index+1)}
            src={API+'/'+job.id+'/scene-'+index+'?v='+scene.asset}/>}
          <div><Button size="small" disabled={running||pending||job.status==='APPROVED'}
            onClick={()=>setEditor({id:job.id,index,scene})}>Sửa cảnh / tạo lại ảnh</Button></div>
        </li>)}</ul>}
        {job.video_sha&&<StudioPreview key={job.video_sha} url={API+'/'+job.id+'/preview?v='+job.video_sha}
          filename="draft.mp4" label="Xem bản nháp MP4"/>}
        {job.status==='REVIEW'&&<Space wrap style={{marginTop:12}}>
          <Button type="primary" disabled={pending}
            onClick={()=>run('/'+job.id+'/approve',{sha256:job.video_sha})}>Duyệt bản nháp</Button>
          <Button danger disabled={pending}
            onClick={()=>run('/'+job.id+'/reject',{sha256:job.video_sha})}>Từ chối</Button>
        </Space>}
      </>,
    }))}/>}
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
  </Card>;
}
