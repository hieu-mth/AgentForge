import {useState} from 'react';
import {Alert,Button,Card,Form,Input,Select,Space} from 'antd';
import {NumberField} from '../components/NumberField.jsx';
import {videoModes,durationBounds,productionMethodOptions,productionMethodLabels,cloudSecondsBounds} from './studioDuration.js';

const editorKey='agentforge.studio.video-brief.v1';
const briefDefaults={idea:'',durationMode:'auto',targetSeconds:12,ratio:'9:16',mode:'motion',routeStrategy:'assigned',cloudSeconds:0};
function savedBrief(){
  try {
    const saved=JSON.parse(localStorage.getItem(editorKey));
    return Object.fromEntries(Object.entries(briefDefaults).map(([key,value])=>[
      key,typeof saved?.[key]===typeof value?saved[key]:value,
    ]));
  } catch {
    return briefDefaults;
  }
}

export function StudioBriefForm({hub,pending,waiting,onCharacters,onSubmit}){
  const [form]=Form.useForm();
  const [initialBrief]=useState(savedBrief);
  const [saveFailed,setSaveFailed]=useState(false);
  const values=Form.useWatch([],form)??initialBrief;
  const moving=(Form.useWatch('mode',form)??initialBrief.mode)==='motion';
  const limit=hub.data?.production_options?.brief_limit;
  const characterCount=Array.from(values.idea??'').length;
  const manual=(Form.useWatch('durationMode',form)??initialBrief.durationMode)==='manual';
  const method=values.routeStrategy??'assigned';
  const methodOptions=productionMethodOptions(hub.data);
  const cloudBounds=cloudSecondsBounds(hub.data,method);
  const targetBounds=durationBounds(hub.data,moving?'motion':'still');
  const needsCloudBudget=['auto','hybrid','cloud'].includes(method);
  const methodUnavailable=moving&&!methodOptions.some(option=>option.value===method&&!option.disabled);
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
      {hub.error&&!moving&&<Alert type="warning" showIcon message="Chưa đọc được giới hạn sản xuất" action={<Button onClick={hub.reload}>Thử lại</Button>}/>}
      {saveFailed&&<Alert type="warning" showIcon message="Trình duyệt không lưu được nội dung để khôi phục khi tải lại."/>}
      <div className="draft-form-options">
        <Form.Item className="draft-video-mode" name="mode" label="Kiểu video" rules={[{required:true}]}>
          <Select options={Object.entries(videoModes).map(([value,label])=>({value,label}))}/>
        </Form.Item>
        {!moving&&<Form.Item name="ratio" label="Tỷ lệ khung hình">
          <Select options={['9:16','16:9'].map(value=>({value,label:value}))}/>
        </Form.Item>}
        <Button className="draft-submit" type="primary" htmlType="submit"
          loading={pending} disabled={waiting>0||!Number.isInteger(limit)||characterCount>limit||(manual&&!targetBounds)||(moving&&needsCloudBudget&&!cloudBounds)}>Tạo storyboard</Button>
      </div>
      {methodUnavailable&&<Alert style={{marginBlockStart:16}} type="warning" showIcon message="Phương pháp đang chọn không tương thích với model video." description="Mở phần phương pháp sản xuất và chọn tuyến khả dụng. Không cần đổi model để lập storyboard nếu chưa phân công video."/>}
      {moving&&<details className="draft-resource-details" open={methodUnavailable||undefined}>
        <summary>Phương pháp sản xuất · {productionMethodLabels[method]??'Chưa chọn'}</summary>
        <Space wrap align="start">
          <Form.Item name="routeStrategy" label="Phương pháp" rules={[{validator:(_,value)=>
            methodOptions.some(option=>option.value===value&&!option.disabled)?Promise.resolve():
              Promise.reject(new Error('Phương pháp chưa có model video tương thích. Kiểm tra Model AI.'))}]}>
            <Select style={{width:280,maxWidth:'100%'}} loading={hub.loading} options={methodOptions}/>
          </Form.Item>
          {needsCloudBudget&&<Form.Item name="cloudSeconds" label="Tối đa giây video cloud" rules={[{required:true,type:'integer',...cloudBounds}]}>
            <NumberField min={cloudBounds?.min} max={cloudBounds?.max} precision={0} suffix="giây"/>
          </Form.Item>}
        </Space>
        {hub.error&&<Alert type="warning" showIcon message="Chưa đọc được phương pháp sản xuất" action={<Button onClick={hub.reload}>Thử lại</Button>}/>}
        <p className="env-muted">Có thể lập storyboard theo model video đã đăng ký dù chưa cấp quyền tạo media hoặc FFmpeg. Khi duyệt mới kiểm tra đầy đủ quyền, cấu hình và công cụ. Cloud có thể tính phí cả phần clip bị cắt.</p>
      </details>}
      <details className="draft-resource-details">
        <summary>Thời lượng · {manual?(values.targetSeconds??'—')+' giây':'AI tự đề xuất'}</summary>
        <Space wrap align="start">
          <Form.Item name="durationMode" label="Cách chọn thời lượng" rules={[{required:true}]}>
            <Select style={{width:180}} options={[{value:'auto',label:'AI tự đề xuất'},{value:'manual',label:'Nhập thủ công'}]}/>
          </Form.Item>
          {manual&&<Form.Item name="targetSeconds" label="Thời lượng"
            rules={[{required:true,type:'integer',...targetBounds}]}>
            <NumberField min={targetBounds?.min} max={targetBounds?.max} precision={0} suffix="giây"/>
          </Form.Item>}
        </Space>
      </details>
    </Form>
    <p className="env-muted">AI đề xuất số cảnh. Studio tạo {moving?'video theo phương pháp đã chọn':'ảnh'} sau khi bạn duyệt storyboard.</p>
    </Card>
  );
}
