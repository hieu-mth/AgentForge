import {useRef,useState} from 'react';
import {Alert,Button,Form,Image,Input,Modal,Space,Typography} from 'antd';
import {requestError} from '../api.js';
import {NumberField} from '../components/NumberField.jsx';

const localStatus={
  READY:'Workflow và model khả dụng',GPU_UNAVAILABLE:'Chưa phát hiện GPU CUDA',
  MODEL_UNAVAILABLE:'Thiếu model trong ComfyUI',WORKFLOW_NODE_UNAVAILABLE:'ComfyUI thiếu node của workflow',
  COMFYUI_UNAVAILABLE:'Không kết nối được ComfyUI',COMFYUI_TIMEOUT:'ComfyUI phản hồi quá chậm',
  COMFYUI_QUEUE_UNAVAILABLE:'Không kiểm tra được hàng đợi ComfyUI',
  COMFYUI_QUEUE_BUSY:'ComfyUI còn tác vụ trong hàng đợi',
  GPU_RESOURCE_FAILURE:'ComfyUI báo lỗi bộ nhớ. Kiểm tra tài nguyên trước khi thử lại.',
  COMFYUI_HTTP_ERROR:'ComfyUI trả lỗi HTTP',COMFYUI_INVALID_RESPONSE:'Phản hồi ComfyUI không hợp lệ',
  AUTH_REQUIRED:'ComfyUI yêu cầu xác thực',WORKFLOW_REJECTED:'ComfyUI từ chối workflow',
  EXECUTION_FAILED:'ComfyUI báo lỗi khi tạo ảnh',CANCELLED:'Tác vụ đã bị hủy tại ComfyUI',
  TIMED_OUT:'Hết thời gian theo dõi. Kiểm tra hàng đợi trước khi chạy lại.',
  OUTPUT_MISSING:'ComfyUI chưa trả ảnh đầu ra',OUTPUT_INVALID:'Không xác minh được ảnh đầu ra',
  SUBMIT_UNCERTAIN:'Chưa xác định kết quả gửi. Kiểm tra hàng đợi trước khi chạy lại.',
  LOCAL_INFERENCE_BUSY:'AgentForge đang chạy một tác vụ local khác',
};

