import { useCallback, useEffect, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Checkbox, Descriptions,
  Form, Input, InputNumber, Select, Space, Switch, Table, Tag, Typography } from 'antd';
import { api } from '../api.js';
import { badge, clip } from '../components/shared.jsx';
const { Paragraph, Text } = Typography;
const { TextArea } = Input;

function confirmOwner(modal,title,content,onOk) {
  modal.confirm({title,content,okText:'Xác nhận',cancelText:'Hủy',onOk});
}

export function Schedules({data,mutate,onReload}) {
  const {modal,message}=AntApp.useApp();
  const [form]=Form.useForm();
  const rows=data?.schedules||[];
  const templates=Object.keys(data?.templates||{});
  const changeStatus=(record)=>{
    const next=record.status==='ACTIVE'?'PAUSED':'ACTIVE';
    confirmOwner(modal,next==='PAUSED'?'Tạm dừng lịch?':'Bật lại lịch?',
      'Chỉ thay đổi một lịch được chọn, không tự gọi model hoặc đăng bài.',
      async()=>{
        const out=await mutate('/api/schedules/'+record.schedule_id+'/status',
          {ack:next,status:next});
        if(out){message.success('Đã cập nhật lịch');onReload();}
      });
  };
  const create=values=>{
    let inputs;
    try {inputs=JSON.parse(values.inputs);} catch {message.error('Inputs phải là JSON hợp lệ');return;}
    if(!inputs||Array.isArray(inputs)||typeof inputs!=='object'){message.error('Inputs phải là JSON object');return;}
    const date=new Date(values.next_due);
    if(Number.isNaN(date.valueOf())){message.error('Thời điểm không hợp lệ');return;}
    confirmOwner(modal,'Tạo lịch lặp?',
      'Chỉ workflow hoàn toàn read-only, không dùng model, mới được backend chấp nhận. Lịch không tự chạy background.',
      async()=>{
        const out=await mutate('/api/schedules/create',{
          ack:'SCHEDULE',title:values.title,template:values.template,
          inputs,next_due:date.toISOString(),
          frequency_minutes:values.frequency_minutes});
        if(out){message.success('Đã tạo lịch');form.resetFields();onReload();}
      });
  };
  return <Space direction="vertical" style={{width:'100%'}} size={18}>
    <Alert type="info" showIcon message="Lịch local có kiểm soát"
      description="Chỉ workflow read-only, không có quyền model/process. Bạn phải chủ động bấm Tick hoặc chạy daemon đã được owner cấu hình. Tạo lịch không có nghĩa là đã bật background."/>
    <Card title="Các lịch đã lập" extra={<Button onClick={()=>confirmOwner(modal,
      'Chạy một tick local?','Kiểm tra tối đa 3 lịch đến hạn và ghi nhận trạng thái; không tự cấp thêm quyền.',
      async()=>{const out=await mutate('/api/schedules/tick',{ack:'TICK'});if(out){message.success('Đã xử lý tick');onReload();}})}>
      Chạy tick có xác nhận</Button>}>
      <Table rowKey="schedule_id" dataSource={rows} pagination={{pageSize:10}}
        columns={[
          {title:'Tên lịch',dataIndex:'title'},
          {title:'Workflow',dataIndex:'template'},
          {title:'Lần tới (UTC)',dataIndex:'next_due_utc',render:x=><Text>{x}</Text>},
          {title:'Chu kỳ (phút)',dataIndex:'frequency_minutes'},
          {title:'Trạng thái',dataIndex:'status',render:badge},
          {title:'Thao tác',render:(_,record)=><Button
            onClick={()=>changeStatus(record)}>{record.status==='ACTIVE'?'Tạm dừng':'Bật lại'}</Button>},
        ]}/>
    </Card>
    <Card title="Lập lịch mới · Nâng cao">
      <Form form={form} layout="vertical" onFinish={create}
        initialValues={{frequency_minutes:1440,inputs:'{}'}}>
        <Form.Item name="title" label="Tên công việc" rules={[{required:true,min:3,max:160}]}>
          <Input placeholder="Đánh giá tình trạng dữ liệu mỗi ngày"/>
        </Form.Item>
        <Form.Item name="template" label="Workflow có sẵn" rules={[{required:true}]}>
          <Select options={templates.map(x=>({value:x,label:x}))}/>
        </Form.Item>
        <Form.Item name="inputs" label="Inputs JSON (chỉ cấu hình dữ liệu đã xác thực)" rules={[{required:true}]}>
          <TextArea rows={3} spellCheck={false}/>
        </Form.Item>
        <Form.Item name="next_due" label="Lần chạy đầu (giờ địa phương)" rules={[{required:true}]}>
          <Input type="datetime-local"/>
        </Form.Item>
        <Form.Item name="frequency_minutes" label="Chu kỳ 60–10080 phút"
          rules={[{required:true,type:'number',min:60,max:10080}]}>
          <InputNumber min={60} max={10080} style={{width:'100%'}}/>
        </Form.Item>
        <Button type="primary" htmlType="submit">Tạo lịch read-only</Button>
      </Form>
    </Card>
  </Space>;
}

