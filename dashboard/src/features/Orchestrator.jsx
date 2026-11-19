import {useEffect,useState} from 'react';
import {App as AntApp,Button,Card,Checkbox,Form,Grid,InputNumber,Radio,Select,Space,Switch,Table,Typography} from 'antd';
import {ApartmentOutlined,ControlOutlined,RollbackOutlined,SafetyCertificateOutlined,SaveOutlined,TeamOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';

const {Title,Text}=Typography;
const modeOptions=[
  {value:'MANUAL',label:'Thủ công'},
  {value:'SUPERVISED',label:'Có giám sát'},
  {value:'AUTOMATIC',label:'Tự động'},
];
const toolOptions=[
  {value:'local_tts',label:'Tạo thoại local'},
  {value:'ffmpeg',label:'FFmpeg'},
  {value:'system_rules',label:'Quy tắc hệ thống'},
];
const unset='';
const fallbackCapabilities=['general.text','film.storyboard'];

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

function LimitField({name,label,min,max,unit,note}){
  return <Form.Item name={name} label={label} extra={note}
    rules={[{required:true,type:'integer',min,max,message:
      max===Number.MAX_SAFE_INTEGER?'Nhập số nguyên không âm.':`Nhập số nguyên từ ${min} đến ${max}.`}]}>
    <InputNumber aria-label={label} min={min} max={max} precision={0} addonAfter={unit}/>
  </Form.Item>;
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
  const selection=Form.useWatch('selection',form)??policy.selection;
  const exclusive=Form.useWatch('gpu_exclusive',form)??policy.gpu_exclusive;
  const fallbackMode=Form.useWatch('fallback',form)??policy.fallback;
  const draftFallbacks=Form.useWatch('fallbacks',form)??policy.fallbacks;
  const draftBindings=Form.useWatch('bindings',form);
  const primary=Form.useWatch('primary',form)??policy.primary;
  const runTools=Form.useWatch(['permissions','run_tools'],form)??policy.permissions.run_tools;
  const profiles=snapshot.profiles;
  const options=profiles.filter(p=>p.enabled).map(p=>({value:p.id,label:p.id+' · '+p.model}));
  const textOptions=options.filter(option=>profiles.some(
    p=>p.id===option.value&&['ollama','anthropic'].includes(p.provider)));
  const localOptions=options.filter(option=>profiles.some(p=>p.id===option.value&&p.provider==='ollama'));
  const initial={...policy,primary:policy.primary??unset,
    fallbacks:Object.fromEntries(fallbackCapabilities.map(id=>[id,policy.fallbacks[id]??unset])),
    bindings:Object.fromEntries(capabilities.filter(row=>!row.tool)
      .map(row=>[row.id,row.model_ref??unset]))};
  const fallbackLabels=capabilities.filter(row=>{
    const fallback=draftFallbacks[row.id];
    const binding=draftBindings?.[row.id]??initial.bindings[row.id];
    return fallback&&fallback!==(binding||row.default_ref)
      &&localOptions.some(option=>option.value===fallback);
  }).map(row=>row.label);

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
        'Lưu cấu hình cho phiên bản '+snapshot.revision+'. Quyền local và model được gán sẽ áp dụng cho các yêu cầu tạo ảnh FLUX.',
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
    const next={...policy,...values,primary:values.primary||null,mappings,fallbacks,
      tools:form.getFieldValue('tools')??policy.tools};
    if(next.gpu_exclusive)next.gpu_concurrency=1;
    if(next.selection==='FIXED'){
      next.allowed_profiles=(form.getFieldValue('allowed_profiles')??[])
        .filter(ref=>options.some(option=>option.value===ref));
    }
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
      {({DETERMINISTIC:'Theo quy tắc',CONFIG_ONLY:'Chỉ cấu hình',LOCAL_RUNTIME:'Có runtime local',
        UNAVAILABLE:'Không khả dụng'})[row.status]}
    </SettingsStatus>
    {row.adapter==='EXISTING_TOOL'&&<Text className="env-muted">Có công cụ riêng</Text>}
  </Space>;

  return <Form form={form} layout="vertical" initialValues={initial}
    onValuesChange={changed=>{
      if(changed.gpu_exclusive===false&&form.getFieldValue('gpu_concurrency')===1)
        form.setFieldValue('gpu_concurrency',2);
      setDirty(true);
    }} onFinish={save} disabled={saving}>
    <SettingsHeading className="orchestrator-header" title="AI điều phối tác vụ" eyebrow="CHÍNH SÁCH OWNER"
      description={<>
        Chọn model điều phối, phân công theo năng lực và đặt giới hạn cho từng tác vụ.
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
      <div className="orchestrator-rules">
        <RuleRow title="Chọn model" description="Quy định cách chọn model cho từng tác vụ.">
          <Form.Item name="selection"><Radio.Group aria-label="Lựa chọn model" optionType="button" buttonStyle="solid" options={[
            {value:'FIXED',label:'Dùng model đã gán'},{value:'SUGGEST',label:'AI đề xuất'},
          ]}/></Form.Item>
          {selection==='SUGGEST'&&<Form.Item name="allowed_profiles" label="Model được phép đề xuất"
            rules={[{validator:(_,value)=>value?.length&&
              value.every(ref=>options.some(option=>option.value===ref))
              ?Promise.resolve():Promise.reject(new Error('Chọn model khả dụng cho danh sách đề xuất.'))}]}>
            <Select mode="multiple" options={options}/>
          </Form.Item>}
        </RuleRow>
        <RuleRow title="Khi gặp sự cố" description="Chọn cách xử lý khi model hoặc tài nguyên không khả dụng.">
          <Form.Item name="fallback" label="Model không khả dụng"><Select options={[
            {value:'STOP',label:'Dừng và báo Owner'},{value:'LOCAL',label:'Dùng model local dự phòng đã gán'},
          ]}/></Form.Item>
          <Form.Item name="unavailable" label="Thiếu tài nguyên"><Select options={[
            {value:'STOP',label:'Dừng và báo Owner'},{value:'WAIT_OWNER',label:'Chờ Owner xử lý'},
          ]}/></Form.Item>
          {fallbackMode==='LOCAL'&&<p className="env-muted orchestrator-rule-hint" aria-live="polite">
            {fallbackLabels.length
              ?'Đã gán dự phòng cho '+fallbackLabels.length+' năng lực: '+fallbackLabels.join(', ')+'.'
              :'Chưa gán model dự phòng. Hãy chọn model trong bảng Phân công AI theo năng lực.'}
          </p>}
        </RuleRow>
        <RuleRow title="Tài nguyên GPU" description="Đặt số tác vụ nặng GPU có thể chạy cùng lúc.">
          <div className="orchestrator-gpu-controls">
            <Form.Item name="gpu_exclusive">
              <Radio.Group aria-label="Cách chạy tác vụ GPU" optionType="button" buttonStyle="solid" options={[
                {value:true,label:'Chạy lần lượt'},
                {value:false,label:'Chạy đồng thời'},
              ]}/>
            </Form.Item>
            {!exclusive&&<div className="orchestrator-gpu-count">
              <Form.Item name="gpu_concurrency"
                rules={[{required:true,type:'integer',min:1,max:8,message:'Nhập số nguyên từ 1 đến 8.'}]}>
                <InputNumber aria-label="Tác vụ GPU đồng thời" min={1} max={8} precision={0}/>
              </Form.Item>
              <span aria-hidden="true">tác vụ</span>
            </div>}
          </div>
        </RuleRow>
      </div>
      <p className="env-muted orchestrator-rule-note">FLUX tạo từng ảnh qua hàng đợi ComfyUI. Hãy đối chiếu tác vụ chưa rõ kết quả trước khi gửi lại.</p>
    </Card>
    <Card className="env-panel" title={<SectionTitle icon={<SafetyCertificateOutlined/>}
      title="Quyền hạn & giới hạn" description="Các quyền và hạn mức mục tiêu cho AI điều phối"/>}>
      <div>
        <RuleRow title="AI được tự làm gì" description="Chọn từng bước AI được phép tự thực hiện.">
          <PermissionToggle field="plan" label="Lập kế hoạch"
            description="Phân tích yêu cầu và chia thành các bước."/>
          <PermissionToggle field="assign_local" label="Giao việc local"
            description="Phân công mỗi bước cho model hoặc công cụ local phù hợp."/>
          <PermissionToggle field="call_local" label="Gọi model local"
            description="Gửi yêu cầu thực thi đến model đã được cấp quyền."/>
        </RuleRow>
        <RuleRow title="Công cụ local" description="Chọn những công cụ AI được phép chạy trên máy này.">
          <PermissionToggle field="run_tools" label="Chạy công cụ local"
            description="Giới hạn theo danh sách công cụ bạn cho phép."/>
          {runTools&&<Form.Item name="tools" label="Công cụ local được phép">
            <Select mode="multiple" options={toolOptions} placeholder="Chọn công cụ"/>
          </Form.Item>}
        </RuleRow>
        <RuleRow title="Giới hạn sử dụng" description="Đặt ngưỡng cho mỗi yêu cầu và số lượt gọi API trong ngày.">
          <div className="orchestrator-limit-fields">
            <LimitField name="retry_limit" label="Số lần thử lại tối đa" min={0} max={5} unit="lần"/>
            <LimitField name="task_budget" label="Số tác vụ tối đa mỗi yêu cầu" min={1} max={100} unit="tác vụ"/>
            <LimitField name="paid_api_daily_limit" label="Lượt gọi API trả phí mỗi ngày"
              min={0} max={Number.MAX_SAFE_INTEGER} unit="lượt/ngày"
              note="Chưa áp dụng khi chạy. API trả phí vẫn cần Owner duyệt."/>
          </div>
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
