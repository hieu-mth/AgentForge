import {Fragment,useRef,useState} from 'react';
import {Alert,Button,Form,Input,Modal,Radio,Select,Space,Switch} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {ApiOutlined,CloudOutlined,DesktopOutlined} from '@ant-design/icons';
import {SectionTitle} from '../components/settings.jsx';
import {outputSummary,profilePayload,readinessReason} from '../model_hub_ui.js';
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

const comparisonFields=['id','provider','model','enabled','base_url','base_url_env','api_key_env','motion_encoder','flux'];
const comparisonData=profile=>Object.fromEntries(comparisonFields.filter(key=>key in profile)
  .map(key=>[key,profile[key]]));

export function ModelProfileDialog({adapters,profile,profiles,revision,onCancel,onSave,onPreview,onReload,onUseRevision,labels}){
  const [form]=Form.useForm();
  const limitsPanel=useRef(null);
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
  const [contracts,setContracts]=useState([]);
  const [saving,setSaving]=useState(false);
  const [saveError,setSaveError]=useState(null);
  const [conflict,setConflict]=useState(false);
  const [comparison,setComparison]=useState(null);
  const editing=Boolean(profile);
  const captureError=error=>{
    const stale=['MODEL_HUB_REVISION_CONFLICT','MODEL_HUB_PROFILE_ALREADY_EXISTS',
      'MODEL_HUB_PROFILE_REMOVED'].includes(error.message);
    setConflict(stale);
    setComparison(null);
    setSaveError(stale?null:requestError(error));
  };

  function changeAdapter(changed){
    if(!changed.connection&&!changed.provider)return;
    const next=adapters.find(item=>changed.connection
      ?item.connection===changed.connection:item.id===changed.provider);
    if(!next)return;
    form.resetFields(['model','api_key',...Object.keys(fieldLabels)]);
    setUseEnv(false);
    form.setFieldsValue({provider:next.id,...next.defaults});
  }

  async function save(checkAfterSave=false){
    setSaving(true);
    setSaveError(null);
    try{
      await onSave(review,revision,directCloud?form.getFieldValue('api_key'):undefined,checkAfterSave);
    }catch(error){
      captureError(error);
    }finally{setSaving(false);}
  }

  async function preview(values){
    setSaving(true);
    setSaveError(null);
    try {
      const candidate=profilePayload(values,{...adapter,defaults:fields});
      const result=await onPreview(candidate,revision);
      setContracts(result.capability_contracts);
      setReview(candidate);
    }catch(error){
      captureError(error);
    }finally{setSaving(false);}
  }

  async function reloadRevision(){
    setSaving(true);
    try{
      const draft=review??profilePayload(form.getFieldsValue(),{...adapter,defaults:fields});
      const current=await onReload(draft.id);
      setComparison({...current,draft});
      setSaveError(null);
      setConflict(false);
    }catch(error){setSaveError(requestError(error));}
    finally{setSaving(false);}
  }

  function useLatestRevision(){
    onUseRevision(comparison.revision);
    setReview(null);
    setContracts([]);
    setComparison(null);
    setConflict(false);
    setSaveError(null);
  }

  const supported=contracts.filter(item=>item.runtime_compatible||item.route_configurable);
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
      {review&&connection==='local'&&review.enabled&&supported.some(item=>item.local_runtime_compatible)&&
        <Button disabled={saving||conflict} onClick={()=>save(true)}>Lưu và kiểm tra</Button>}
      <Button type="primary" loading={saving} disabled={conflict} onClick={review?()=>save():()=>form.submit()}>
        {review?'Xác nhận lưu':'Xem lại cấu hình'}
      </Button>
    </Space>}>
    <Form hidden={Boolean(review)} form={form} layout="vertical" initialValues={initial} disabled={saving||conflict}
      requiredMark={false} onValuesChange={changeAdapter}
      onFinishFailed={({errorFields})=>{
        if(limitsPanel.current&&errorFields.some(({name})=>name[0]==='flux_settings'&&name[1]!=='workflow'))
          limitsPanel.current.open=true;
      }}
      onFinish={preview}>
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
        {!fluxEnabled&&adapter.motion_encoder_supported&&
          <Form.Item name="motion_encoder" label="Đường dẫn tuyệt đối tới encoder LTX">
            <Input placeholder="t5xxl_fp8_e4m3fn.safetensors" spellCheck={false}/>
          </Form.Item>}
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
          <details ref={limitsPanel} className="model-workflow-details"><summary>Giới hạn và thư mục đầu ra</summary>
          <div className="model-dialog-grid">
            {[
              ['max_resolution','Cạnh ảnh tối đa (px)',256,1536],
              ['max_steps','Số bước tối đa',1,20],
              ['timeout_seconds','Thời gian chờ (giây)',5,600],
            ].map(([key,label,min,max])=><Form.Item key={key} name={['flux_settings',key]} label={label}
              rules={[{required:true,type:'integer',min,max}]}><NumberField min={min} max={max}/></Form.Item>)}
            <Form.Item name={['flux_settings','output_dir']} label="Thư mục con trong workspace"
              rules={[{required:true}]}><Input spellCheck={false}/></Form.Item>
          </div></details>
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
      {supported.length?<ul className="model-contract-list">{supported.map(item=><li key={item.capability}>
        <strong>{labels[item.capability]??item.capability}</strong>
        {item.capability==='film.motion'&&review.motion_encoder&&<div>Preset LTX cố định</div>}
        <div>{outputSummary(item.output_limits)??readinessReason(item.reason)}</div>
        {item.workflow_sha256&&<details className="model-workflow-details"><summary>Workflow SHA-256</summary>
          <code>{item.workflow_sha256}</code></details>}
      </li>)}</ul>:<Alert showIcon type="warning" message="Chưa có capability tương thích"
        description={review.provider==='comfyui'
          ?readinessReason(contracts.find(item=>item.capability===(review.motion_encoder?'film.motion':'image.generate'))?.reason)
          :undefined}/>}
      <p className="model-dialog-help">Hồ sơ được lưu vào SQLite trên máy này. Lượt lưu chỉ cập nhật cấu hình.</p>
    </>}
    {(saveError||conflict)&&<Alert className="model-dialog-error" showIcon type="error"
      message={review?'Chưa lưu được hồ sơ':'Chưa kiểm tra được cấu hình'}
      description={saveError??'Cấu hình đã thay đổi ở phiên khác. Tải lại để đối chiếu. Nội dung bạn đã nhập vẫn được giữ.'}
      action={conflict&&<Button size="small" loading={saving} onClick={reloadRevision}>Tải lại cấu hình</Button>}/>}
    {comparison&&<section className="model-conflict" aria-label="Đối chiếu hồ sơ model">
      <div className="model-conflict-grid">
        <div><strong>Bản nháp của bạn</strong><pre>{JSON.stringify(comparisonData(comparison.draft),null,2)}</pre></div>
        <div><strong>Bản trên máy chủ · Phiên bản {comparison.revision}</strong>
          {comparison.profile
            ?<pre>{JSON.stringify(comparisonData(comparison.profile),null,2)}</pre>
            :<p>Phiên bản này chưa có hồ sơ mang mã {comparison.draft.id}.</p>}</div>
      </div>
      {editing&&!comparison.profile
        ?<Alert type="warning" message="Hồ sơ đã bị xóa. Hãy đăng ký hồ sơ mới nếu muốn sử dụng lại cấu hình này."/>
        :<Button onClick={useLatestRevision} disabled={saving}>
          {!editing&&comparison.profile?'Đổi mã hồ sơ':'Dùng phiên bản này để tiếp tục'}
        </Button>}
      {!editing&&comparison.profile&&<p>Mã hồ sơ đã được sử dụng. Hãy nhập mã khác trước khi lưu.</p>}
    </section>}
  </Modal>;
}
