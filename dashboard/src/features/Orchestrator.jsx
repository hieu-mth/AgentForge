import {useEffect,useState} from 'react';
import {App as AntApp,Button,Card,Form,Grid,Select,Space,Switch,Table,Typography} from 'antd';
import {ApartmentOutlined,ControlOutlined,RollbackOutlined,SafetyCertificateOutlined,SaveOutlined,TeamOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';

const {Title,Text}=Typography;
const modeOptions=[
  {value:'MANUAL',label:'Thủ công'},
  {value:'SUPERVISED',label:'Có giám sát'},
];
const toolOptions=[
  {value:'ffmpeg',label:'FFmpeg'},
];
const unset='';

function RuleRow({title,description,children}){
  return <section className="orchestrator-rule-row">
    <div className="orchestrator-rule-copy">
      <h3>{title}</h3>
      <div>{description}</div>
    </div>
    <div className="orchestrator-rule-controls">{children}</div>
  </section>;
}

function PermissionToggle({field,label,description}){
  return <div className="orchestrator-permission">
    <div><strong>{label}</strong><span>{description}</span></div>
    <Form.Item name={['permissions',field]} valuePropName="checked">
      <Switch aria-label={label}/>
    </Form.Item>
  </div>;
}

export function Orchestrator({mutate,dirty,setDirty}){
  const resource=useResource('/api/model-hub');
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
  const runTools=Form.useWatch(['permissions','run_tools'],form)??policy.permissions.run_tools;
  const profiles=snapshot.profiles;
  const options=profiles.filter(p=>p.enabled).map(p=>({value:p.id,label:p.id+' · '+p.model}));
  const initial={mode:policy.mode==='MANUAL'?'MANUAL':'SUPERVISED',
    permissions:policy.permissions,tools:policy.tools.filter(tool=>tool==='ffmpeg'),
    bindings:Object.fromEntries(capabilities.filter(row=>!row.tool&&row.kind!=='vision')
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
        'Áp dụng quyền thực thi và model đã gán cho Studio. Các tùy chọn cũ không còn được hỗ trợ sẽ trở về mặc định; dữ liệu lịch sử vẫn được giữ.',
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
    for(const row of capabilities){
      if(row.tool||row.kind==='vision')continue;
      const ref=values.bindings?.[row.id];
      if(row.existing_route){
        if(ref!==initial.bindings[row.id])route_changes[row.id]=ref||null;
      }else if(ref)mappings[row.id]=ref;
    }
    const next={mode:values.mode,mappings,permissions:values.permissions,
      tools:form.getFieldValue('tools')??initial.tools};
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

  const mainBinding=row=>row.kind==='vision'
      ?<Text type="secondary">Chưa có adapter kiểm tra thị giác.</Text>
      :row.tool||modelField(['bindings',row.id],
      options.filter(option=>row.options.includes(option.value)),row.model_ref,
      'Chưa gán',undefined,'Model chính · '+row.label);
  const capabilityStatus=row=><Space direction="vertical" size={4}>
    <SettingsStatus tone={({DETERMINISTIC:'good',UNAVAILABLE:'warn'})[row.status]}>
      {({DETERMINISTIC:'Theo quy tắc',CONFIG_ONLY:'Chỉ cấu hình',LOCAL_RUNTIME:'Có runtime local',
        UNAVAILABLE:'Không khả dụng'})[row.status]}
    </SettingsStatus>
    {row.adapter==='EXISTING_TOOL'&&<Text className="env-muted">Có công cụ riêng</Text>}
  </Space>;

  return <Form form={form} layout="vertical" initialValues={initial}
    onValuesChange={()=>setDirty(true)} onFinish={save} disabled={saving}>
    <SettingsHeading className="orchestrator-header" title="AI điều phối tác vụ" eyebrow="CHÍNH SÁCH OWNER"
      description={<>
        Phân công model theo năng lực và cấp quyền thực thi local cho Studio.
        <span className="orchestrator-edit-status" role="status">
          <SettingsStatus tone={dirty?'warn':'neutral'}>
            {dirty?'Có thay đổi chưa lưu':'Không có thay đổi'}
          </SettingsStatus>
        </span>
      </>}
      actions={<>
        <Button className={!dirty?'orchestrator-cancel-idle':undefined} disabled={!dirty}
          onClick={()=>{form.resetFields();setDirty(false);}}>Hủy thay đổi</Button>
        <Button type="primary" icon={<SaveOutlined/>} htmlType="submit" disabled={!dirty} loading={saving}>Lưu cấu hình</Button>
      </>}/>
    <Card className="env-panel" title={<SectionTitle icon={<ApartmentOutlined/>}
      title="Chế độ thực thi" description="Cho phép Studio chạy local hoặc giữ chế độ thủ công"/>}>
      <div className="orchestrator-meta">
        <span className="env-checked">{owner_override?'Owner tùy chỉnh':'Mặc định'} · Phiên bản {snapshot.revision}</span>
      </div>
      <div className="orchestrator-fields">
        <Form.Item name="mode" label="Chế độ hoạt động"><Select options={modeOptions}/></Form.Item>
      </div>
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<TeamOutlined/>}
      title="Phân công AI theo năng lực" description="Gán model hoặc công cụ phù hợp cho từng việc. Studio dùng các tuyến local tương thích đã gán; không tự chuyển model."/>}>
      {desktop?<Table className="hub-table" rowKey="id" pagination={false} dataSource={capabilities}
        columns={[
          {title:'Năng lực',dataIndex:'label',width:'22%'},
          {title:'Model hoặc công cụ chính',render:(_,row)=>mainBinding(row),width:'30%'},
          {title:'Trạng thái đã lưu',render:(_,row)=>capabilityStatus(row)},
        ]}/>:<div className="orchestrator-capabilities">{capabilities.map(row=>
          <section key={row.id}><Title level={5}>{row.label}</Title>{capabilityStatus(row)}
            <div>{mainBinding(row)}</div>
          </section>)}</div>}
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<ControlOutlined/>}
      title="An toàn runtime" description="Các điều kiện bắt buộc khi xử lý media local"/>}>
      <p>GPU xử lý lần lượt. Studio dừng hoặc giữ checkpoint khi thiếu tài nguyên.</p>
      <p className="env-muted orchestrator-rule-note">Không tự chuyển model, không gọi cloud. Luôn đối soát tác vụ ComfyUI chưa rõ kết quả trước khi gửi lại.</p>
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<SafetyCertificateOutlined/>}
      title="Quyền thực thi" description="Các quyền được kiểm tra trước khi Studio chạy"/>}>
      <div>
        <RuleRow title="AI được tự làm gì" description="Chọn từng bước AI được phép tự thực hiện.">
          <PermissionToggle field="plan" label="Lập kế hoạch"
            description="Cho phép Studio lập kế hoạch."/>
          <PermissionToggle field="assign_local" label="Giao việc local"
            description="Cho phép dùng các model local đã được phân công."/>
          <PermissionToggle field="call_local" label="Gọi model local"
            description="Gửi yêu cầu thực thi đến model đã được cấp quyền."/>
        </RuleRow>
        <RuleRow title="Công cụ local" description="Chọn những công cụ AI được phép chạy trên máy này.">
          <PermissionToggle field="run_tools" label="Chạy công cụ local"
            description="Cho phép Studio sử dụng công cụ dựng video."/>
          {runTools&&<Form.Item name="tools" label="Công cụ local được phép">
            <Select mode="multiple" options={toolOptions} placeholder="Chọn công cụ"/>
          </Form.Item>}
        </RuleRow>
      </div>
      <div className="orchestrator-approval-note">
        <SafetyCertificateOutlined aria-hidden="true"/>
        <div><strong>Luôn cần Owner duyệt</strong>
          <div>Gọi cloud hoặc API trả phí, tải model, thay đổi dữ liệu quan trọng, xuất bản và thay đổi quyền riêng tư.</div>
        </div>
      </div>
    </Card>
    <div className="model-history">
      <Button type="text" icon={<RollbackOutlined/>} onClick={()=>confirm('RESET_ORCHESTRATOR')}>
        Đặt lại mặc định
      </Button>
    </div>
  </Form>;
}
