import {useEffect,useState} from 'react';
import {Alert,App as AntApp,Button,Card,Checkbox,Form,Grid,InputNumber,Select,Space,Table,Typography} from 'antd';
import {ApartmentOutlined,ControlOutlined,RollbackOutlined,SafetyCertificateOutlined,SaveOutlined,TeamOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';

const {Title,Text}=Typography;
const modeOptions=[
  {value:'MANUAL',label:'Thủ công'},
  {value:'SUPERVISED',label:'Có giám sát'},
  {value:'AUTOMATIC',label:'Tự động · chỉ cấu hình'},
];
const permissions={
  plan:'Tự phân tích và lập kế hoạch',
  assign_local:'Tự phân công tác vụ local an toàn',
  call_local:'Gọi model local đã được phép',
  run_tools:'Chạy công cụ local trong danh sách cho phép',
};
const toolOptions=[
  {value:'local_tts',label:'Tạo thoại local'},
  {value:'ffmpeg',label:'FFmpeg'},
  {value:'system_rules',label:'Quy tắc hệ thống'},
];
const unset='';
const fallbackCapabilities=['general.text','film.storyboard'];

export function Orchestrator({mutate}){
  const resource=useResource('/api/model-hub');
  const [dirty,setDirty]=useState(false);
  useScreenRefresh(()=>dirty?undefined:resource.reload());
  return <div className="orchestrator-page">
    <ResourceStatus resource={resource} label="chính sách điều phối"/>
    {resource.data?.orchestrator&&<PolicyEditor key={resource.data.revision}
      snapshot={resource.data} mutate={mutate} dirty={dirty} setDirty={setDirty}
      accept={resource.setData}/>}
  </div>;
}

function PolicyEditor({snapshot,mutate,dirty,setDirty,accept}){
  const {modal,message}=AntApp.useApp();
  const [form]=Form.useForm();
  const {md:desktop}=Grid.useBreakpoint();
  const [saving,setSaving]=useState(false);
  const {policy,capabilities,owner_override}=snapshot.orchestrator;
  const selection=Form.useWatch('selection',form)??policy.selection;
  const exclusive=Form.useWatch('gpu_exclusive',form)??policy.gpu_exclusive;
  const primary=Form.useWatch('primary',form)??policy.primary;
  const profiles=snapshot.profiles;
  const options=profiles.filter(p=>p.enabled).map(p=>({value:p.id,label:p.id+' · '+p.model}));
  const textOptions=options.filter(option=>profiles.some(
    p=>p.id===option.value&&['ollama','anthropic'].includes(p.provider)));
  const localOptions=options.filter(option=>profiles.some(p=>p.id===option.value&&p.provider==='ollama'));
  const initial={...policy,primary:policy.primary??unset,
    fallbacks:Object.fromEntries(fallbackCapabilities.map(id=>[id,policy.fallbacks[id]??unset])),
    bindings:Object.fromEntries(capabilities.filter(row=>!row.tool)
      .map(row=>[row.id,row.model_ref??unset]))};

  useEffect(()=>{
    if(!dirty)return;
    const protect=event=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',protect);
    return ()=>window.removeEventListener('beforeunload',protect);
  },[dirty]);

  function confirm(ack,values={}){
    const reset=ack==='RESET_ORCHESTRATOR';
    modal.confirm({
      title:reset?'Đặt lại chính sách điều phối?':'Lưu chính sách điều phối?',
      content:reset?'Chính sách và các mapping điều phối sẽ trở về mặc định.':
        'Lưu cấu hình mục tiêu cho phiên bản '+snapshot.revision+'. Các lựa chọn này chưa được áp dụng vào thực thi.',
      okText:reset?'Đặt lại':'Lưu cấu hình',cancelText:'Hủy',
      onOk:async()=>{
        setSaving(true);
        try{
          const result=await mutate('/api/model-hub/orchestrator',{
            ack,expected_revision:snapshot.revision,...values,
          });
          if(!result)return;
          setDirty(false);
          accept(result);
          message.success(reset?'Đã đặt lại chính sách':'Đã lưu chính sách');
        }finally{setSaving(false);}
      },
    });
  }

  function save(values){
    const route_changes={};
    const mappings={};
    const fallbacks={};
    for(const row of capabilities){
      const ref=values.bindings?.[row.id];
      if(row.existing_route){
        if(ref!==initial.bindings[row.id])route_changes[row.id]=ref||null;
      }else if(ref)mappings[row.id]=ref;
      const fallback=values.fallbacks?.[row.id];
      if(fallback&&(fallback===(ref||row.default_ref))){
        form.setFields([{name:['fallbacks',row.id],errors:['Model dự phòng phải khác model chính.']}]);
        return;
      }
      if(fallback)fallbacks[row.id]=fallback;
    }
    const next={...policy,...values,primary:values.primary||null,mappings,fallbacks};
    delete next.bindings;
    confirm('SAVE_ORCHESTRATOR',{policy:next,route_changes});
  }

  function modelField(name,choices,current,placeholder,label,accessibleName=label){
    const valid=choices.some(option=>option.value===current)||!current;
    return <Form.Item name={name} className="orchestrator-inline-field" label={label}
      rules={[{validator:(_,value)=>!value||choices.some(option=>option.value===value)
        ?Promise.resolve():Promise.reject(new Error('Model không khả dụng hoặc không tương thích.'))}]}>
      <Select aria-label={accessibleName} options={[{value:unset,label:placeholder},...choices,
        ...(!valid?[{value:current,label:current+' · Không khả dụng',disabled:true}]:[])]}/>
    </Form.Item>;
  }

  const mainBinding=row=>row.id==='film.tts'?
    <Form.Item name="tts_engine" className="orchestrator-inline-field"><Select aria-label="Công cụ tạo thoại" options={[
      {value:'windows',label:'Windows SAPI'},{value:'piper',label:'Piper offline'},
    ]}/></Form.Item>:row.kind==='vision'
      ?<Text type="secondary">Model Hub chưa khai báo năng lực thị giác.</Text>
      :row.tool||modelField(['bindings',row.id],
      options.filter(option=>row.options.includes(option.value)),row.model_ref,
      row.default_ref?'Mặc định · '+row.default_ref:'Chưa gán',undefined,'Model chính · '+row.label);
  const fallbackBinding=row=>fallbackCapabilities.includes(row.id)
    ?modelField(['fallbacks',row.id],localOptions,policy.fallbacks[row.id],
      'Không dùng dự phòng',undefined,'Model dự phòng · '+row.label):'—';
  const capabilityStatus=row=><Space direction="vertical" size={4}>
    <SettingsStatus tone={({DETERMINISTIC:'good',UNAVAILABLE:'warn'})[row.status]}>
      {({DETERMINISTIC:'Theo quy tắc',CONFIG_ONLY:'Chỉ cấu hình',UNAVAILABLE:'Không khả dụng'})[row.status]}
    </SettingsStatus>
    {row.adapter==='EXISTING_TOOL'&&<Text className="env-muted">Có công cụ riêng</Text>}
  </Space>;

  return <Form form={form} layout="vertical" initialValues={initial}
    onValuesChange={(_,values)=>{
      if(values.gpu_exclusive)form.setFieldValue('gpu_concurrency',1);
      setDirty(true);
    }} onFinish={save} disabled={saving}>
    <SettingsHeading className="orchestrator-header" title="AI điều phối tác vụ" eyebrow="CHÍNH SÁCH OWNER"
      description="Chọn model điều phối, phân công theo năng lực và đặt giới hạn cho từng tác vụ."
      actions={<>
        {dirty&&<Button onClick={()=>{form.resetFields();setDirty(false);}}>Hủy thay đổi</Button>}
        <Button type="primary" icon={<SaveOutlined/>} htmlType="submit" disabled={!dirty} loading={saving}>Lưu cấu hình</Button>
      </>}/>
    {dirty&&<Alert showIcon type="warning" message="Có thay đổi chưa lưu"/>}
    <Card className="env-panel" title={<SectionTitle icon={<ApartmentOutlined/>}
      title="AI điều phối chính" description="Phân tích yêu cầu và đề xuất cách phân công"/>}>
      <div className="orchestrator-meta">
        <SettingsStatus>Chỉ cấu hình</SettingsStatus>
        <span className="env-checked">{owner_override?'Owner tùy chỉnh':'Mặc định'} · Phiên bản {snapshot.revision}</span>
      </div>
      <div className="orchestrator-fields">
        <div>{modelField('primary',textOptions,policy.primary,'Chưa chọn model','Model điều phối')}
          {primary&&<Text className="env-muted">{textOptions.some(option=>option.value===primary)
            ?'Đã cấu hình · Chưa xác minh khả năng chạy':'Model không khả dụng'}</Text>}</div>
        <Form.Item name="mode" label="Chế độ hoạt động"><Select options={modeOptions}/></Form.Item>
      </div>
      <Form.Item className="orchestrator-toggle" name="decompose" valuePropName="checked">
        <Checkbox>Tự phân tích và chia nhỏ yêu cầu</Checkbox>
      </Form.Item>
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<TeamOutlined/>}
      title="Phân công AI theo năng lực" description="Gán model hoặc công cụ phù hợp cho từng việc. Các tuyến model đang ở mức cấu hình."/>}>
      {desktop?<Table className="hub-table" rowKey="id" pagination={false} dataSource={capabilities}
        columns={[
          {title:'Năng lực',dataIndex:'label',width:'22%'},
          {title:'Model hoặc công cụ chính',render:(_,row)=>mainBinding(row),width:'30%'},
          {title:'Dự phòng local',render:(_,row)=>fallbackBinding(row),width:'25%'},
          {title:'Trạng thái đã lưu',render:(_,row)=>capabilityStatus(row)},
        ]}/>:<div className="orchestrator-capabilities">{capabilities.map(row=>
          <section key={row.id}><Title level={5}>{row.label}</Title>{capabilityStatus(row)}
            <div>{mainBinding(row)}</div>
            {fallbackCapabilities.includes(row.id)&&<div>{fallbackBinding(row)}</div>}
          </section>)}</div>}
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<ControlOutlined/>}
      title="Quy tắc tự động điều phối" description="Chính sách lựa chọn model, dự phòng và tài nguyên GPU"/>}>
      <div className="orchestrator-fields">
        <Form.Item name="selection" label="Lựa chọn model"><Select options={[
          {value:'FIXED',label:'Theo mapping cố định'},{value:'SUGGEST',label:'AI đề xuất từ danh sách cho phép'},
        ]}/></Form.Item>
        <Form.Item name="allowed_profiles" label="Model được phép đề xuất"
          rules={[{validator:(_,value)=>(selection!=='SUGGEST'||value?.length)&&
            (value||[]).every(ref=>options.some(option=>option.value===ref))
            ?Promise.resolve():Promise.reject(new Error('Chọn model khả dụng cho danh sách đề xuất.'))}]}>
          <Select mode="multiple" options={options}/>
        </Form.Item>
        <Form.Item name="fallback" label="Khi model chính không khả dụng"><Select options={[
          {value:'STOP',label:'Dừng và báo Owner'},{value:'LOCAL',label:'Dùng model local dự phòng đã gán'},
        ]}/></Form.Item>
        <Form.Item name="unavailable" label="Khi thiếu VRAM hoặc tài nguyên"><Select options={[
          {value:'STOP',label:'Dừng và báo Owner'},{value:'WAIT_OWNER',label:'Chờ Owner xử lý'},
        ]}/></Form.Item>
        <Form.Item name="gpu_exclusive" valuePropName="checked"><Checkbox>GPU độc quyền</Checkbox></Form.Item>
        <Form.Item name="gpu_concurrency" label="Tác vụ GPU đồng thời"
          rules={[{required:true,type:'integer',min:1,max:8,message:'Nhập số nguyên từ 1 đến 8.'}]}>
          <InputNumber min={1} max={8} precision={0} disabled={exclusive||saving}/>
        </Form.Item>
      </div>
      <Text type="secondary">Tác vụ ComfyUI chưa rõ kết quả phải được đối chiếu trước khi thử lại. Các giới hạn GPU và retry là cấu hình mục tiêu.</Text>
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<SafetyCertificateOutlined/>}
      title="Quyền hạn & giới hạn" description="Phạm vi được phép, giới hạn thử lại và ngân sách tác vụ"/>}>
      <div className="orchestrator-fields">
        {Object.entries(permissions).map(([key,label])=><Form.Item key={key}
          name={['permissions',key]} valuePropName="checked"><Checkbox>{label}</Checkbox></Form.Item>)}
        <Form.Item name="tools" label="Công cụ local được phép"><Select mode="multiple" options={toolOptions}/></Form.Item>
        <Form.Item name="retry_limit" label="Số lần thử lại tối đa"
          rules={[{required:true,type:'integer',min:0,max:5,message:'Nhập số nguyên từ 0 đến 5.'}]}>
          <InputNumber min={0} max={5} precision={0}/>
        </Form.Item>
        <Form.Item name="task_budget" label="Ngân sách mỗi yêu cầu (số tác vụ)"
          rules={[{required:true,type:'integer',min:1,max:100,message:'Nhập số nguyên từ 1 đến 100.'}]}>
          <InputNumber min={1} max={100} precision={0}/>
        </Form.Item>
      </div>
      <Alert type="info" showIcon message="Luôn cần Owner duyệt"
        description="Gọi cloud hoặc API trả phí, tải model, thay đổi dữ liệu quan trọng, xuất bản và thay đổi quyền riêng tư."/>
    </Card>
    <div className="model-history">
      <Button type="text" icon={<RollbackOutlined/>} onClick={()=>confirm('RESET_ORCHESTRATOR')}>
        Đặt lại mặc định
      </Button>
    </div>
  </Form>;
}
