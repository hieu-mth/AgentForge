import {Fragment,useState} from 'react';
import {Alert,Button,Form,Input,InputNumber,Modal,Radio,Select,Space,Switch} from 'antd';
import {ApiOutlined,CloudOutlined,DesktopOutlined} from '@ant-design/icons';
import {SectionTitle} from '../components/settings.jsx';
import {profilePayload} from '../model_hub_ui.js';
import {requestError} from '../api.js';

const connectionOptions=[
  {value:'local',label:<><DesktopOutlined/> Local</>},
  {value:'cloud',label:<><CloudOutlined/> Cloud</>},
];
const fieldLabels={
  base_url:'Địa chỉ runtime local',
  base_url_env:'Biến môi trường chứa endpoint',
  api_key_env:'Biến môi trường chứa API key',
};
const localUrl=/^http:\/\/(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})\/?$/;
const envName=/^[A-Z_][A-Z0-9_]*$/;

export function ModelProfileDialog({adapters,profile,profiles,revision,onCancel,onSave}){
  const [form]=Form.useForm();
  const initialAdapter=adapters.find(item=>item.id===profile?.provider)??adapters[0];
  const initial={connection:initialAdapter.connection,provider:initialAdapter.id,
    enabled:true,...initialAdapter.defaults,...profile,
    flux_enabled:Boolean(profile?.flux),flux_settings:{
      max_resolution:1024,max_steps:4,timeout_seconds:180,output_dir:'visuals',
      ...profile?.flux,workflow:profile?.flux?JSON.stringify(profile.flux.workflow,null,2):'',
    }};
  const connection=Form.useWatch('connection',form)??initial.connection;
  const provider=Form.useWatch('provider',form)??initial.provider;
  const fluxEnabled=Form.useWatch('flux_enabled',form)??initial.flux_enabled;
  const adapter=adapters.find(item=>item.id===provider);
  const [useEnv,setUseEnv]=useState(Boolean(profile?.api_key_env));
  const directCloud=connection==='cloud'&&!useEnv;
  const fields=useEnv&&adapter.legacy_defaults?adapter.legacy_defaults:adapter.defaults;
  const [review,setReview]=useState(null);
  const [saving,setSaving]=useState(false);
  const [saveError,setSaveError]=useState(null);
  const editing=Boolean(profile);

  function changeAdapter(changed){
    if(!changed.connection&&!changed.provider)return;
    const next=adapters.find(item=>changed.connection
      ?item.connection===changed.connection:item.id===changed.provider);
    if(!next)return;
    form.resetFields(['model','api_key',...Object.keys(fieldLabels)]);
    setUseEnv(false);
    form.setFieldsValue({provider:next.id,...next.defaults});
  }

  async function save(){
    setSaving(true);
    setSaveError(null);
    try{
      await onSave(review,revision,directCloud?form.getFieldValue('api_key'):undefined);
    }catch(error){
      setSaveError(requestError(error));
    }finally{setSaving(false);}
  }

  return <Modal open width={620} className="model-profile-dialog"
    title={<SectionTitle icon={<ApiOutlined/>}
      title={editing?'Chỉnh sửa hồ sơ model':'Đăng ký model mới'}
      description={review?'Kiểm tra thông tin trước khi lưu vào AgentForge.':
        'Chọn cách kết nối, sau đó nhập model và cấu hình truy cập.'}/>}
    onCancel={saving?undefined:onCancel} closable={!saving} keyboard={!saving} mask={{closable:false}}
    footer={<Space wrap>
      <Button disabled={saving} onClick={review?()=>{setReview(null);setSaveError(null);}:onCancel}>
        {review?'Quay lại':'Hủy'}
      </Button>
      <Button type="primary" loading={saving} onClick={review?save:()=>form.submit()}>
        {review?'Xác nhận lưu':'Xem lại cấu hình'}
      </Button>
    </Space>}>
    <Form hidden={Boolean(review)} form={form} layout="vertical" initialValues={initial}
      requiredMark={false} onValuesChange={changeAdapter}
      onFinish={values=>setReview(profilePayload(values,{...adapter,defaults:fields}))}>
      <div className="model-dialog-grid">
        <Form.Item name="connection" label="Loại kết nối">
          <Radio.Group optionType="button" buttonStyle="solid" disabled={editing}
            options={connectionOptions.filter(option=>adapters.some(item=>item.connection===option.value))}/>
        </Form.Item>
        <Form.Item name="provider" label={connection==='local'?'Runtime':'Nhà cung cấp'}
          rules={[{required:true,message:'Chọn runtime hoặc nhà cung cấp.'}]}>
          <Select disabled={editing} options={adapters.filter(item=>item.connection===connection)
            .map(item=>({value:item.id,label:item.label}))}/>
        </Form.Item>
      </div>
      <p className="model-dialog-help">{adapter.description}</p>
      <Form.Item name="model" label={adapter.model_label}
        rules={[{required:true,max:160,pattern:/^[A-Za-z0-9][A-Za-z0-9._:/+-]*$/,
          message:'Nhập tên model hoặc mã checkpoint hợp lệ.'}]}>
        <Input placeholder={adapter.model_example}/>
      </Form.Item>
      <div className="model-dialog-divider"/>
      {connection==='cloud'&&<Button type="link" className="model-dialog-mode" onClick={()=>{
        form.setFieldsValue({...(useEnv?adapter.defaults:adapter.legacy_defaults),api_key:undefined});
        setUseEnv(!useEnv);
      }}>{useEnv?'Nhập trực tiếp':'Dùng biến môi trường'}</Button>}
      {Object.entries(fields).map(([key,example])=><Form.Item key={key} name={key}
        label={directCloud?'Endpoint Cloud':fieldLabels[key]}
        rules={[{required:true,message:'Hãy điền trường này.'},{validator:(_,value)=>{
          if(!value)return Promise.resolve();
          const port=Number(localUrl.exec(value)?.[2]);
          const valid=directCloud?/^https:\/\/[^\s@?#\\]+$/.test(value)
            :key==='base_url'?port>=1&&port<=65535:envName.test(value);
          const error=directCloud?'Nhập URL HTTPS hợp lệ.':key==='base_url'
            ?'Dùng địa chỉ HTTP loopback với cổng từ 1 đến 65535.':'Chỉ nhập tên biến môi trường hợp lệ.';
          return valid?Promise.resolve():Promise.reject(new Error(error));
        }}]}>
        <Input placeholder={directCloud?'https://api.example.com':example} spellCheck={false}/>
      </Form.Item>)}
      {directCloud&&<Form.Item name="api_key" label="API key" dependencies={['base_url']}
        extra={profile?.has_api_key?'Để trống để giữ API key đã lưu cho endpoint hiện tại.':'API key được mã hóa theo tài khoản Windows.'}
        rules={[({getFieldValue})=>({validator:(_,value)=>
          (value?/^[!-~]{1,4096}$/.test(value):profile?.has_api_key&&getFieldValue('base_url')===profile.base_url)
            ?Promise.resolve():Promise.reject(new Error('Nhập API key hợp lệ cho endpoint này.'))})]}>
        <Input.Password autoComplete="new-password"/>
      </Form.Item>}
      {provider==='comfyui'&&!adapter.flux_workflow_max_bytes&&
        <Alert type="warning" showIcon message="Backend đang chạy chưa hỗ trợ đăng ký workflow FLUX."/>}
      {provider==='comfyui'&&adapter.flux_workflow_max_bytes&&<>
        <Form.Item name="flux_enabled" label="Workflow FLUX GGUF" valuePropName="checked"><Switch/></Form.Item>
        {fluxEnabled&&<>
          <Form.Item name={['flux_settings','workflow']} label="Workflow API JSON" rules={[
            {required:true},{validator:(_,value)=>{
              try {
                const graph=JSON.parse(value);
                if(graph&&Object.values(graph).filter(node=>node?.class_type==='UnetLoaderGGUF').length===1) {
                  if(new TextEncoder().encode(JSON.stringify(graph)).length<=adapter.flux_workflow_max_bytes)
                    return Promise.resolve();
                  return Promise.reject(new Error('Workflow vượt giới hạn '+adapter.flux_workflow_max_bytes+' byte.'));
                }
              } catch { /* Show validation below. */ }
              return Promise.reject(new Error('Dán workflow FLUX ở định dạng ComfyUI API JSON.'));
            }},
           ]}><Input.TextArea rows={6} spellCheck={false}/></Form.Item>
          <div className="model-dialog-grid">
            {[
              ['max_resolution','Cạnh ảnh tối đa (px)',256,1536],
              ['max_steps','Số bước tối đa',1,20],
              ['timeout_seconds','Thời gian chờ (giây)',5,600],
            ].map(([key,label,min,max])=><Form.Item key={key} name={['flux_settings',key]} label={label}
              rules={[{required:true,type:'integer',min,max}]}><InputNumber min={min} max={max}/></Form.Item>)}
            <Form.Item name={['flux_settings','output_dir']} label="Thư mục con trong workspace"
              rules={[{required:true}]}><Input spellCheck={false}/></Form.Item>
          </div>
        </>}
      </>}
      <div className="model-dialog-divider"/>
      <Form.Item name="id" label="Mã hồ sơ"
        rules={[{required:true,pattern:/^[a-z][a-z0-9_]{2,39}$/,
          message:'Dùng 3–40 ký tự thường, số hoặc dấu gạch dưới. Bắt đầu bằng chữ.'},
        {validator:(_,value)=>editing||!profiles.some(item=>item.id===value)
          ?Promise.resolve():Promise.reject(new Error('Mã hồ sơ đã tồn tại. Hãy chọn mã khác.'))}]}>
        <Input disabled={editing} placeholder="model_van_ban" spellCheck={false}/>
      </Form.Item>
      <div className="model-dialog-toggle">
        <label htmlFor="model-profile-enabled">Bật hồ sơ</label>
        <Form.Item name="enabled" valuePropName="checked" noStyle>
          <Switch id="model-profile-enabled"/>
        </Form.Item>
      </div>
    </Form>
    {review&&<>
      <dl className="model-dialog-summary">
        <dt>Mã hồ sơ</dt><dd>{review.id}</dd>
        <dt>{connection==='local'?'Runtime':'Nhà cung cấp'}</dt><dd>{adapter.label}</dd>
        <dt>{adapter.model_label}</dt><dd>{review.model}</dd>
        {Object.keys(fields).map(key=><Fragment key={key}><dt>{directCloud?'Endpoint Cloud':fieldLabels[key]}</dt><dd>{review[key]}</dd></Fragment>)}
        {directCloud&&<><dt>API key</dt><dd>••••••••</dd></>}
        <dt>Trạng thái</dt><dd>{review.enabled?'Đã bật':'Đã tắt'}</dd>
        {review.flux&&<><dt>Workflow FLUX</dt><dd>{Object.keys(review.flux.workflow).length} node</dd>
          <dt>Giới hạn</dt><dd>{review.flux.max_resolution} px · {review.flux.max_steps} bước · {review.flux.timeout_seconds} giây</dd>
          <dt>Đầu ra</dt><dd>workspace/{review.flux.output_dir}</dd></>}
      </dl>
      <p className="model-dialog-help">Hồ sơ được lưu vào SQLite trên máy này. Lượt lưu chỉ cập nhật cấu hình.</p>
      {saveError&&<Alert showIcon type="error" message="Chưa lưu được hồ sơ" description={saveError}/>}
    </>}
  </Modal>;
}