export function OperationsControl({data,mutate,onReload}) {
  const {modal,message}=AntApp.useApp();
  const mode=data?.operations?.mode||'UNKNOWN';
  const change=next=>confirmOwner(modal,next==='PAUSED'?'Dừng các thao tác mới?':'Cho phép vận hành trở lại?',
    'Quyết định ghi vào state local và được các skill gates kiểm tra. Không tự chạy bất kỳ task nào.',
    async()=>{
      const out=await mutate('/api/ops/control',{
        ack:next==='PAUSED'?'PAUSE_OPERATIONS':'RESUME_OPERATIONS',mode:next});
      if(out){message.success('Operations: '+next);onReload();}
    });
  return <Space size={18} direction="vertical" style={{width:'100%'}}>
    <Alert type="info" showIcon message="Đây là công tắc vận hành local"
      description="Pause không xóa task, sản phẩm hoặc audit. Resume không tự cấp quyền publish, browser, model hoặc chi tiền."/>
    <Card title="Operations">
      <Descriptions bordered column={1} items={[
        {key:'1',label:'Trạng thái',children:badge(mode)},
        {key:'2',label:'Nguồn',children:data?.operations?.reason||'UNKNOWN'},
        {key:'3',label:'Daemon',children:badge(data?.daemon?.status||'NOT_RUNNING')},
        {key:'4',label:'Heartbeat mới?',children:data?.daemon?.fresh?'Có':'Không xác minh'},
      ]}/>
      <Space style={{marginTop:18}}>
        <Button danger disabled={mode==='PAUSED'} onClick={()=>change('PAUSED')}>Pause Operations</Button>
        <Button type="primary" disabled={mode==='ACTIVE'} onClick={()=>change('ACTIVE')}>Resume Operations</Button>
      </Space>
    </Card>
  </Space>;
}

export function Intelligence({data}) {
  const items=data?.datasets||[];
  return <Space direction="vertical" style={{width:'100%'}}>
    <Alert type="info" showIcon message="Dữ liệu đã lưu trên máy"
      description="Synthetic và real được đánh dấu riêng. Dữ liệu thống kê không chứng minh có khách hàng hoặc lợi nhuận thật."/>
    <Card title="Datasets hiện có">
      <Table rowKey="dataset" dataSource={items} pagination={{pageSize:10}}
        columns={[
          {title:'Dataset',dataIndex:'dataset',render:value=><Text code>{value}</Text>},
          {title:'Nguồn',dataIndex:'synthetic',render:v=>v?<Tag color="gold">Synthetic</Tag>:<Tag color="green">Owner imported</Tag>},
          {title:'Dòng hiệu suất',dataIndex:'performance_rows'},
          {title:'Dòng sổ cái',dataIndex:'ledger_rows'},
        ]}/>
    </Card>
  </Space>;
}