export function MediaProbeDialog({profile,revision,mutate,onCancel}){
  const videoContract=profile.capability_contracts?.find(c=>c.capability==='film.motion'&&c.runtime_compatible);
  const video=Boolean(videoContract);
  const modes=videoContract?.input_modes??['text-to-video'];
  const imageInput=video&&modes.includes('image-to-video');
  const imageRequired=imageInput&&!modes.includes('text-to-video');
  const local=profile.provider==='comfyui';
  const config=!video&&(profile.comfy_image??profile.flux);
  const localImage=Boolean(local&&config);
  const {max_resolution,max_steps,timeout_seconds}=config||{};
  const initial=localImage?{width:Math.min(768,Math.floor(max_resolution/16)*16),height:Math.min(768,Math.floor(max_resolution/16)*16),steps:Math.min(4,max_steps)}:{};
  const submitted=useRef(null);
  const [id,setId]=useState(null);
  const [pending,setPending]=useState(false);
  const [result,setResult]=useState(null);
  const [error,setError]=useState(null);
  const lock=useRef(false);
  async function invoke(ack,ident,values){
    const {prompt,source,...options}=values??{};
    if(lock.current)return;
    lock.current=true;
    setPending(true);
    setError(null);
    try{
      const reply=await mutate('/api/model-hub/probe',{ack,profile_id:profile.id,
        expected_revision:revision,probe_id:ident,...(prompt===undefined?{}:{prompt}),...(source?.trim()?{source_image_job:source.trim()}: {}),...options},{inlineError:true});
      setResult(reply);
    }catch(e){const message=requestError(e);setError(localStatus[message]??message);}
    finally{lock.current=false;setPending(false);}
  }
  function run(values){
    if(id||lock.current)return;
    const ident=crypto.randomUUID().replaceAll('-','');
    setId(ident);
    submitted.current=Object.fromEntries(Object.entries(values).filter(([,value])=>value!=null));
    void invoke('RUN_MEDIA_MODEL_PROBE',ident,submitted.current);
  }
  return <Modal open title={'Chạy thử · '+profile.id} footer={null}
    onCancel={pending?undefined:onCancel} closable={!pending} keyboard={!pending} mask={{closable:false}}>
    <Alert type="warning" showIcon message={local?"Một lượt chạy local sử dụng GPU/RAM.":"Một lượt gọi Cloud có thể phát sinh phí."}
      description={video?'Tạo một video thử ngắn. Kiểm tra kết quả không gửi lại yêu cầu tạo video.':
        localImage?'Tạo một ảnh theo workflow đã đăng ký. Không tự gửi lại nếu chưa xác định kết quả.':'Tạo một ảnh thử 1K. Không tự gửi lại nếu chưa xác định kết quả.'}/>
    <Form layout="vertical" initialValues={initial} onFinish={run} disabled={pending||Boolean(id)}>
      <Form.Item name="prompt" label="Prompt" rules={[{required:true,whitespace:true},{min:local&&video?30:1}]}>
        <Input.TextArea rows={4} maxLength={local&&video?1100:2000}/>
      </Form.Item>
      {imageInput&&<Form.Item name="source" label="Mã ảnh nguồn đã xác minh (I2V)"
        extra={imageRequired?"Bắt buộc: lấy mã từ lượt tạo ảnh thành công.":"Để trống nếu muốn T2V."}
        rules={[{required:imageRequired,whitespace:true},{pattern:/^[a-f0-9]{32}$/,message:"Mã ảnh gồm 32 ký tự hex."}]}>
        <Input spellCheck={false}/>
      </Form.Item>}
      {localImage&&<>
      <Space wrap>
        {['width','height'].map((key,index)=><Form.Item key={key} name={key}
          label={index?'Cao (px)':'Rộng (px)'} rules={[{required:true,type:'integer',min:256,max:max_resolution},
            {validator:(_,v)=>v==null||v%16===0?Promise.resolve():Promise.reject(new Error('Dùng bội số của 16.'))}]}>
          <NumberField min={256} max={max_resolution} step={16}/>
        </Form.Item>)}
        <Form.Item name="steps" label="Số bước" rules={[{required:true,type:'integer',min:1,max:max_steps}]}>
          <NumberField min={1} max={max_steps}/>
        </Form.Item>
        <Form.Item name="seed" label="Seed" rules={[{type:'integer',min:0,max:Number.MAX_SAFE_INTEGER}]}>
          <NumberField min={0} max={Number.MAX_SAFE_INTEGER} placeholder="Ngẫu nhiên"/>
        </Form.Item>
      </Space>
      </>}
      <Button type="primary" htmlType="submit" loading={pending}>{video?'Tạo video':'Tạo ảnh'}</Button>
    </Form>
    <Space direction="vertical" style={{marginTop:16,width:'100%'}}>
      {id&&<Typography.Text copyable={{text:id}}>Mã kiểm tra: {id}</Typography.Text>}
      {pending&&<Alert type="info" showIcon message={localImage?'Đang tạo và xác minh ảnh · giới hạn theo dõi '+timeout_seconds+' giây':"Đang xử lý yêu cầu đã xác nhận…"}/>}
      {error&&<Alert type="error" showIcon message={error}/>}
      {error&&localImage&&id&&!result&&<Button disabled={pending} onClick={()=>invoke('RUN_MEDIA_MODEL_PROBE',id,submitted.current)}>Thử lại yêu cầu này</Button>}
      {result?.status==='NEEDS_RECONCILIATION'&&<Alert type="warning" showIcon message="Chưa xác định kết quả gửi. Kiểm tra nhà cung cấp, không tạo lại tự động."/>}
      {result?.error&&<Alert type={result.status==='REJECTED'?'error':'warning'} showIcon message={localStatus[result.error]??result.error}/>}
      {['REJECTED','FAILED'].includes(result?.status)&&<Button onClick={()=>{setId(null);setResult(null);setError(null);}}>Tạo lượt thử mới</Button>}
      {result?.status==='FAILED'&&<Alert type="error" showIcon message="Nhà cung cấp báo tác vụ thất bại."/>}
      {id&&result?.status!=='ASSET_READY'&&result?.status!=='FAILED'&&result?.status!=='REJECTED'&&<Button disabled={pending}
        onClick={()=>invoke('POLL_MEDIA_MODEL_PROBE',id)}>Kiểm tra kết quả</Button>}
      {result?.status==='ASSET_READY'&&(video?<video controls preload="metadata" src={result.preview_url} style={{width:'100%'}}/>:
        <Image width="100%" alt={localImage?(profile.comfy_image?"Ảnh chạy thử ComfyUI":"Ảnh chạy thử FLUX"):"Ảnh chạy thử Cloud"} src={result.preview_url}/>)}
      {localImage&&result?.status==='ASSET_READY'&&<>
        <Typography.Text>Thời gian: {result.duration_seconds} giây</Typography.Text>
        <Typography.Text className="env-break" copyable>{result.workspace_path}</Typography.Text>
        <Typography.Text type="secondary">{result.width}×{result.height} · {result.steps} bước · seed {result.seed}</Typography.Text>
      </>}
    </Space>
  </Modal>;
}
