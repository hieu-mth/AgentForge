import { useState } from 'react';
import { Alert, Button, Card, Col, Collapse, Empty, Form, Image, Input, Modal, Popconfirm, Row, Space, Tag, Typography } from 'antd';
import { useResource, ResourceStatus } from '../use_resource.jsx';

const { Text, Paragraph } = Typography;
const ROLES = [
  ['primary','Chính diện / chân dung','Khuôn mặt và dấu hiệu nhận diện rõ'],
  ['full_body','Toàn thân','Tỷ lệ cơ thể, dáng đứng tự nhiên'],
  ['alternate','Góc 3/4','Thấy rõ mặt và chiều sâu'],
  ['left','Bên trái','Thấy đặc điểm phía trái'],
  ['right','Bên phải','Thấy đặc điểm phía phải'],
  ['rear','Phía sau','Lưng, đuôi, hoa văn'],
  ['sheet','Bản thiết kế tổng hợp','Ảnh đa góc do Owner duyệt; có thể tạo bằng AI'],
];
const FIELDS = [
  ['name','Tên nhân vật',100],['species','Loài / kiểu nhân vật',80],
  ['appearance','Đặc điểm nhận diện cố định',2000],['personality','Tính cách / vai trò',2000],
  ['voice','Giọng nói / phong cách kể chuyện',300],['model_ref','Model / LoRA tham chiếu (nếu có)',200],
  ['reference_notes','Nguồn ảnh, ghi chú bản thiết kế',2000],
];
const MAX_FILE = 1024*1024;
const MAX_SOURCE = 20*1024*1024;
const readURL = file => new Promise((resolve,reject)=>{
  const reader=new FileReader();
  reader.onload=()=>resolve(String(reader.result));
  reader.onerror=()=>reject(new Error('Không đọc được ảnh.'));
  reader.readAsDataURL(file);
});
const decodeImage = src => new Promise((resolve,reject)=>{
  const image=new window.Image();
  image.onload=()=>resolve(image);
  image.onerror=()=>reject(new Error('Ảnh không hợp lệ.'));
  image.src=src;
});
async function normalizeImage(file){
  if(!['image/png','image/jpeg'].includes(file.type)||file.size>MAX_SOURCE)
    throw new Error('Chọn PNG/JPEG tối đa 20 MiB.');
  const src=await readURL(file);
  const image=await decodeImage(src);
  if(file.size<=MAX_FILE&&image.width*image.height<=12000000)return src;
  const canvas=document.createElement('canvas');
  const scale=Math.min(1,2048/Math.max(image.width,image.height));
  canvas.width=Math.max(1,Math.round(image.width*scale));
  canvas.height=Math.max(1,Math.round(image.height*scale));
  const ctx=canvas.getContext('2d');
  if(!ctx)throw new Error('Không thể chuẩn hóa ảnh.');
  ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(image,0,0,canvas.width,canvas.height);
  for(const quality of [0.9,0.8,0.65,0.5]){
    const result=canvas.toDataURL('image/jpeg',quality);
    if(result.split(',')[1].length<=4*Math.floor(MAX_FILE/3))return result;
  }
  throw new Error('Ảnh vẫn quá lớn sau khi chuẩn hóa. Hãy chọn ảnh khác.');
}
function field([key,label,max]){
  return <Form.Item key={key} name={key} label={label} rules={key==='name'?[{required:true,whitespace:true,message:'Nhập tên nhân vật'}]:[]}>
    {max>300?<Input.TextArea rows={3} maxLength={max} showCount/>:<Input maxLength={max}/>}
  </Form.Item>;
}

