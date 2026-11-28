import {useRef,useState} from 'react';
import {Alert,Button,Form,Image,Input,Modal,Space,Typography} from 'antd';
import {requestError} from '../api.js';

export function MediaProbeDialog({profile,revision,mutate,onCancel}){
  const videoContract=profile.capability_contracts?.find(c=>c.capability==='film.motion'&&c.runtime_compatible);
  const video=Boolean(videoContract);
  const modes=videoContract?.input_modes??['text-to-video'];
  const imageInput=video&&modes.includes('image-to-video');
  const imageRequired=imageInput&&!modes.includes('text-to-video');
  const local=profile.provider==='comfyui';
  const [id,setId]=useState(null);
  const [pending,setPending]=useState(false);
  const [result,setResult]=useState(null);
  const [error,setError]=useState(null);
  const lock=useRef(false);
  async function invoke(ack,ident,prompt,source){
    if(lock.current)return;
    lock.current=true;
    setPending(true);
    setError(null);
    try{
      const reply=await mutate('/api/model-hub/probe',{ack,profile_id:profile.id,
        expected_revision:revision,probe_id:ident,...(prompt===undefined?{}:{prompt}),...(source?.trim()?{source_image_job:source.trim()}: {})},{inlineError:true});
      setResult(reply);
    }catch(e){setError(requestError(e));}
    finally{lock.current=false;setPending(false);}
  }
  function run({prompt,source}){
    if(id||lock.current)return;
    const ident=crypto.randomUUID().replaceAll('-','');
    setId(ident);
    void invoke('RUN_MEDIA_MODEL_PROBE',ident,prompt,source);
  }
  return <Modal open title={'Chạy thử · '+profile.id} footer={null}
    onCancel={pending?undefined:onCancel} closable={!pending} keyboard={!pending} mask={{closable:false}}>
    <Alert type="warning" showIcon message={local?"Một lượt chạy local sử dụng GPU/RAM.":"Một lượt gọi Cloud có thể phát sinh phí."}
      description={video?'Tạo một video thử ngắn. Kiểm tra kết quả không gửi lại yêu cầu tạo video.':
        'Tạo một ảnh thử 1K. Không tự gửi lại nếu chưa xác định kết quả.'}/>
    <Form layout="vertical" onFinish={run} disabled={pending||Boolean(id)}>
      <Form.Item name="prompt" label="Prompt" rules={[{required:true,whitespace:true},{min:local?30:1}]}>
        <Input.TextArea rows={4} maxLength={local?1100:2000}/>
      </Form.Item>
      {imageInput&&<Form.Item name="source" label="Mã ảnh nguồn đã xác minh (I2V)"
        extra={imageRequired?"Bắt buộc: lấy mã từ lượt tạo ảnh thành công.":"Để trống nếu muốn T2V."}
        rules={[{required:imageRequired,whitespace:true},{pattern:/^[a-f0-9]{32}$/,message:"Mã ảnh gồm 32 ký tự hex."}]}>
        <Input spellCheck={false}/>
      </Form.Item>}
      <Button type="primary" htmlType="submit" loading={pending}>{video?'Tạo video':'Tạo ảnh'}</Button>
    </Form>
    <Space direction="vertical" style={{marginTop:16,width:'100%'}}>
      {id&&<Typography.Text copyable={{text:id}}>Mã kiểm tra: {id}</Typography.Text>}
      {pending&&<Alert type="info" showIcon message="Đang xử lý yêu cầu đã xác nhận…"/>}
      {error&&<Alert type="error" showIcon message={error}/>}
      {result?.status==='NEEDS_RECONCILIATION'&&<Alert type="warning" showIcon message="Chưa xác định kết quả gửi. Kiểm tra nhà cung cấp, không tạo lại tự động."/>}
      {result?.error&&<Alert type={result.status==='REJECTED'?'error':'warning'} showIcon message={result.error}/>}
      {result?.status==='REJECTED'&&<Button onClick={()=>{setId(null);setResult(null);setError(null);}}>Tạo lượt thử mới</Button>}
      {result?.status==='FAILED'&&<Alert type="error" showIcon message="Nhà cung cấp báo tác vụ thất bại."/>}
      {id&&result?.status!=='ASSET_READY'&&result?.status!=='FAILED'&&result?.status!=='REJECTED'&&<Button disabled={pending}
        onClick={()=>invoke('POLL_MEDIA_MODEL_PROBE',id)}>Kiểm tra kết quả</Button>}
      {result?.status==='ASSET_READY'&&(video?<video controls preload="metadata" src={result.preview_url} style={{width:'100%'}}/>:
        <Image width="100%" alt="Ảnh chạy thử Cloud" src={result.preview_url}/>)}
    </Space>
  </Modal>;
}
