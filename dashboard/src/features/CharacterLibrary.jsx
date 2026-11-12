import { useCallback, useState } from 'react';
import { Alert, Button, Card, Col, Form, Input, Modal, Row, Space, Table, Tag, Typography } from 'antd';
import { api } from '../api.js';
import { useResource, ResourceStatus } from '../use_resource.jsx';
import { useScreenRefresh } from '../refresh_scope.jsx';
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
  const [form]=Form.useForm();
  const [saving,setSaving]=useState(false);
  const refresh=useCallback(()=>registry.reload(),[registry.reload]);
  useScreenRefresh(refresh);
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
      description="Hồ sơ nhân vật được lưu trong SQLite trên máy. Model/LoRA chỉ là thông tin tham chiếu; chưa có huấn luyện, upload ảnh hoặc liên kết video tự động."/>
    <Row gutter={[16,16]}>
      <Col xs={24} sm={12}><Card><Text type="secondary">Nhân vật đã lưu</Text><h2 style={{margin:0}}>{registry.data?items.length:'—'}</h2></Card></Col>
      <Col xs={24} sm={12}><Card><Text type="secondary">Kho lưu trữ</Text><h3 style={{margin:0}}>SQLite local</h3><Text type="secondary">Không tự đồng bộ cloud</Text></Card></Col>
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
          {title:'',render:(_,item)=><Button onClick={()=>open(item)}>Xem / Sửa</Button>},
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
        <Alert type="warning" showIcon message="Chưa hỗ trợ upload ảnh gốc" style={{marginBottom:16}}/>
        <Button block type="primary" htmlType="submit" loading={saving}>Lưu hồ sơ local</Button>
      </Form>
    </Modal>
  </Space>;
}
