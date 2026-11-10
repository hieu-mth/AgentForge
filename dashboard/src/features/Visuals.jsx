import {useCallback,useEffect,useState} from 'react';
import {App as AntApp,Alert,Button,Card,Image,Input,Select,Space,Tag,Typography} from 'antd';
import {api} from '../api.js';
const {Paragraph,Text}=Typography;

// One consent for bounded GPU batch and a separate explicit import action.
// Generation is server-side: users never need to author image prompts manually.
export function AutoVisuals({task=null,purpose='image',topic='',scenes=[],mutate,onReady}) {
  const {message,modal}=AntApp.useApp();
  const [health,setHealth]=useState(null);
  const [jobs,setJobs]=useState([]);
  const [checkpoint,setCheckpoint]=useState('');
  const [busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{
    try{
      const [h,j]=await Promise.all([api('/api/image/health'),api('/api/visuals/jobs')]);
      setHealth(h);
      const mine=(j.jobs||[]).filter(x=>task
        ?x.purpose==='video'&&x.source_sha===task.storyboard_source_sha
        :x.purpose===purpose&&x.source_sha===null);
      setJobs(mine);
      const choices=h.checkpoints||[];
      if(!choices.includes(checkpoint))setCheckpoint(choices[0]||'');
    }catch(e){message.error(e.message);}
  },[task?.storyboard_source_sha,purpose,checkpoint,message]);
  useEffect(()=>{refresh();},[refresh]);
  const count=scenes.length;
  const groups={};
  for(const job of jobs){
    if(!groups[job.package_id])groups[job.package_id]=[];
    groups[job.package_id].push(job);
  }
  const batches=Object.values(groups).sort((a,b)=>
    (b[0]?.created_at||'').localeCompare(a[0]?.created_at||''));
  const active=batches[0]||[];
  const ordered=[...active].sort((a,b)=>a.scene_index-b.scene_index);
  const complete=(count>0&&ordered.length===count&&ordered.every((j,i)=>
    j.status==='ASSET_READY'&&j.scene_index===i&&!!j.asset_sha));
  const generate=()=>modal.confirm({
    title:'Cho phép AI tự tạo hình ảnh?',
    content:<Space orientation="vertical">
      <Paragraph>ComfyUI local tạo {count} ảnh theo mô tả sản phẩm và từng cảnh, sử dụng checkpoint đã chọn. Mỗi ảnh là một lượt GPU. Không có tự retry hoặc chi phí cloud.</Paragraph>
      <Text>Model: {checkpoint}</Text>
      <Text type="secondary">Các hình ảnh được AI tạo là minh họa, không xác minh mẫu sản phẩm thương mại hay thương hiệu.</Text>
    </Space>,
    okText:'Tạo '+count+' ảnh AI',
    onOk:async()=>{
      setBusy(true);
      try{
        const body=task
          ?{ack:'GENERATE_STORYBOARD_VISUALS',task_id:task.task_id,
            source_sha:task.storyboard_source_sha,checkpoint}
          :{ack:'GENERATE_AI_VISUALS',purpose,topic,scenes,checkpoint};
        const result=await mutate(task?'/api/visuals/generate-for-task':'/api/visuals/generate',body);
        if(result)message.success('Đã gửi '+result.gpu_jobs_submitted+' lượt tạo ảnh đến ComfyUI');
        await refresh();
      }finally{setBusy(false);}
    },
  });
  const importAll=()=>modal.confirm({
    title:'Kiểm tra và nhận ảnh AI đã hoàn tất?',
    content:'Chỉ đọc kết quả ComfyUI và nhập PNG có kiểm tra định dạng/SHA. Không tạo GPU job mới. Nếu chưa xong, hãy thử kiểm tra lại.',
    okText:'Nhận ảnh',
    onOk:async()=>{
      setBusy(true);
      try{
        for(const job of ordered){
          if(job.status==='SUBMITTED'){
            const result=await mutate('/api/visuals/'+job.job_id+'/collect',
              {ack:'IMPORT_AI_VISUAL'});
            if(result?.status==='PROCESSING')message.info('Cảnh '+(job.scene_index+1)+' đang được tạo');
          }
        }
        await refresh();
      }finally{setBusy(false);}
    },
  });
  return <Card size="small" title={'AI Visual Generation · '+(task?'Video':'Ảnh '+purpose)}>
    <Space orientation="vertical" size={10} style={{width:'100%'}}>
      <Alert showIcon type={health?.status==='READY'?'info':'warning'}
        message={health?.status==='READY'?'AI tạo ảnh bằng ComfyUI local':'Chưa sẵn sàng tạo ảnh'}
        description={health?.status==='READY'
          ?'AI tự tạo prompt ảnh theo từng cảnh. Bạn không cần cung cấp ảnh.'
          :'Cần chạy ComfyUI tại 127.0.0.1:8188 và cài checkpoint ảnh. Không dùng template thay thế.'}/>
      <Select value={checkpoint||undefined} style={{width:'100%'}}
        placeholder="Chọn model ảnh local"
        onChange={setCheckpoint}
        options={(health?.checkpoints||[]).map(x=>({value:x,label:x}))}/>
      <Space wrap>
        <Button type="primary" disabled={busy||!checkpoint||!count||count>5}
          onClick={generate}>AI tự tạo {count} ảnh</Button>
        <Button disabled={busy||!ordered.length} onClick={importAll}>Nhận ảnh đã tạo</Button>
        <Button disabled={busy} onClick={refresh}>Làm mới trạng thái</Button>
      </Space>
      {!!ordered.length&&<Space wrap align="start">
        {ordered.map(j=><div key={j.job_id} style={{maxWidth:130}}>
          {j.status==='ASSET_READY'
            ?<Image width={120} src={'/api/visuals/'+j.job_id+'/preview'}
              alt={'Ảnh AI cảnh '+(j.scene_index+1)}/>
            :<div style={{height:95,background:'#30343b',borderRadius:8,
                          padding:10}}>Cảnh {j.scene_index+1}</div>}
          <Text style={{display:'block',fontSize:11}}>Cảnh {j.scene_index+1}</Text>
          <Tag>{j.status}</Tag>
        </div>)}
      </Space>}
      {complete&&<Alert showIcon type="success"
        message="Đủ ảnh AI cho các cảnh"
        description="Kiểm tra ảnh thực tế phía trên. Bạn có thể chọn dùng bộ ảnh này để tiếp tục dựng video."/>}
      {complete&&onReady&&<Button type="primary"
        onClick={()=>onReady(ordered.map(j=>j.job_id))}>Dùng bộ ảnh này cho video</Button>}
    </Space>
  </Card>;
}
