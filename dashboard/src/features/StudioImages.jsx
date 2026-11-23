import {useRef,useState} from 'react';
import {Alert,Button,Card,Form,Image,Input,Space,Tag,Typography} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {requestError} from '../api.js';

const {Text,Paragraph}=Typography;
const statuses={
  SUBMITTING:'Đang gửi',SUBMITTED:'Đang tạo ảnh',ASSET_READY:'Chờ duyệt',
  CANCELLED:'Đã hủy tại ComfyUI',TIMED_OUT:'Hết thời gian chờ',
  EXECUTION_FAILED:'ComfyUI báo lỗi',OUTPUT_MISSING:'Thiếu ảnh đầu ra',
  OUTPUT_INVALID:'Không xác minh được ảnh',SUBMIT_UNCERTAIN:'Chưa xác định được kết quả gửi',
};

export function StudioImages({mutate,scene,initialPrompt=''}) {
  const [form]=Form.useForm();
  const jobs=useResource('/api/visuals/jobs');
  const hub=useResource('/api/model-hub');
  const [pending,setPending]=useState(false);
  const [error,setError]=useState(null);
  const [previewed,setPreviewed]=useState({});
  const inFlight=useRef(false);
  const binding=hub.data?.routes?.find(route=>route.id==='image.generate')?.model_ref;
  const profile=hub.data?.profiles?.find(item=>item.id===binding&&item.enabled&&item.flux);
  const settings=profile?.flux;
  const inputsFor=kind=>Object.values(settings?.workflow??{}).find(node=>node.class_type===kind)?.inputs;
  const latent=inputsFor('EmptySD3LatentImage');
  const sampler=inputsFor('KSampler');
  const history=(jobs.data?.jobs??[]).filter(row=>row.workflow_sha256&&!row.probe&&(!scene||row.scene===scene));

  async function run(action) {
    if(inFlight.current)return;
    inFlight.current=true;
    setPending(true);
    setError(null);
    try {
      await action();
    } catch(failure) {
      setError(requestError(failure));
    } finally {
      await jobs.reload();
      setPending(false);
      inFlight.current=false;
    }
  }

  function generate(values) {
    return run(async()=>{
      const payload=Object.fromEntries(Object.entries(values).filter(([,item])=>item!=null));
      const result=await mutate('/api/visuals/flux',{
        ...payload,...(scene?{scene}:{}),ack:'GENERATE_AI_VISUALS',
      },{inlineError:true});
      if(result.status!=='ASSET_READY')setError(statuses[result.status]??result.status);
    });
  }

  return <Card className="env-panel" title={scene?'Ảnh cho cảnh '+scene:'Tạo ảnh bằng ComfyUI'}
    extra={<Button onClick={jobs.reload} loading={jobs.loading}>Làm mới ảnh</Button>}>
    <ResourceStatus resource={hub} label="hồ sơ tạo ảnh"/>
    {hub.data&&!settings&&<Alert type="info" showIcon
      message="Đăng ký workflow FLUX trong Model AI rồi gán hồ sơ vào năng lực Tạo ảnh trong AI điều phối."/>}
    {error&&<Alert type="error" showIcon message={error}/>}
    {settings&&<Form form={form} layout="vertical" initialValues={{prompt:initialPrompt}}
      onFinish={generate} disabled={pending}>
      <Form.Item name="prompt" label="Prompt" rules={[{required:true,whitespace:true}]}>
        <Input.TextArea rows={3} maxLength={2000} showCount/>
      </Form.Item>
      <Space wrap align="start">
        <Form.Item name="width" label="Rộng (px)"><NumberField min={256} max={settings.max_resolution}
          step={16} placeholder={String(latent?.width??'')}/></Form.Item>
        <Form.Item name="height" label="Cao (px)"><NumberField min={256} max={settings.max_resolution}
          step={16} placeholder={String(latent?.height??'')}/></Form.Item>
        <Form.Item name="steps" label="Số bước"><NumberField min={1} max={settings.max_steps}
          placeholder={String(sampler?.steps??'')}/></Form.Item>
        <Form.Item name="seed" label="Seed"><NumberField min={0} max={Number.MAX_SAFE_INTEGER}
          placeholder="Ngẫu nhiên"/></Form.Item>
      </Space>
      <div><Button htmlType="submit" type="primary" loading={pending}>Tạo ảnh local</Button></div>
    </Form>}
    <ResourceStatus resource={jobs} label="tác vụ tạo ảnh"/>
    <div className="studio-episode-grid" style={{marginTop:16}}>
      {history.map(row=><Card key={row.job_id} size="small"
        title={<Tag color={row.approved?'success':undefined}>{row.approved?'Đã duyệt':statuses[row.status]??row.status}</Tag>}>
        {row.status==='ASSET_READY'&&<Image src={'/api/visuals/'+row.job_id+'/preview'}
          alt={'Ảnh tạo từ prompt '+row.prompt} width="100%"
          onLoad={()=>setPreviewed(old=>({...old,[row.job_id]:row.asset_sha}))}/>}
        <Paragraph ellipsis={{rows:2,expandable:true}}>{row.prompt}</Paragraph>
        <p className="env-break"><Text type="secondary">
          {row.width}×{row.height} · {row.steps} bước · seed {row.seed}
          {row.duration_seconds!=null?' · '+row.duration_seconds+' giây':''}
        </Text></p>
        <Space wrap>
          {row.status==='ASSET_READY'&&!row.approved&&<Button size="small"
            disabled={pending||previewed[row.job_id]!==row.asset_sha}
            onClick={()=>run(()=>mutate('/api/visuals/approve',{
              job_id:row.job_id,sha256:row.asset_sha,
            },{inlineError:true}))}>Duyệt ảnh</Button>}
          {settings&&<Button size="small" disabled={pending} onClick={()=>{
            form.setFieldsValue({prompt:row.prompt,width:row.width,height:row.height,steps:row.steps,seed:null});
            form.scrollToField('prompt',{focus:true});
          }}>Chỉnh prompt / Tạo lại</Button>}
        </Space>
      </Card>)}
    </div>
  </Card>;
}