export function CharacterLibrary({mutate,onNavigate}) {
  const registry=useResource('/api/characters');
  const [editing,setEditing]=useState(null);
  const [archived,setArchived]=useState(false);
  const [busy,setBusy]=useState(false);
  const all=registry.data?.characters||[];
  const active=all.filter(item=>!item.archived);
  const items=all.filter(item=>Boolean(item.archived)===archived);
  async function archive(item){
    setBusy(true);
    try{
      const result=await mutate('/api/characters/archive',{ack:'SET_CHARACTER_ARCHIVED',character_id:item.id,
        expected_version:item.version,archived:!item.archived});
      if(result)await registry.reload();
    }finally{setBusy(false);}
  }
  return <Space direction="vertical" size="large" style={{width:'100%'}}>
    <Alert type="info" showIcon message="Thư viện nhân vật · ảnh nhận diện"
      description="Lưu ảnh gốc, góc nhìn và bản thiết kế đã duyệt trên máy. Chưa tự gửi ảnh cho model hoặc bảo đảm giữ ngoại hình khi tạo video."/>
    <Card title={'Nhân vật của tôi · '+active.length} extra={<Space wrap>
      <Button onClick={()=>setArchived(!archived)}>{archived?'Đang xem lưu trữ · về thư viện':'Đã lưu trữ ('+(all.length-active.length)+')'}</Button>
      <Button onClick={registry.reload} loading={registry.loading}>Làm mới</Button>
      <Button type="primary" onClick={()=>setEditing({})}>Tạo nhân vật</Button>
    </Space>}>
      <ResourceStatus resource={registry} label="danh sách nhân vật"/>
      {!items.length&&!registry.loading&&!registry.error&&<Empty description={archived?'Chưa có nhân vật lưu trữ':'Chưa có nhân vật'}/>}
      <Row gutter={[16,16]}>{items.map(item=>{
        const pack=item.reference_pack;
        return <Col key={item.id} xs={24} sm={12} lg={8} xl={6}><Card size="small"
          cover={pack?.preview_url?<Image alt={'Ảnh nhận diện '+item.name} src={pack.preview_url} height={180}
            style={{objectFit:'contain',background:'rgba(128,128,128,.08)'}}/>:
            <div style={{height:180,display:'grid',placeItems:'center',background:'rgba(128,128,128,.08)'}}><Text type="secondary">Chưa có ảnh</Text></div>}>
          <Space direction="vertical" style={{width:'100%'}}>
            <Text strong>{item.name}</Text>
            <Text type="secondary">{item.species||'Chưa phân loại'}</Text>
            <Paragraph ellipsis={{rows:2}} style={{margin:0,minHeight:42}}>{item.appearance||'Chưa có mô tả nhận diện'}</Paragraph>
            <Space wrap><Tag>{pack?pack.roles.length+'/'+ROLES.length+' ảnh · v'+pack.revision:'Chưa có bộ ảnh'}</Tag>
              {pack?.roles.includes('sheet')&&<Tag color="success">Có bản thiết kế</Tag>}</Space>
            <Space wrap>
              {!item.archived&&<Button onClick={()=>setEditing(item)}>Xem / Sửa</Button>}
              <Popconfirm title={item.archived?'Khôi phục nhân vật?':'Lưu trữ nhân vật?'}
                description={item.archived?'Nhân vật sẽ trở lại danh sách casting.':'Ẩn khỏi casting mới, giữ ảnh và dữ liệu cũ.'}
                onConfirm={()=>archive(item)} okText="Xác nhận" cancelText="Hủy">
                <Button loading={busy}>{item.archived?'Khôi phục':'Lưu trữ'}</Button>
              </Popconfirm>
            </Space>
          </Space>
        </Card></Col>;
      })}</Row>
    </Card>
    <Button onClick={()=>onNavigate('media-studio')}>Mở Studio video</Button>
    {editing&&(editing.id?<ExistingEditor key={editing.id} character={editing} mutate={mutate}
      onClose={()=>setEditing(null)} onSaved={async()=>{setEditing(null);await registry.reload();}}/>:
      <CharacterEditor character={editing} mutate={mutate} onClose={()=>setEditing(null)}
        onSaved={async()=>{setEditing(null);await registry.reload();}}/>)}
  </Space>;
}

