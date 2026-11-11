import { useCallback, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Checkbox, Empty, Form, Image,
  Input, Select, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { api } from '../api.js';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import { AutoVisuals } from './Visuals.jsx';
import { badge, clip } from '../components/shared.jsx';
const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

export function Projects({mutate}) {
  const {message,modal} = AntApp.useApp();
  const artifacts=useResource('/api/artifacts');
  const health=useResource('/api/image/health');
  const jobs=useResource('/api/image/jobs');
  const state={artifacts:artifacts.data,health:health.data,jobs:jobs.data};
  const busy=artifacts.loading||health.loading||jobs.loading;
  const [checked,setChecked] = useState({});
  const [visualPurpose,setVisualPurpose]=useState('image');
  const [visualTopic,setVisualTopic]=useState('');
  const [visualSite,setVisualSite]=useState(null);
  const [form] = Form.useForm();

  const refresh=useCallback(()=>Promise.all([artifacts.reload(),health.reload(),jobs.reload()]),
    [artifacts.reload,health.reload,jobs.reload]);
  useScreenRefresh(refresh);
  const submit = values => modal.confirm({
    title:'Tạo một ảnh bằng ComfyUI local?',
    content:'Tác vụ này sử dụng GPU/điện trên máy. Không tự tải model, không đăng bài và không chi API cloud.',
    okText:'Cho phép tạo ảnh',cancelText:'Hủy',
    onOk:async()=>{
      const result=await mutate('/api/image/submit',{
        ack:'GENERATE_LOCAL_IMAGE',slug:values.slug,
        checkpoint:values.checkpoint,prompt:values.prompt.trim()});
      if(result){message.success('Đã gửi đúng một job'); await refresh();}
    }
  });
  const collect = job => modal.confirm({
    title:'Kiểm tra và nhập ảnh local?',content:'Không chạy lại ComfyUI. Chỉ nhận ảnh nếu job đã hoàn thành và SHA hợp lệ.',
    okText:'Nhận ảnh',onOk:async()=>{
      const out=await mutate('/api/image/'+job.job_id+'/collect',{ack:'IMPORT_AI_IMAGE'});
      if(out){message.info(out.status==='PROCESSING'?'ComfyUI vẫn đang xử lý':'Đã nhập ảnh');await refresh();}
    }
  });
  const attach = job => {
    if(!checked[job.job_id]){message.warning('Hãy xem ảnh và xác nhận đã kiểm tra trước.');return;}
    if(!job.asset_sha || !job.current_html_sha){message.error('Thiếu SHA ảnh hoặc website');return;}
    modal.confirm({
      title:'Gắn ảnh vào website local?',
      content:<div><Paragraph>Đã kiểm tra hình ảnh thật. HTML gốc sẽ được backup. Không deploy.</Paragraph>
        <Text code>Image: {job.asset_sha}</Text>
        <br/><Text code>HTML: {job.current_html_sha}</Text></div>,
      okText:'Xác nhận SHA',
      onOk:async()=>{
        const out=await mutate('/api/image/'+job.job_id+'/attach',{
          ack:'ATTACH_AI_IMAGE',image_sha:job.asset_sha,html_sha:job.current_html_sha});
        if(out){message.success('Đã gắn ảnh và tạo backup HTML');await refresh();}
      },
    });
  };
  const sites=(state.artifacts?.items||[]).filter(x=>x.kind==='website');
  const models=state.health?.checkpoints||[];
  return <Space orientation="vertical" size={18} style={{width:'100%'}}>
    <Alert showIcon type="info" message="Kho sản phẩm và lịch sử local — không tự xóa"
      description="Danh sách dưới đây chỉ kiểm kê những sản phẩm được lưu tại máy. Website local không phải website đã triển khai Internet."/>
    <Card title="Projects & Files" extra={<Button icon={<ReloadOutlined/>} onClick={refresh} loading={busy}>Làm mới</Button>}>
      <ResourceStatus resource={artifacts} label="kho thành phẩm"/>
      <Table rowKey={x=>x.kind+':'+x.id} size="middle" pagination={{pageSize:8}}
        dataSource={state.artifacts?.items||[]} loading={artifacts.loading}
        locale={{emptyText:artifacts.error?'Không tải được dữ liệu': 'Chưa có artifact local hợp lệ'}}
        columns={[
          {title:'Loại',dataIndex:'kind'},
          {title:'Mã sản phẩm',dataIndex:'id',render:value=><code>{value}</code>},
          {title:'Trạng thái',dataIndex:'status',render:badge},
          {title:'Dung lượng',dataIndex:'bytes',render:n=>(n/1024).toFixed(1)+' KB'},
          {title:'Public?',render:()=><Tag>Chưa xác minh</Tag>},
        ]}/>
      {state.artifacts&&<Text type="secondary">{state.artifacts.total_items||0} mục đã kiểm kê (tối đa 40 mục hiển thị). Không bao gồm nội dung file hay dữ liệu khách hàng.</Text>}
    </Card>
    <Card title="AI tự tạo hình ảnh — dùng chung cho Video / Ảnh / Website">
      <Alert showIcon type="info"
        message="Không cần tải ảnh lên hoặc viết prompt kỹ thuật"
        description="Mô tả sản phẩm hoặc nội dung muốn làm. AgentForge tự biên soạn prompt hình ảnh và gọi model ComfyUI local được chọn. Ảnh sau đó được lưu thành job độc lập, không phụ thuộc có website trước."/>
      <Space orientation="vertical" style={{width:'100%',marginTop:12}}>
        <Select value={visualPurpose} style={{width:'100%'}}
          onChange={value=>{setVisualPurpose(value);setVisualSite(null);}}
          options={[{value:'image',label:'Tạo ảnh độc lập'},
                    {value:'website',label:'AI tự làm ảnh cho website đã lưu local'}]}/>
        {visualPurpose==='website'?<>
          <Select placeholder="Chọn website đã lưu local"
            style={{width:'100%'}} value={visualSite?.slug}
            options={sites.map(x=>({value:x.id,label:x.id}))}
            onChange={async slug=>{
              setVisualSite(null);
              try{setVisualSite(await api('/api/visuals/website/'+encodeURIComponent(slug)));}
              catch(e){message.error(e.message);}
            }}/>
          {visualSite&&<AutoVisuals key={visualSite.slug+visualSite.source_sha}
            purpose="website" website={visualSite}
            topic={visualSite.visual_subject}
            scenes={[visualSite.visual_subject]} mutate={mutate}/>}
          {!visualSite&&<Text type="secondary">Hệ thống sẽ đọc nội dung website để tự quyết định prompt ảnh phù hợp. Không cần bạn nhập prompt.</Text>}
        </>:<>
          <Input.TextArea rows={3} maxLength={350} showCount
            placeholder="Ví dụ: Tạo bộ ảnh nệm cao cấp, phòng ngủ sáng sớm, ánh sáng tự nhiên"
            value={visualTopic} onChange={e=>setVisualTopic(e.target.value)}/>
          {visualTopic.trim().length>=3
            ?<AutoVisuals purpose="image" topic={visualTopic.trim()}
                scenes={[visualTopic.trim()]} mutate={mutate}/>
            :<Text type="secondary">Nói bạn muốn tạo ảnh về gì; hệ thống tự viết prompt cho model ảnh.</Text>}
        </>}
      </Space>
    </Card>
    <Card title="AI Image Studio · ComfyUI local" extra={badge(state.health?.status)}>
      <ResourceStatus resource={health} label="kết nối ảnh"/>
      <Alert type="warning" showIcon message="Ảnh do AI tạo không phải ảnh sản phẩm thật"
        description="Cần checkpoint ComfyUI cài riêng tại 127.0.0.1:8188. Sinh ảnh có thể dùng GPU. Phải xem ảnh trước khi gắn vào website."/>
      <Form form={form} layout="vertical" style={{marginTop:20}} onFinish={submit}>
        <Form.Item label="Website đã lưu local" name="slug" rules={[{required:true}]}>
          <Select options={sites.map(x=>({value:x.id,label:x.id}))} placeholder="Chọn website từ kho local"/>
        </Form.Item>
        <Form.Item label="Model ảnh ComfyUI" name="checkpoint" rules={[{required:true}]}>
          <Select options={models.map(x=>({value:x,label:x}))} placeholder="Chọn checkpoint đã cài"/>
        </Form.Item>
        <Form.Item label="Mô tả ảnh" name="prompt"
          rules={[{required:true,min:20,max:450}]}>
          <TextArea rows={3} maxLength={450} showCount
            placeholder="Photorealistic cozy bedroom with premium mattress, natural window light, no lettering or logo"/>
        </Form.Item>
        <Button type="primary" htmlType="submit"
          disabled={health.loading||!!health.error||state.health?.status!=='READY'||!sites.length}>Tạo một ảnh AI local</Button>
        <Button style={{marginLeft:10}} onClick={health.reload}>Kiểm tra ComfyUI</Button>
      </Form>
    </Card>
    <Card title="Lượt tạo ảnh và duyệt file">
      <ResourceStatus resource={jobs} label="lịch sử ảnh"/>
      <Space orientation="vertical" style={{width:'100%'}} size="middle">
        {(state.jobs?.jobs||[]).length===0?(!jobs.error&&!jobs.loading&&<Empty description="Chưa có job ảnh AI"/>):
          (state.jobs?.jobs||[]).map(job=><Card size="small" key={job.job_id}>
            <div className="image-job">
              <div><Text strong>{job.slug}</Text> · <Text code>{clip(job.job_id)}</Text>
                <p>{badge(job.status)} <Text type="secondary">{job.checkpoint}</Text></p>
                {job.status==='SUBMITTED'&&<Button onClick={()=>collect(job)}>Nhận ảnh khi xong</Button>}
                {job.status==='ASSET_READY'&&<>
                  <Image alt={'Ảnh minh họa AI cho '+job.slug} width={300}
                    src={'/api/image/'+job.job_id+'/preview'}/>
                  <div><Text type="secondary">SHA: </Text><Text code>{job.asset_sha}</Text></div>
                  <Checkbox checked={!!checked[job.job_id]}
                    onChange={e=>setChecked({...checked,[job.job_id]:e.target.checked})}>
                    Tôi đã xem ảnh và xác nhận dùng làm minh họa AI</Checkbox>
                  <div style={{marginTop:12}}><Button type="primary"
                    disabled={!checked[job.job_id]} onClick={()=>attach(job)}>
                    Gắn vào website local (backup HTML)</Button></div>
                </>}
                {['SUBMITTING','COLLECTING','ATTACHING'].includes(job.status)&&
                  <Alert type="warning" message="Trạng thái chưa chắc chắn — không tự retry. Kiểm tra log và file local trước."/>}
              </div>
            </div>
          </Card>)}
      </Space>
    </Card>
  </Space>;
}
