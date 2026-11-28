import {useState} from 'react';
import {Alert,Button,Card,Form,Input,Select,Space} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {useResource} from '../use_resource.jsx';
import {videoModes,durationBounds} from './studioDuration.js';

const editorKey='agentforge.studio.video-brief.v1';
const briefDefaults={idea:'',durationMode:'auto',targetSeconds:12,ratio:'9:16',mode:'motion',routeStrategy:'assigned',casting:'auto',characterIds:[]};
function savedBrief(){
  try {
    const saved=JSON.parse(localStorage.getItem(editorKey));
    const next=Object.fromEntries(Object.entries(briefDefaults).map(([key,value])=>[
      key,typeof saved?.[key]===typeof value?saved[key]:value,
    ]));
    if(!['assigned','auto'].includes(next.routeStrategy))next.routeStrategy='assigned';
    if(!['auto','manual','none'].includes(next.casting))next.casting='auto';
    if(!Array.isArray(next.characterIds))next.characterIds=[];
    return next;
  } catch {
    return briefDefaults;
  }
}

export function StudioBriefForm({hub,pending,waiting,onCharacters,onSubmit}){
  const [form]=Form.useForm();
  const [initialBrief]=useState(savedBrief);
  const [saveFailed,setSaveFailed]=useState(false);
  const characters=useResource('/api/characters');
  const values=Form.useWatch([],form)??initialBrief;
  const moving=(Form.useWatch('mode',form)??initialBrief.mode)==='motion';
  const casting=Form.useWatch('casting',form)??initialBrief.casting;
  const limit=hub.data?.production_options?.brief_limit;
  const characterCount=Array.from(values.idea??'').length;
  const manual=(Form.useWatch('durationMode',form)??initialBrief.durationMode)==='manual';
  const method=values.routeStrategy??'assigned';
  const ready=hub.data?.production_options?.methods?.find(option=>option.id===method)?.execution_ready;
  const targetBounds=durationBounds(hub.data,moving?'motion':'still');
  const activeCharacters=(characters.data?.characters??[]).filter(item=>!item.archived);
  function resetBrief(){
    form.setFieldsValue(briefDefaults);
    try {
      localStorage.removeItem(editorKey);
      setSaveFailed(false);
    } catch {
      setSaveFailed(true);
    }
  }
  return (
    <Card className="env-panel" title="Tạo video mới"
      extra={<Button onClick={onCharacters}>Thư viện nhân vật</Button>}>
    <Form form={form} layout="vertical" onFinish={values=>onSubmit(values,resetBrief)} initialValues={initialBrief}
      onValuesChange={(_,next)=>{
        try {
          localStorage.setItem(editorKey,JSON.stringify(next));
          setSaveFailed(false);
        } catch {
          setSaveFailed(true);
        }
      }}>
      <Form.Item className="draft-editor-field" label="Nội dung video" name="idea"
        rules={[{required:true,whitespace:true,message:'Nhập ý tưởng hoặc kịch bản video.'},
          {validator:(_,value)=>Number.isInteger(limit)&&Array.from(value??'').length<=limit?Promise.resolve():
            Promise.reject(new Error(Number.isInteger(limit)?'Nội dung vượt giới hạn '+limit.toLocaleString('vi-VN')+' ký tự.':'Chưa đọc được giới hạn nội dung.'))}]}
        extra={<span className="draft-editor-count">
          {characterCount.toLocaleString('vi-VN')} / {limit?.toLocaleString('vi-VN')??'—'} ký tự
        </span>}>
        <Input.TextArea autoSize={{minRows:7,maxRows:20}} spellCheck={false}
          placeholder="Mô tả ý tưởng hoặc nhập kịch bản bạn muốn AI thực hiện..."/>
      </Form.Item>
      {hub.error&&<Alert type="warning" showIcon message="Chưa đọc được giới hạn sản xuất" action={<Button onClick={hub.reload}>Thử lại</Button>}/>}
      {saveFailed&&<Alert type="warning" showIcon message="Trình duyệt không lưu được nội dung để khôi phục khi tải lại."/>}
      <Space wrap align="start" size="middle">
        <Form.Item name="casting" label="Nhân vật">
          <Select style={{width:240}} options={[
            {value:'auto',label:'AI tự chọn nhân vật'},
            {value:'manual',label:'Chọn từ thư viện'},
            {value:'none',label:'Không dùng nhân vật đã đăng ký'},
          ]}/>
        </Form.Item>
        <Form.Item name="durationMode" label="Thời lượng" rules={[{required:true}]}>
          <Select style={{width:180}} options={[{value:'auto',label:'AI tự xác định'},{value:'manual',label:'Nhập thủ công'}]}/>
        </Form.Item>
        {manual&&<Form.Item name="targetSeconds" label="Số giây mong muốn"
          rules={[{required:true,type:'integer',...targetBounds}]}>
          <NumberField min={targetBounds?.min} max={targetBounds?.max} precision={0} suffix="giây"/>
        </Form.Item>}
        {moving?<Form.Item label="Tỷ lệ khung hình"><span>16:9 · Ngang</span></Form.Item>:
          <Form.Item name="ratio" label="Tỷ lệ khung hình">
            <Select style={{width:160}} options={['9:16','16:9'].map(value=>({value,label:value}))}/>
          </Form.Item>}
      </Space>
      {casting==='manual'&&<Form.Item name="characterIds" label="Nhân vật từ thư viện"
        rules={[{validator:(_,ids)=>Array.isArray(ids)&&ids.length>=1&&ids.length<=2&&ids.every(id=>activeCharacters.some(item=>item.id===id))
          ?Promise.resolve():Promise.reject(new Error('Chọn 1–2 nhân vật đang hoạt động.'))}]}>
        <Select mode="multiple" maxCount={2} loading={characters.loading} placeholder="Chọn tối đa hai nhân vật"
          options={activeCharacters.map(item=>({value:item.id,label:item.name}))}
          notFoundContent={characters.error?'Không đọc được thư viện':'Chưa có nhân vật'}/>
      </Form.Item>}
      {casting==='manual'&&characters.error&&<Alert type="warning" showIcon message="Không đọc được thư viện nhân vật"
        action={<Button onClick={characters.reload}>Thử lại</Button>}/>}
      <details className="draft-resource-details">
        <summary>Tùy chọn nâng cao</summary>
        <Space wrap align="start">
          <Form.Item name="mode" label="Kiểu video" rules={[{required:true}]}>
            <Select style={{width:220}} options={Object.entries(videoModes).map(([value,label])=>({value,label}))}/>
          </Form.Item>
          {moving&&<Form.Item name="routeStrategy" label="Điều phối sản xuất">
            <Select style={{width:260}} options={[{value:'assigned',label:'Theo model đã phân công'},{value:'auto',label:'AI tự chọn model phù hợp'}]}/>
          </Form.Item>}
        </Space>
        <p className="env-muted">Model, quyền cloud và giới hạn lượt gọi được quản lý tại AI điều phối. Studio tự tính số giây cloud theo storyboard.</p>
      </details>
      {moving&&ready===false&&<p className="env-muted">Bạn vẫn có thể lập storyboard. Kiểm tra model và quyền sản xuất trước khi duyệt.</p>}
      <Space wrap style={{marginTop:12}}>
        <Button className="draft-submit" type="primary" htmlType="submit"
          loading={pending} disabled={waiting>0||!Number.isInteger(limit)||characterCount>limit||(manual&&!targetBounds)}>Tạo storyboard</Button>
        <span className="env-muted">AI lập kế hoạch; chỉ sinh media sau khi bạn duyệt storyboard.</span>
      </Space>
    </Form>
    </Card>
  );
}
