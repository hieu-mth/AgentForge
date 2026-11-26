import {useEffect,useState} from 'react';
import {App as AntApp,Button,Card,Form,InputNumber,Select,Switch,Typography} from 'antd';
import {ApartmentOutlined,ControlOutlined,RollbackOutlined,SafetyCertificateOutlined,SaveOutlined,TeamOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {configurableProfiles} from '../model_hub_ui.js';

const {Text}=Typography;
const modeOptions=[
  {value:'MANUAL',label:'Thủ công'},
  {value:'SUPERVISED',label:'Có giám sát'},
];
const toolOptions=[
  {value:'ffmpeg',label:'FFmpeg'},
];

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
  const [saving,setSaving]=useState(false);
  const profiles=snapshot.profiles??[];
  const byAdapter=Object.fromEntries((snapshot.adapters??[]).map(adapter=>[adapter.id,adapter]));

  const [routeChanges,setRouteChanges]=useState({});
  function updateRoute(taskId,model){
    setRouteChanges(changes=>({...changes,[taskId]:model||null}));
    setDirty(true);
  }
  const {policy,owner_override}=snapshot.orchestrator;
  const runTools=Form.useWatch(['permissions','run_tools'],form)??policy.permissions.run_tools;
  const initial={mode:policy.mode,
    permissions:policy.permissions,tools:policy.tools,cloud_call_limit:policy.cloud_call_limit};

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
      content:reset?'Đặt lại quyền thực thi, công cụ và ngân sách. Phân công model không thay đổi.':
        'Áp dụng quyền thực thi và ngân sách cho Studio. Phân công model và dữ liệu lịch sử không thay đổi.',
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
    const next={mode:values.mode,permissions:values.permissions,
      tools:form.getFieldValue('tools')??initial.tools,cloud_call_limit:values.cloud_call_limit};
    confirm('SAVE_ORCHESTRATOR',{policy:next,route_changes:routeChanges});
  }

  return <Form form={form} layout="vertical" initialValues={initial}
    onValuesChange={()=>setDirty(true)} onFinish={save} disabled={saving}>
    <SettingsHeading className="orchestrator-header" title="AI điều phối tác vụ" eyebrow="CHÍNH SÁCH OWNER"
      description={<>
        Phân công model, quản lý quyền thực thi, công cụ và ngân sách của Studio.
        <span className="orchestrator-edit-status" role="status">
          <SettingsStatus tone={dirty?'warn':'neutral'}>
            {dirty?'Có thay đổi chưa lưu':'Không có thay đổi'}
          </SettingsStatus>
        </span>
      </>}
      actions={<>
        <Button className={!dirty?'orchestrator-cancel-idle':undefined} disabled={!dirty}
          onClick={()=>{form.resetFields();setRouteChanges({});setDirty(false);}}>Hủy thay đổi</Button>
        <Button type="primary" icon={<SaveOutlined/>} htmlType="submit" disabled={!dirty} loading={saving}>Lưu cấu hình</Button>
      </>}/>
    <Card className="env-panel" title={<SectionTitle icon={<ApartmentOutlined/>}
      title="Chế độ thực thi" description="Cho phép Studio chạy theo quyền đã cấp hoặc giữ chế độ thủ công"/>}>
      <div className="orchestrator-meta">
        <span className="env-checked">{owner_override?'Owner tùy chỉnh':'Mặc định'} · Phiên bản {snapshot.revision}</span>
      </div>
      <div className="orchestrator-fields">
        <Form.Item name="mode" label="Chế độ hoạt động"><Select options={modeOptions}/></Form.Item>
      </div>
    </Card>
    {snapshot.routes?.some(route=>route.kind!=='rules')&&<Card className="env-panel"
      title={<SectionTitle icon={<TeamOutlined/>} title="Phân công model"
        description="Chọn model đã đăng ký tại Model AI cho từng năng lực. Phân công được lưu riêng với chính sách."/>}>
      <div className="model-route-list">{snapshot.routes.filter(route=>route.kind!=='rules').map(route=>{
        const options=configurableProfiles(profiles,route.id);
        const selected=Object.hasOwn(routeChanges,route.id)?routeChanges[route.id]:route.model_ref;
        return <label key={route.id} className="model-route">
          <strong>{route.label}</strong>
          <Select disabled={saving} showSearch optionFilterProp="label" aria-label={'Model cho '+route.label} value={selected??''}
            options={[{value:'',label:'Chưa gán'},...options.map(profile=>({value:profile.id,
              label:(profile.id.toLowerCase().replace(/[._-]/g,'')===profile.model.toLowerCase().replace(/[._-]/g,'')
                ?profile.model:profile.id+' · '+profile.model)
                +(byAdapter[profile.provider]?.connection==='cloud'?' · Cloud':' · Local')})),
              ...(route.model_ref&&!options.some(profile=>profile.id===route.model_ref)
                ?[{value:route.model_ref,label:route.model_ref+' · Không khả dụng',disabled:true}]:[])]}
            onChange={model=>updateRoute(route.id,model)}/>
        </label>;
      })}</div>
    </Card>}
    <Card className="env-panel" title={<SectionTitle icon={<ControlOutlined/>}
      title="An toàn runtime" description="Các điều kiện bắt buộc khi xử lý media local"/>}>
      <p>GPU xử lý lần lượt. Studio dừng hoặc giữ checkpoint khi thiếu tài nguyên.</p>
      <p className="env-muted orchestrator-rule-note">AI chỉ chọn tuyến trong các model và quyền đã cấp khi Owner yêu cầu; tuyến đã duyệt không tự đổi. Luôn đối soát job local hoặc cloud chưa rõ kết quả trước khi gửi lại.</p>
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<SafetyCertificateOutlined/>}
      title="Quyền thực thi" description="Các quyền được kiểm tra trước khi Studio chạy"/>}>
      <div>
        <RuleRow title="AI được tự làm gì" description="Chọn từng bước AI được phép tự thực hiện.">
          <PermissionToggle field="plan" label="Lập kế hoạch"
            description="Cho phép Studio lập kế hoạch."/>
          <PermissionToggle field="assign_models" label="Sử dụng model đã phân công"
            description="Cho phép sử dụng model đã phân công hoặc chọn tuyến trong phạm vi cấu hình."/>
          <PermissionToggle field="call_local" label="Gọi model local"
            description="Gửi yêu cầu thực thi đến model local đã được cấp quyền."/>
          <PermissionToggle field="call_cloud" label="Gọi AI cloud"
            description="Cho phép gửi nội dung và mô tả nhân vật đến endpoint cloud đã phân công; API có thể tính phí."/>
          <Form.Item name="cloud_call_limit" label="Giới hạn lượt gọi cloud mỗi production"
            rules={[{required:true,type:'integer',min:1,max:1000}]}>
            <InputNumber min={1} max={1000} precision={0}/>
          </Form.Item>
          <Text type="secondary">Tính cả lượt lỗi và thử lại. Đây không phải giới hạn số tiền.</Text>
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
          <div>Cấp quyền cloud và giới hạn lượt gọi trước khi tạo production. Chạy thử cloud, tải model, xuất bản và thay đổi quyền riêng tư cần xác nhận riêng.</div>
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