function ExistingEditor(props){
  const resource=useResource('/api/characters/'+props.character.id+'/references');
  if(!resource.data||resource.loading||resource.error)return <Modal open title="Đọc hồ sơ nhân vật"
    footer={null} onCancel={props.onClose}><ResourceStatus resource={resource} label="bộ ảnh nhận diện"/></Modal>;
  return <CharacterEditor {...props} resource={resource.data}/>;
}
function CharacterEditor({character,resource,mutate,onClose,onSaved}){
  const [form]=Form.useForm();
  const [files,setFiles]=useState({});
  const [removed,setRemoved]=useState([]);
  const [processing,setProcessing]=useState(false);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState(null);
  const [sheetPrompt,setSheetPrompt]=useState('');
  const latest=resource?.packs?.[0];
  const previous=Object.fromEntries((latest?.images||[]).map(item=>[item.role,item]));
  const existing=role=>!removed.includes(role)&&previous[role];
  const has=role=>Boolean(files[role]||existing(role));
  const changed=Object.keys(files).length>0||removed.length>0;
  const busy=processing||saving;
  async function choose(role,file){
    if(!file)return;
    setProcessing(true);setError(null);
    try{
      const src=await normalizeImage(file);
      setFiles(old=>({...old,[role]:src}));
      setRemoved(old=>old.filter(value=>value!==role));
    }catch(e){setError(e.message||'Không nhập được ảnh.');}
    finally{setProcessing(false);}
  }
  function remove(role){
    setFiles(old=>Object.fromEntries(Object.entries(old).filter(([key])=>key!==role)));
    if(previous[role])setRemoved(old=>[...new Set([...old,role])]);
  }
  async function save(values){
    if(busy)return;
    if(changed&&!has('primary')){setError('Cần ảnh chính để lưu bộ nhận diện.');return;}
    setSaving(true);setError(null);
    try{
      const data={ack:'SAVE_CHARACTER',character:{...values}};
      if(character.id)Object.assign(data.character,{id:character.id,expected_version:resource.character_version});
      if(changed)data.pack={expected_revision:resource?.latest_revision||0,
        images:Object.entries(files).map(([role,src])=>({role,data_base64:src.split(',')[1]})),
        keep_roles:ROLES.map(([role])=>role).filter(role=>!files[role]&&existing(role))};
      const result=await mutate('/api/characters/save',data);
      if(result?.character)await onSaved();
      else setError('Chưa lưu được hồ sơ. Hãy kiểm tra thông báo hoặc tải lại hồ sơ nếu đã bị thay đổi.');
    }finally{setSaving(false);}
  }
  function buildPrompt(){
    const values=form.getFieldsValue(true);
    setSheetPrompt('Create a clean character turnaround reference sheet for ONE subject: '+(values.name||'[name]')+
      '. Species/type: '+(values.species||'[type]')+'. Fixed identity: '+(values.appearance||'[describe identity]')+
      '. Use the attached real reference photos as the source of truth. Show front, three-quarter, left profile, right profile and rear full-body views, same scale, neutral pose, plain background, neutral lighting. Preserve face, proportions, markings, colors and distinctive features exactly. Do not add accessories or invent unseen markings. Keep each view separate and clearly labeled. The result is a design reference, not a scene. Also provide separate single-view images if supported. Owner must verify against the original photos.');
  }
  return <Modal open width={840} title={character.id?'Chỉnh sửa nhân vật':'Tạo nhân vật'} footer={null}
    onCancel={()=>{if(!busy)onClose();}} closable={!busy} maskClosable={!busy}>
    <Form form={form} layout="vertical" onFinish={save}
      initialValues={Object.fromEntries(FIELDS.map(([key])=>[key,character[key]||'']))}>
      <Space direction="vertical" size="middle" style={{width:'100%'}}>
        <div><Text strong>1. Bộ ảnh nhận diện</Text><Paragraph type="secondary" style={{margin:0}}>
          Ảnh chính là nền tảng; các góc khác tùy chọn. PNG/JPEG tối đa 20 MiB đầu vào, tự giảm xuống tối đa 1 MiB khi cần. Giữ ảnh gốc riêng.
        </Paragraph></div>
        <Row gutter={[12,12]}>{ROLES.map(([role,label,hint])=>{
          const src=files[role]||existing(role)?.preview_url;
          return <Col key={role} xs={12} sm={8} md={6}><Card size="small">
            <Space direction="vertical" style={{width:'100%'}}>
              <Text strong>{label}</Text>
              {src?<Image alt={label} src={src} width="100%" height={100} style={{objectFit:'contain'}}/>:
                <div style={{height:100,display:'grid',placeItems:'center',background:'rgba(128,128,128,.08)'}}><Text type="secondary">Chưa có ảnh</Text></div>}
              <Text type="secondary" style={{fontSize:12}}>{hint}</Text>
              <input aria-label={'Nhập ảnh '+label} type="file" accept="image/png,image/jpeg" disabled={busy}
                style={{width:'100%'}} onChange={event=>{const file=event.target.files?.[0];event.target.value='';void choose(role,file);}}/>
              {src&&<Button size="small" disabled={busy} onClick={()=>remove(role)}>Bỏ ảnh</Button>}
            </Space>
          </Card></Col>;
        })}</Row>
        <Alert type="info" showIcon message="Ảnh đa góc là tài sản tham chiếu, không phải model 3D hoặc LoRA."
          description="Dùng ảnh thật làm chuẩn. Nếu tạo sheet bằng AI, hãy kiểm tra từng góc; model video có thể cần ảnh riêng thay vì ảnh tổng hợp."/>
        <div><Text strong>2. Thông tin nhân vật</Text></div>
        <Row gutter={12}><Col xs={24} sm={12}>{field(FIELDS[0])}</Col><Col xs={24} sm={12}>{field(FIELDS[1])}</Col></Row>
        {FIELDS.slice(2,4).map(field)}
        <Collapse items={[{key:'sheet',label:'Chuẩn bị bản thiết kế bằng AI (tùy chọn)',children:<Space direction="vertical" style={{width:'100%'}}>
          <Paragraph>Đính kèm ảnh gốc vào công cụ tạo ảnh hỗ trợ tham chiếu. Dùng prompt dưới đây, kiểm tra kết quả rồi nhập sheet và từng góc vào hồ sơ. AgentForge không tự gọi API.</Paragraph>
          <Button onClick={buildPrompt}>Tạo prompt bản thiết kế</Button>
          {sheetPrompt&&<Input.TextArea value={sheetPrompt} readOnly autoSize={{minRows:4,maxRows:12}}/>}
        </Space>},{key:'advanced',label:'Thiết lập nâng cao',forceRender:true,children:<>{FIELDS.slice(4).map(field)}</>},
        ...(resource?.packs?.length?[{key:'history',label:'Lịch sử bộ ảnh ('+resource.packs.length+')',children:<Space direction="vertical">
          {resource.packs.map(pack=><details key={pack.revision}><summary>Phiên bản {pack.revision} · hồ sơ v{pack.character_version}</summary>
            <Space wrap>{pack.images.map(item=><Image key={item.role} width={80} src={item.preview_url}
              alt={ROLES.find(([role])=>role===item.role)?.[1]||item.role}/>)}</Space></details>)}
        </Space>}]:[])]}/>
        {error&&<Alert type="error" showIcon message={error}/>}
        <Button type="primary" block htmlType="submit" loading={saving} disabled={processing}>Lưu nhân vật</Button>
      </Space>
    </Form>
  </Modal>;
}