export function Growth({data,mutate,onReload}) {
  const {modal,message}=AntApp.useApp();
  const [form]=Form.useForm();
  const create=v=>confirmOwner(modal,'Tạo campaign local?',
    'Chỉ tạo bản ghi kế hoạch/đối soát. Không tự chi ngân sách, đăng bài hay tiếp cận khách.',
    async()=>{
      const out=await mutate('/api/campaigns/create',{ack:'CREATE_CAMPAIGN',data:{
        campaign:v.campaign,title:v.title,analytics_dataset:v.analytics_dataset||'',
        budget_vnd:v.budget_vnd||0,synthetic:!!v.synthetic
      }});
      if(out){message.success('Đã tạo campaign');form.resetFields();onReload();}
    });
  return <Space direction="vertical" size={18} style={{width:'100%'}}>
    <Alert type="warning" showIcon message="Budget ở đây chỉ là số liệu kế hoạch"
      description="Không phải quyền chi tiền, hóa đơn provider hay lợi nhuận xác minh."/>
    <Card title="Growth & Revenue">
      <Table rowKey="campaign" dataSource={data?.growth||[]} pagination={{pageSize:8}}
        columns={[
          {title:'Campaign',dataIndex:'campaign',render:x=><Text code>{x}</Text>},
          {title:'Tên',dataIndex:'title'},
          {title:'Nguồn',dataIndex:'synthetic',render:v=>v?<Tag>Demo</Tag>:<Tag color="green">Owner recorded</Tag>},
          {title:'Leads',dataIndex:'lead_total'},
          {title:'Bài đăng ghi nhận',dataIndex:'owner_reported_posts'},
          {title:'Lợi nhuận xác minh',render:()=> 'Chưa xác minh'},
        ]}/>
    </Card>
    <Card title="Tạo campaign trong sổ local">
      <Form form={form} layout="vertical" onFinish={create}
        initialValues={{budget_vnd:0,synthetic:true}}>
        <Form.Item name="campaign" label="Campaign slug" rules={[{required:true}]}>
          <Input placeholder="nem-gia-dinh-2026"/>
        </Form.Item>
        <Form.Item name="title" label="Tên chiến dịch" rules={[{required:true,max:120}]}>
          <Input placeholder="Giới thiệu nệm ngủ gia đình"/>
        </Form.Item>
        <Form.Item name="analytics_dataset" label="Dataset liên kết (nếu có)">
          <Select allowClear options={(data?.datasets||[]).map(x=>({value:x.dataset,label:x.dataset}))}/>
        </Form.Item>
        <Form.Item name="budget_vnd" label="Ngân sách kế hoạch (VND, chưa chi)"
          rules={[{required:true,type:'number',min:0}]}>
          <InputNumber min={0} max={10**13} style={{width:'100%'}}/>
        </Form.Item>
        <Form.Item name="synthetic" label="Dữ liệu demo/synthetic" valuePropName="checked">
          <Switch/>
        </Form.Item>
        <Button type="primary" htmlType="submit">Tạo campaign local</Button>
      </Form>
    </Card>
  </Space>;
}

