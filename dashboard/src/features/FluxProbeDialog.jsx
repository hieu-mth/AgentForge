import {useRef,useState} from 'react';
import {Alert,Button,Form,Image,Input,Modal,Space,Typography} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {requestError} from '../api.js';

const fluxStatus={
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

export function FluxProbeDialog({profile,revision,mutate,onCancel}) {
  const pendingRef=useRef(false);
  const [pending,setPending]=useState(false);
  const [result,setResult]=useState(null);
  const [error,setError]=useState(null);
  const {max_resolution,max_steps,timeout_seconds}=profile.flux;
  const initial={width:Math.min(768,Math.floor(max_resolution/16)*16),
    height:Math.min(768,Math.floor(max_resolution/16)*16),steps:Math.min(4,max_steps)};

  async function run(values) {
    if(pendingRef.current)return;
    pendingRef.current=true;
    setPending(true);
    setResult(null);
    setError(null);
    try {
      const options=Object.fromEntries(Object.entries(values).filter(([,value])=>value!=null));
      const reply=await mutate('/api/model-hub/probe',{
        ...options,ack:'RUN_FLUX_MODEL_PROBE',profile_id:profile.id,expected_revision:revision,
      },{inlineError:true});
      setResult(reply);
      if(reply.status!=='ASSET_READY')setError(fluxStatus[reply.status]??reply.status);
    } catch(failure) {
      const message=requestError(failure);
      setError(fluxStatus[message]??message);
    } finally {
      pendingRef.current=false;
      setPending(false);
    }
  }

  return <Modal open title={'Chạy thử · '+profile.id} footer={null}
    onCancel={pending?undefined:onCancel} closable={!pending} keyboard={!pending} mask={{closable:false}}>
    <Form layout="vertical" initialValues={initial} onFinish={run} disabled={pending}>
      <Form.Item name="prompt" label="Prompt" rules={[{required:true,whitespace:true}]}>
        <Input.TextArea rows={3} maxLength={2000}/>
      </Form.Item>
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
      <Button type="primary" htmlType="submit" aria-label="Tạo ảnh" loading={pending}>Tạo ảnh</Button>
    </Form>
    <Space direction="vertical" style={{marginTop:16,width:'100%'}}>
      {pending&&<Alert type="info" showIcon message={'Đang tạo và xác minh ảnh · giới hạn theo dõi '+timeout_seconds+' giây'}/>}
      {error&&<Alert type="error" showIcon message={error}/>}
      {result&&<Typography.Text>Thời gian: {result.duration_seconds} giây</Typography.Text>}
      {result?.status==='ASSET_READY'&&<>
        <Image width="100%" alt="Ảnh chạy thử FLUX" src={result.preview_url}/>
        <Typography.Text className="env-break" copyable>{result.workspace_path}</Typography.Text>
        <Typography.Text type="secondary">{result.width}×{result.height} · {result.steps} bước · seed {result.seed}</Typography.Text>
      </>}
    </Space>
  </Modal>;
}
