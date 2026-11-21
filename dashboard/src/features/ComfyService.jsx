import {useEffect,useState} from 'react';
import {Alert,Button,Card,Form,Input,Modal,Select,Space,Spin,Tag} from 'antd';
import {useResource} from '../use_resource.jsx';
import {requestError} from '../api.js';

const statusPath='/api/ops/comfyui';
const states={
  UNCONFIGURED:['Chưa cấu hình','default'],
  STOPPED:['Đã dừng','default'],
  STARTING:['Đang khởi động','processing'],
  STOPPING:['Đang dừng','processing'],
  RUNNING:['Đang chạy','success'],
  ERROR:['Lỗi','error'],
};
const gib=bytes=>Number.isFinite(bytes)?(bytes/2**30).toFixed(1)+' GB':'—';

export function ComfyService({mutate}){
  const {data,error,loading,reload,setData}=useResource(statusPath);
  const [dialog,setDialog]=useState(false);
  const [pending,setPending]=useState(null);
  const [failure,setFailure]=useState(null);
  const [form]=Form.useForm();
  const transitioning=['STARTING','STOPPING'].includes(data?.state);
  const managed=data?.managed;
  useEffect(()=>{
    if(loading||(!transitioning&&!pending&&!managed))return;
    const timer=setTimeout(reload,transitioning||pending?2000:10000);
    return ()=>clearTimeout(timer);
  },[transitioning,managed,pending,reload,loading]);

  async function submit(operation,body){
    setPending(operation);
    setFailure(null);
    try{
      const result=await mutate(statusPath+(operation==='config'?'/config':'/control'),body,{inlineError:true});
      setData({...result,can_manage:data?.can_manage});
      if(operation==='config')setDialog(false);
    }catch(err){
      setFailure(requestError(err));
      await reload();
    }finally{
      setPending(null);
    }
  }

  const badge=states[data?.state];
  const blocked=Boolean(pending||transitioning||error);
  const stopBlocked=blocked||data?.busy;
  return <Card className="env-panel" title="Dịch vụ ComfyUI" extra={
    <Button aria-label="Kiểm tra ComfyUI" onClick={reload} loading={loading&&!pending}>Kiểm tra</Button>
  }>
    <Space orientation="vertical" size="middle" style={{display:'flex'}}>
      {error&&<Alert type="error" showIcon message={requestError(error)}/>}
      {!data&&loading&&<span role="status"><Spin size="small"/> Đang kiểm tra ComfyUI…</span>}
      {badge&&<div role="status"><Tag color={badge[1]}>{badge[0]}</Tag>
        {data.managed?'AgentForge quản lý':data.state==='RUNNING'?'Chạy bên ngoài':''}
      </div>}
      {data?.endpoint&&<div className="env-break">
        {data.endpoint}{data.pid?' · PID '+data.pid:''}
      </div>}
      {!!data?.devices?.length&&data.devices.map((device,i)=><div key={i}>
        {device.name||device.type} · VRAM khả dụng {gib(device.vram_free)} / {gib(device.vram_total)}
      </div>)}
      {data?.busy&&<Alert type="info" showIcon
        message="Đang có tác vụ hoặc chưa xác minh được hàng đợi. Đợi kiểm tra lại trước khi dừng."/>}
      {data&&data.can_manage===false&&<Alert type="info" showIcon message="Phiên AgentForge hiện ở chế độ chỉ đọc công cụ local."/>}
      {data?.error&&<Alert type="error" showIcon message={data.error}/>}
      {failure&&!dialog&&<Alert type="error" showIcon message={failure}
        action={<Button size="small" onClick={reload}>Kiểm tra lại</Button>}/>}
      {data&&<Space wrap>
        <Button type="primary" loading={pending==='start'} disabled={blocked||!data.can_manage||!data.configured||data.managed||data.state==='RUNNING'}
          onClick={()=>submit('start',{action:'start'})}>{data.state==='ERROR'&&!data.managed?'Thử khởi động lại':'Khởi động'}</Button>
        <Button loading={pending==='stop'} disabled={stopBlocked||!data.can_manage||!data.managed}
          onClick={()=>submit('stop',{action:'stop'})}>Dừng</Button>
        <Button loading={pending==='restart'} disabled={stopBlocked||!data.can_manage||!data.managed}
          onClick={()=>submit('restart',{action:'restart'})}>Khởi động lại</Button>
        <Button disabled={blocked||data.managed} onClick={()=>{
          setFailure(null);setDialog(true);
        }}>Cấu hình launcher</Button>
      </Space>}
    </Space>
    <Modal title="Cấu hình ComfyUI Portable" open={dialog}
      onCancel={()=>{if(!pending){setDialog(false);setFailure(null);}}}
      onOk={()=>form.submit()} confirmLoading={pending==='config'} okText="Lưu" cancelText="Hủy">
      {dialog&&<LauncherSettings form={form} initialValues={{profile_id:data?.profile_id,install_root:data?.install_root}} submit={body=>submit('config',body)}/>}
      {dialog&&failure&&<Alert type="error" showIcon message={failure}/>}
    </Modal>
  </Card>;
}

function LauncherSettings({form,initialValues,submit}){
  const hub=useResource('/api/model-hub');
  const profiles=(hub.data?.profiles||[]).filter(profile=>profile.enabled&&profile.provider==='comfyui');
  return <Form form={form} layout="vertical" initialValues={initialValues} preserve={false} onFinish={submit}>
    {hub.error&&<Alert type="error" showIcon message={requestError(hub.error)}/>}
    <Form.Item name="profile_id" label="Hồ sơ ComfyUI trong Model Hub" rules={[{required:true}]}>
      <Select loading={hub.loading} options={profiles.map(p=>({value:p.id,label:p.id+' · '+p.base_url}))}/>
    </Form.Item>
    <Form.Item name="install_root" label="Thư mục ComfyUI Windows Portable"
      rules={[{required:true}]} extra="AgentForge xác minh Python Portable và khởi chạy với --cache-none.">
      <Input maxLength={500}/>
    </Form.Item>
  </Form>;
}
