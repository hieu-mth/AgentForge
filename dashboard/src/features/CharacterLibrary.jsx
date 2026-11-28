import { useCallback, useState } from 'react';
import { Alert, Button, Card, Col, Form, Image, Input, Modal, Row, Space, Table, Tag, Typography } from 'antd';
import { useResource, ResourceStatus } from '../use_resource.jsx';
const { Text, Paragraph } = Typography;
const FIELDS = [
  ['name','Tên nhân vật',100],['species','Loài / kiểu nhân vật',80],
  ['appearance','Đặc điểm ngoại hình cố định',2000],
  ['personality','Tính cách / vai trò',2000],
  ['voice','Giọng nói / phong cách kể chuyện',300],
  ['model_ref','Model / LoRA tham chiếu (nếu có)',200],
  ['reference_notes','Ghi chú ảnh tham chiếu và nguồn',2000],
];
export function CharacterLibrary({mutate,onNavigate}) {
  const registry=useResource('/api/characters');
  const [editing,setEditing]=useState(null);
  const [references,setReferences]=useState(null);
  const [form]=Form.useForm();
  const [saving,setSaving]=useState(false);
  const refresh=useCallback(()=>registry.reload(),[registry.reload]);

  const open=character=>{setEditing(character||{});form.setFieldsValue(
    Object.fromEntries(FIELDS.map(([key])=>[key,character?.[key]||''])))};
  const save=async values=>{
    setSaving(true);
    try {
      const character={...values};
      if(editing?.id){character.id=editing.id;character.expected_version=editing.version;}
      const result=await mutate('/api/characters/save',{ack:'SAVE_CHARACTER',character});
      if(result){setEditing(null);await refresh();}
    } finally {setSaving(false);}
  };
  const items=registry.data?.characters||[];
  return <Space direction="vertical" size="large" style={{width:'100%'}}>
    <Alert showIcon type="info" message="Character Registry · Lưu local"
      description="Hồ sơ và bộ ảnh tham chiếu được lưu trong SQLite trên máy. Model/LoRA chỉ là thông tin tham chiếu; chưa tự huấn luyện hoặc gửi ảnh cho model."/>
    <Row gutter={[16,16]}>
      <Col xs={24} sm={12}><Card style={{height:'100%'}}><Text type="secondary">Nhân vật đã lưu</Text><h2 style={{margin:0}}>{registry.data?items.length:'—'}</h2></Card></Col>
      <Col xs={24} sm={12}><Card style={{height:'100%'}}><Text type="secondary">Kho lưu trữ</Text><h3 style={{margin:0}}>SQLite local</h3><Text type="secondary">Không tự đồng bộ cloud</Text></Card></Col>
    </Row>
    <Card title="Nhân vật của tôi" extra={<Space><Button onClick={refresh} loading={registry.loading}>Làm mới</Button><Button type="primary" onClick={()=>open(null)}>Tạo nhân vật</Button></Space>}>
      <ResourceStatus resource={registry} label="danh sách nhân vật"/>
      <Table rowKey="id" dataSource={items} loading={registry.loading} pagination={{pageSize:8}}
        locale={{emptyText:registry.error?'Không tải được dữ liệu':'Chưa có nhân vật'}}
        columns={[
          {title:'Tên',dataIndex:'name'},
          {title:'Loài',dataIndex:'species'},
          {title:'Phiên bản',dataIndex:'version',render:v=><Tag>v{v}</Tag>},
          {title:'Cập nhật',dataIndex:'updated_at',render:v=>v?.slice(0,16).replace('T',' ')},
          {title:'',render:(_,item)=><Space wrap><Button onClick={()=>open(item)}>Xem / Sửa</Button>
            <Button onClick={()=>setReferences(item)}>Ảnh nhận diện</Button></Space>},
        ]}/>
    </Card>
    <Card title="Sử dụng nhân vật trong video">
      <Paragraph type="secondary">Hồ sơ có ID ổn định để liên kết với storyboard trong giai đoạn tiếp theo. Chưa có cơ chế bảo đảm nhân vật nhất quán giữa các cảnh.</Paragraph>
      <Button onClick={()=>onNavigate('media-studio')}>Mở AI Media Studio</Button>
    </Card>
    <Modal open={editing!==null} title={editing?.id?'Chỉnh sửa nhân vật':'Tạo nhân vật'}
      onCancel={()=>setEditing(null)} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={save}>
        {FIELDS.map(([key,label,max])=><Form.Item key={key} name={key} label={label}
          rules={key==='name'?[{required:true,message:'Nhập tên nhân vật'}]:[]}>
          {max>300?<Input.TextArea rows={3} maxLength={max} showCount/>:<Input maxLength={max}/>}
        </Form.Item>)}
        <Alert type="info" showIcon message="Lưu hồ sơ trước, sau đó mở Ảnh nhận diện để thêm bộ tham chiếu." style={{marginBottom:16}}/>
        <Button block type="primary" htmlType="submit" loading={saving}>Lưu hồ sơ local</Button>
      </Form>
    </Modal>
    {references&&<ReferencePacks key={references.id} character={references} mutate={mutate} onClose={()=>setReferences(null)}/>}
  </Space>;
}

