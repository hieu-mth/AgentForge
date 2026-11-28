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
  account_ref:'Mã tài khoản ChatGPT',
};
const localUrl=/^http:\/\/(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})\/?$/;
const envName=/^[A-Z_][A-Z0-9_]*$/;

const comparisonFields=['id','provider','model','enabled','base_url','base_url_env','api_key_env','motion_encoder','flux','comfy_image','comfy_video','account_ref'];
const comparisonData=profile=>Object.fromEntries(comparisonFields.filter(key=>key in profile)
  .map(key=>[key,profile[key]]));

export function ModelProfileDialog({adapters,profile,profiles,revision,onCancel,onSave,onPreview,onReload,onUseRevision,labels,onChatGPTAction}){
  const [form]=Form.useForm();
  const limitsPanel=useRef(null);
  const initialAdapter=adapters.find(item=>item.id===profile?.provider)??adapters[0];
  const imageWorkflow=profile?.comfy_image??profile?.flux;
  const initial={connection:initialAdapter.connection,provider:initialAdapter.id,
    enabled:true,...initialAdapter.defaults,...profile,
    comfy_video_json:profile?.comfy_video?JSON.stringify(profile.comfy_video,null,2):'',
    flux_enabled:Boolean(imageWorkflow),flux_settings:{
      max_resolution:1024,max_steps:4,timeout_seconds:180,output_dir:'visuals',
      ...imageWorkflow,workflow:imageWorkflow?JSON.stringify(imageWorkflow.workflow,null,2):'',
    }};
  const connection=Form.useWatch('connection',form)??initial.connection;
  const provider=Form.useWatch('provider',form)??initial.provider;
  const fluxEnabled=Form.useWatch('flux_enabled',form)??initial.flux_enabled;
  const accountRef=Form.useWatch('account_ref',form)??initial.account_ref;
  const [chatgpt,setChatgpt]=useState(null);
  const [chatgptError,setChatgptError]=useState(null);
  const currentChatGPT=chatgpt?.account_ref===accountRef?chatgpt:null;
  const catalogLoaded=Boolean(currentChatGPT?.models?.length);
  const catalogActionLabel=catalogLoaded?'Cập nhật danh sách model':'Lấy danh sách model';
  const adapter=adapters.find(item=>item.id===provider);
  const [useEnv,setUseEnv]=useState(Boolean(profile?.api_key_env));
  const directCloud=connection==='cloud'&&!useEnv&&provider!=='chatgpt';
  const fields=useEnv&&adapter.environment_defaults?adapter.environment_defaults:adapter.defaults;
  const [review,setReview]=useState(null);
  const [contracts,setContracts]=useState([]);
  const [saving,setSaving]=useState(false);
  const [oauthAction,setOauthAction]=useState(null);
  const oauthLock=useRef(false);
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
    if(Object.hasOwn(changed,'account_ref')){
      setChatgpt(null);
      setChatgptError(null);
      form.setFieldValue('model',undefined);
    }
    if(!changed.connection&&!changed.provider)return;
    const next=adapters.find(item=>changed.connection
      ?item.connection===changed.connection:item.id===changed.provider);
    if(!next)return;
    form.resetFields(['model','api_key',...Object.keys(fieldLabels)]);
    setUseEnv(false);
    setChatgpt(null);
    setChatgptError(null);
    form.setFieldsValue({provider:next.id,...next.defaults});
  }

  async function chatgptAction(ack){
    if(oauthLock.current)return;
    oauthLock.current=true;
    setOauthAction(ack);
    setSaving(true);
    setChatgptError(null);
    if(ack==='CHATGPT_STATUS')setChatgpt(null);
    try{
      const {account_ref}=await form.validateFields(['account_ref']);
      const result=await onChatGPTAction(ack,account_ref);
      if(result?.account_ref!==account_ref||typeof result.connected!=='boolean')
        throw new Error('Kết quả kiểm tra tài khoản không hợp lệ.');
      setChatgpt(result);
      if(ack==='DISCONNECT_CHATGPT'||!result.connected)
        form.setFieldValue('model',undefined);
    }catch(error){
      // An account action may have failed after changing local credentials.
      // Do not continue to present a possibly stale connected state or catalog.
      setChatgpt(null);
      setChatgptError(requestError(error));
    }finally{
      oauthLock.current=false;
      setOauthAction(null);
      setSaving(false);
    }
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
  return <Modal open centered width={620} className="model-profile-dialog"
    styles={{body:{maxHeight:'calc(100dvh - 180px)',overflowY:'auto'}}}
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
        <Form.Item name="provider" label={connection==='local'?'Runtime':'Chuẩn kết nối'}
          rules={[{required:true,message:'Chọn runtime hoặc chuẩn kết nối.'}]}>
          <Select disabled={editing} virtual={false} options={adapters.filter(item=>item.connection===connection)
            .map(item=>({value:item.id,label:item.label}))}/>
        </Form.Item>
      </div>
      <p className="model-dialog-help">{adapter.description}</p>
      {provider!=='chatgpt'&&<Form.Item name="model" label={adapter.model_label}
        rules={[{required:true,max:160,pattern:/^[A-Za-z0-9][A-Za-z0-9._:/+-]*$/,
          message:'Nhập tên model hoặc mã checkpoint hợp lệ.'}]}>
        <Input placeholder={adapter.model_example}/>
      </Form.Item>}
      <div className="model-dialog-divider"/>
      {connection==='cloud'&&provider!=='chatgpt'&&<Button type="link" className="model-dialog-mode" onClick={()=>{
        form.setFieldsValue({...(useEnv?adapter.defaults:adapter.environment_defaults),api_key:undefined});
        setUseEnv(!useEnv);
      }}>{useEnv?'Nhập trực tiếp':'Dùng biến môi trường'}</Button>}
      {Object.entries(fields).map(([key,example])=><Form.Item key={key} name={key}
        label={directCloud?'Endpoint Cloud':fieldLabels[key]}
        rules={[{required:true,message:'Hãy điền trường này.'},{validator:(_,value)=>{
          if(!value)return Promise.resolve();
          const port=Number(localUrl.exec(value)?.[2]);
          const valid=key==='account_ref'?/^[a-z][a-z0-9_]{2,39}$/.test(value):directCloud?/^https:\/\/[^\s@?#\\]+$/.test(value)
            :key==='base_url'?port>=1&&port<=65535:envName.test(value);
          const error=key==='account_ref'?'Mã tài khoản gồm 3–40 ký tự thường, số hoặc dấu gạch dưới.':directCloud?'Nhập URL HTTPS hợp lệ.':key==='base_url'
            ?'Dùng địa chỉ HTTP loopback với cổng từ 1 đến 65535.':'Chỉ nhập tên biến môi trường hợp lệ.';
          return valid?Promise.resolve():Promise.reject(new Error(error));
        }}]}>
        <Input placeholder={directCloud?'https://api.example.com':example} spellCheck={false}/>
      </Form.Item>)}
      {provider==='chatgpt'&&<>
        <Alert type={currentChatGPT?.connected?'success':'info'} showIcon message={currentChatGPT?.connected?'Đã kết nối tài khoản ChatGPT':currentChatGPT?'Chưa kết nối tài khoản ChatGPT':'Kết nối ChatGPT qua OAuth'} style={{marginBottom:12}}
          description={<div style={{display:'grid',gridTemplateColumns:'minmax(0, 1fr)',gap:8}}>
            {!currentChatGPT?.connected&&<p style={{margin:0}}>Liên kết mở trình duyệt OpenAI trên máy chạy AgentForge. Không nhập mật khẩu, cookie hoặc token tại đây.</p>}
            <Space wrap>
              {!currentChatGPT&&<Button key="check-account" type="primary" aria-label="Kiểm tra" disabled={saving} loading={oauthAction==='CHATGPT_STATUS'}
                onClick={()=>chatgptAction('CHATGPT_STATUS')}>Kiểm tra</Button>}
              {currentChatGPT?.connected===false&&<>
                <Button key="connect-account" type="primary" disabled={saving} loading={oauthAction==='CONNECT_CHATGPT'}
                  onClick={()=>chatgptAction('CONNECT_CHATGPT')}>Liên kết ChatGPT</Button>
                <Button key="recheck-account" type="text" aria-label="Kiểm tra lại" disabled={saving} onClick={()=>chatgptAction('CHATGPT_STATUS')}>Kiểm tra lại</Button>
              </>}
              {currentChatGPT?.connected&&<Button key="catalog" type={catalogLoaded?'default':'primary'}
                aria-label={catalogActionLabel} data-testid="chatgpt-catalog-action" disabled={saving}
                loading={oauthAction==='LIST_CHATGPT_MODELS'}
                onClick={()=>chatgptAction('LIST_CHATGPT_MODELS')}>{catalogActionLabel}</Button>}
              {currentChatGPT?.connected&&<Button key="disconnect-account" danger disabled={saving} loading={oauthAction==='DISCONNECT_CHATGPT'} onClick={()=>Modal.confirm({
                title:'Ngắt kết nối tài khoản ChatGPT?',
                content:'Phiên OAuth local sẽ bị xóa; các hồ sơ dùng tài khoản này cần kết nối lại để chạy.',
                onOk:()=>chatgptAction('DISCONNECT_CHATGPT'),
              })}>Ngắt kết nối</Button>}
            </Space>
            {currentChatGPT?.remote_revocation==='NOT_CONFIRMED'&&
              <p style={{margin:0}}>Đã ngắt kết nối local. Chưa xác nhận thu hồi quyền từ xa.</p>}
            {chatgptError&&<Alert type="error" showIcon message={chatgptError}/>}
            <a href="https://chatgpt.com/#settings/Usage" target="_blank" rel="noreferrer">Quản lý hạn mức ChatGPT</a>
          </div>}/>
        <Form.Item name="model" label="Model ChatGPT" rules={[{required:true,message:'Lấy danh sách rồi chọn model.'}]}>
          {currentChatGPT?.models?.length>0?<Select showSearch={false} autoComplete="off"
            placeholder="Chọn model ChatGPT"
            options={[
              ...(profile?.model&&!currentChatGPT?.models?.some(item=>item.slug===profile.model)&&profile.account_ref===accountRef
                ?[{value:profile.model,label:profile.model+' · Đã lưu'}]:[]),
              ...(currentChatGPT?.models||[]).map(item=>({value:item.slug,label:item.display_name||item.slug})),
            ]}/>:<Input className="model-dialog-locked-value" disabled readOnly placeholder={currentChatGPT?.connected?'Lấy danh sách model để chọn':'Kiểm tra kết nối trước'}/>}
        </Form.Item>
      </>}
      {directCloud&&<Form.Item name="api_key" label="API key" dependencies={['base_url']}
        extra={profile?.has_api_key?'Để trống để giữ API key đã lưu cho endpoint hiện tại.':'API key được mã hóa theo tài khoản Windows.'}
        rules={[({getFieldValue})=>({validator:(_,value)=>
          (value?/^[!-~]{1,4096}$/.test(value):profile?.has_api_key&&getFieldValue('base_url')===profile.base_url)
            ?Promise.resolve():Promise.reject(new Error('Nhập API key hợp lệ cho endpoint này.'))})]}>
        <Input.Password autoComplete="new-password"/>
      </Form.Item>}
      {provider==='comfyui'&&!adapter.flux_workflow_max_bytes&&
        <Alert type="warning" showIcon message="Backend đang chạy chưa hỗ trợ đăng ký workflow ảnh."/>}
      {provider==='comfyui'&&adapter.flux_workflow_max_bytes&&<>
        <Form.Item name="flux_enabled" label="Workflow tạo ảnh ComfyUI" valuePropName="checked"><Switch/></Form.Item>
        {!fluxEnabled&&adapter.motion_encoder_supported&&
          <Form.Item name="motion_encoder" label="Đường dẫn tuyệt đối tới encoder video">
            <Input placeholder="t5xxl_fp8_e4m3fn.safetensors" spellCheck={false}/>
          </Form.Item>}
        {!fluxEnabled&&adapter.video_workflow_max_bytes&&
          <Form.Item name="comfy_video_json" label="Workflow I2V có cấu hình (JSON)"
            extra="Để trống nếu dùng preset LTX cũ. Backend kiểm tra graph, SHA-256 weights và giới hạn tài nguyên."
            rules={[{validator:(_,value)=>{
              if(!value?.trim())return Promise.resolve();
              try {
                const graph=JSON.parse(value);
                if(graph&&typeof graph==='object'&&!Array.isArray(graph)&&
                    new TextEncoder().encode(JSON.stringify(graph)).length<=adapter.video_workflow_max_bytes)
                  return Promise.resolve();
              }catch{ /* Backend validates the complete graph. */ }
              return Promise.reject(new Error('Workflow video JSON không hợp lệ hoặc vượt giới hạn.'));
            }}]}><Input.TextArea rows={6} spellCheck={false}/></Form.Item>}
        {fluxEnabled&&<>
          <Form.Item name={['flux_settings','workflow']} label="Workflow API JSON" rules={[
            {required:true},{validator:(_,value)=>{
              try {
                const graph=JSON.parse(value);
                if(graph&&typeof graph==='object'&&!Array.isArray(graph)&&Object.keys(graph).length>0) {
                  if(new TextEncoder().encode(JSON.stringify(graph)).length<=adapter.flux_workflow_max_bytes)
                    return Promise.resolve();
                  return Promise.reject(new Error('Workflow vượt giới hạn '+adapter.flux_workflow_max_bytes+' byte.'));
                }
              } catch { /* Show validation below. */ }
              return Promise.reject(new Error('Dán workflow ảnh ở định dạng ComfyUI API JSON.'));
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
        <dt>{connection==='local'?'Runtime':'Chuẩn kết nối'}</dt><dd>{adapter.label}</dd>
        <dt>{adapter.model_label}</dt><dd>{review.model}</dd>
        {Object.keys(fields).map(key=><Fragment key={key}><dt>{directCloud?'Endpoint Cloud':fieldLabels[key]}</dt><dd>{review[key]}</dd></Fragment>)}
        {directCloud&&<><dt>API key</dt><dd>••••••••</dd></>}
        <dt>Trạng thái</dt><dd>{review.enabled?'Đã bật':'Đã tắt'}</dd>
        {(review.comfy_image??review.flux)&&<><dt>Workflow ảnh</dt><dd>{Object.keys((review.comfy_image??review.flux).workflow).length} node</dd>
          <dt>Giới hạn</dt><dd>{(review.comfy_image??review.flux).max_resolution} px · {(review.comfy_image??review.flux).max_steps} bước · {(review.comfy_image??review.flux).timeout_seconds} giây</dd>
          <dt>Đầu ra</dt><dd>workspace/{(review.comfy_image??review.flux).output_dir}</dd></>}
      </dl>
      {supported.length?<ul className="model-contract-list">{supported.map(item=><li key={item.capability}>
        <strong>{labels[item.capability]??item.capability}</strong>
        {item.capability==='film.motion'&&review.motion_encoder&&<div>{review.comfy_video?'Workflow I2V đã cấu hình':'Preset LTX cũ'}</div>}
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