export function OwnerSettings({data,mutate,onReload}) {
  const {modal,message}=AntApp.useApp();
  const p=data?.workspace_policy||{},ap=data?.autopilot_policy||{};
  const [form]=Form.useForm(),[auto]=Form.useForm();
  useEffect(()=>{
    form.setFieldsValue({max_estimated_model_calls:p.max_estimated_model_calls??1,
      website_enabled:p.website_enabled!==false,
      storyboard_enabled:p.storyboard_enabled!==false});
    auto.setFieldsValue({enabled:ap.enabled===true,daily_cap:ap.daily_cap??0});
  },[data,form,auto]);
  const save=values=>confirmOwner(modal,'Thay đổi policy prompt?',
    'Chỉ giới hạn các Goal mới tạo từ prompt. Không thay quyền S1 hoặc giới hạn hóa đơn model thực tế.',
    async()=>{
      const out=await mutate('/api/workspace/policy',{
        ack:'UPDATE_WORKSPACE_POLICY',...values});
      if(out){message.success('Đã lưu policy');onReload();}
    });
  const saveAuto=values=>confirmOwner(modal,'Cập nhật ủy quyền Autopilot?',
    'Đây là hạn mức lượt model ước tính theo ngày UTC, không phải ngân sách VND được provider xác minh.',
    async()=>{
      const out=await mutate('/api/autopilot/configure',{
        ack:'SET_DAILY_MODEL_POLICY',enabled:!!values.enabled,daily_cap:values.daily_cap});
      if(out){message.success('Đã lưu policy Autopilot');onReload();}
    });
  return <div className="two-cols">
    <Card title="Prompt Workspace · Role/Calls">
      <Form form={form} layout="vertical" onFinish={save}>
        <Form.Item name="max_estimated_model_calls" label="Ước tính lượt model tối đa / Goal (0–3)"
          rules={[{required:true,type:'number',min:0,max:3}]}>
          <InputNumber min={0} max={3} style={{width:'100%'}}/>
        </Form.Item>
        <Form.Item name="website_enabled" label="Nhận yêu cầu Website" valuePropName="checked">
          <Switch/>
        </Form.Item>
        <Form.Item name="storyboard_enabled" label="Nhận yêu cầu Storyboard" valuePropName="checked">
          <Switch/>
        </Form.Item>
        <Button type="primary" htmlType="submit">Lưu prompt policy</Button>
      </Form>
    </Card>
    <Card title="Autopilot · Standing Delegation">
      <Alert type="warning" showIcon message="Quota không đồng nghĩa chi phí provider."/>
      <Form form={auto} layout="vertical" onFinish={saveAuto} style={{marginTop:18}}>
        <Form.Item name="enabled" label="Cho phép delegation" valuePropName="checked">
          <Switch/>
        </Form.Item>
        <Form.Item name="daily_cap" label="Lượt model dự kiến mỗi ngày"
          rules={[{required:true,type:'number',min:0,max:100}]}>
          <InputNumber min={0} max={100} style={{width:'100%'}}/>
        </Form.Item>
        <Button htmlType="submit">Cập nhật Autopilot</Button>
      </Form>
    </Card>
  </div>;
}

export function OwnerMemory({mutate}) {
  const {message,modal}=AntApp.useApp();
  const [rows,setRows]=useState(null);
  const [form]=Form.useForm();
  const refresh=useCallback(()=>api('/api/memory').then(setRows).catch(err=>message.error(err.message)),[message]);
  useEffect(()=>{refresh();},[refresh]);
  const save=v=>confirmOwner(modal,'Ghi ghi chú owner?',
    'Ghi chú chỉ lưu local, không tự trở thành fact xác minh hoặc prompt hệ thống.',
    async()=>{
      const out=await mutate('/api/memory/set',{ack:'SAVE_NOTE',
        key:v.key,note:v.note,evidence_ref:v.evidence_ref});
      if(out){message.success('Đã lưu phiên bản ghi chú');form.resetFields();refresh();}
    });
  return <Space direction="vertical" size={18} style={{width:'100%'}}>
    <Card title="Owner Memory · ghi chú có nguồn">
      <Table rowKey="key" dataSource={rows||[]} pagination={{pageSize:8}}
        columns={[
          {title:'Key',dataIndex:'key',render:v=><Text code>{v}</Text>},
          {title:'Ghi chú',dataIndex:'note'},
          {title:'Evidence ref',dataIndex:'evidence_ref'},
          {title:'Revision',dataIndex:'revision'},
        ]}/>
    </Card>
    <Card title="Thêm/cập nhật ghi chú">
      <Form form={form} layout="vertical" onFinish={save}>
        <Form.Item name="key" label="Key" rules={[{required:true}]}>
          <Input placeholder="brand_voice"/>
        </Form.Item>
        <Form.Item name="note" label="Ghi chú" rules={[{required:true,max:600}]}>
          <TextArea rows={3} maxLength={600} showCount/>
        </Form.Item>
        <Form.Item name="evidence_ref" label="Nguồn/đối chiếu" rules={[{required:true,min:3,max:160}]}>
          <Input placeholder="owner-confirmed-brief-2026-11"/>
        </Form.Item>
        <Button type="primary" htmlType="submit">Lưu ghi chú có nguồn</Button>
      </Form>
    </Card>
  </Space>;
}
