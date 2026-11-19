import {Fragment,useState} from 'react';
import {Alert,Button,Form,Input,Modal,Radio,Select,Space,Switch} from 'antd';
import {ApiOutlined,CloudOutlined,DesktopOutlined} from '@ant-design/icons';
import {SectionTitle} from '../components/settings.jsx';
import {profilePayload} from '../model_hub_ui.js';

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
    enabled:true,...initialAdapter.defaults,...profile};
  const connection=Form.useWatch('connection',form)??initial.connection;
  const provider=Form.useWatch('provider',form)??initial.provider;
  const adapter=adapters.find(item=>item.id===provider);
  const [review,setReview]=useState(null);
  const [saving,setSaving]=useState(false);
  const [failed,setFailed]=useState(false);
  const editing=Boolean(profile);

  function changeAdapter(changed){
    if(!changed.connection&&!changed.provider)return;
    const next=adapters.find(item=>changed.connection
      ?item.connection===changed.connection:item.id===changed.provider);
    if(!next)return;
    form.resetFields(['model',...Object.keys(fieldLabels)]);
    form.setFieldsValue({provider:next.id,...next.defaults});
  }

  async function save(){
    setSaving(true);
    setFailed(false);
    try{
      if(!await onSave(review,revision))setFailed(true);
    }finally{setSaving(false);}
  }

  return <Modal open width={620} className="model-profile-dialog"
    title={<SectionTitle icon={<ApiOutlined/>}
      title={editing?'Chỉnh sửa hồ sơ model':'Đăng ký model mới'}
      description={review?'Kiểm tra thông tin trước khi lưu vào AgentForge.':
        'Chọn cách kết nối, sau đó nhập model và cấu hình truy cập.'}/>}
    onCancel={saving?undefined:onCancel} closable={!saving} keyboard={!saving} mask={{closable:false}}
    footer={<Space wrap>
      <Button disabled={saving} onClick={review?()=>{setReview(null);setFailed(false);}:onCancel}>
        {review?'Quay lại':'Hủy'}
      </Button>
      <Button type="primary" loading={saving} onClick={review?save:()=>form.submit()}>
        {review?'Xác nhận lưu':'Xem lại cấu hình'}
      </Button>
    </Space>}>
    <Form hidden={Boolean(review)} form={form} layout="vertical" initialValues={initial}
      requiredMark={false} onValuesChange={changeAdapter} onFinish={values=>setReview(profilePayload(values,adapter))}>
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
      {Object.entries(adapter.defaults).map(([key,example])=><Form.Item key={key} name={key}
        label={fieldLabels[key]}
        rules={[{required:true,message:'Hãy điền trường này.'},{validator:(_,value)=>{
          if(!value)return Promise.resolve();
          const port=Number(localUrl.exec(value)?.[2]);
          const valid=key==='base_url'?port>=1&&port<=65535:envName.test(value);
          return valid?Promise.resolve():Promise.reject(new Error(key==='base_url'
            ?'Dùng địa chỉ HTTP loopback với cổng từ 1 đến 65535.':'Chỉ nhập tên biến môi trường hợp lệ.'));
        }}]}>
        <Input placeholder={example} spellCheck={false}/>
      </Form.Item>)}
      {connection==='cloud'&&<p className="model-dialog-help">Nhập tên biến đã thiết lập trên máy chạy AgentForge. Giá trị API key nằm trong môi trường của tiến trình.</p>}
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
        {Object.keys(adapter.defaults).map(key=><Fragment key={key}><dt>{fieldLabels[key]}</dt><dd>{review[key]}</dd></Fragment>)}
        <dt>Trạng thái</dt><dd>{review.enabled?'Đã bật':'Đã tắt'}</dd>
      </dl>
      <p className="model-dialog-help">Hồ sơ được lưu vào SQLite trên máy này. Lượt lưu chỉ cập nhật cấu hình.</p>
      {failed&&<Alert showIcon type="error" message="Chưa lưu được hồ sơ"
        description="Đóng dialog rồi làm mới danh sách nếu cấu hình đã thay đổi ở phiên khác."/>}
    </>}
  </Modal>;
}