const ROLES=[['primary','Ảnh chính'],['full_body','Toàn thân'],['alternate','Góc nhìn khác']];
const MAX_FILE=512*1024;
const readBase64=file=>new Promise((resolve,reject)=>{
  const reader=new FileReader();
  reader.onload=()=>resolve(String(reader.result).split(',')[1]);
  reader.onerror=()=>reject(new Error('Không đọc được ảnh.'));
  reader.readAsDataURL(file);
});
function ReferencePacks({character,mutate,onClose}){
  const resource=useResource('/api/characters/'+character.id+'/references');
  const [files,setFiles]=useState({});
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState(null);
  const [inputVersion,setInputVersion]=useState(0);
  const save=async()=>{
    if(saving||!files.primary||!resource.data||resource.error||resource.loading)return;
    setSaving(true);setError(null);
    try{
      const images=await Promise.all(ROLES.filter(([role])=>files[role]).map(async([role])=>({
        role,data_base64:await readBase64(files[role]),
      })));
      const result=await mutate('/api/characters/references/save',{ack:'SAVE_REFERENCE_PACK',pack:{
        character_id:character.id,expected_character_version:resource.data.character_version,
        expected_revision:resource.data.latest_revision,images,
      }});
      if(result?.packs){resource.setData(result);setFiles({});setInputVersion(v=>v+1);}
    }catch(e){setError(e.message||'Không lưu được bộ ảnh.');await resource.reload();}
    finally{setSaving(false);}
  };
  return <Modal open centered title={'Ảnh nhận diện · '+character.name} onCancel={onClose} footer={null}>
    <Alert type="info" showIcon message="Chỉ lưu trên máy"
      description="Bộ ảnh được lưu theo phiên bản; chưa tự gửi đến model tạo ảnh/video hoặc chứng minh tính nhất quán."/>
    <ResourceStatus resource={resource} label="bộ ảnh nhận diện"/>
    {resource.data?.packs.map(pack=><details key={pack.revision} open={pack.revision===resource.data.latest_revision}>
      <summary>Phiên bản {pack.revision} · Hồ sơ v{pack.character_version}</summary>
      <Space wrap>{pack.images.map(item=><div key={item.role}>
        <Image width={96} src={item.preview_url} alt={ROLES.find(([r])=>r===item.role)?.[1]??item.role}/>
        <div>{ROLES.find(([r])=>r===item.role)?.[1]??item.role}</div>
      </div>)}</Space>
    </details>)}
    <h3>Lưu bộ ảnh mới</h3>
    <Paragraph type="secondary">PNG/JPEG tĩnh, tối đa 512 KiB mỗi ảnh. Cần ít nhất ảnh chính. Bộ cũ không bị ghi đè.</Paragraph>
    {error&&<Alert type="error" showIcon message={error}/>}
    <Space direction="vertical" style={{width:'100%'}} key={inputVersion}>
      {ROLES.map(([role,label])=><label key={role} style={{display:'block'}}>
        {label} {role==='primary'?'(bắt buộc)':''}
        <input type="file" accept="image/png,image/jpeg" disabled={saving} style={{display:'block'}}
          onChange={event=>{
            const file=event.target.files?.[0];
            setError(null);
            if(file&&(!['image/png','image/jpeg'].includes(file.type)||file.size>MAX_FILE)){
              event.target.value='';setFiles(prev=>({...prev,[role]:null}));
              setError('Chỉ chọn PNG/JPEG tối đa 512 KiB.');return;
            }
            setFiles(prev=>({...prev,[role]:file??null}));
          }}/>
      </label>)}
    </Space>
    <Button type="primary" loading={saving} disabled={!files.primary||resource.loading||!resource.data||Boolean(resource.error)||resource.data.latest_revision>=12}
      onClick={save}>Lưu phiên bản ảnh mới</Button>
  </Modal>;
}
