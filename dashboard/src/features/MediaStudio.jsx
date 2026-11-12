import { useState } from 'react';
import { Alert, Button, Card, Col, Empty, Input, Row, Space, Steps, Tag, Typography } from 'antd';
import { CameraOutlined, CloudUploadOutlined, PlayCircleOutlined, SettingOutlined } from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const STAGES = [
  {title:'Kịch bản', description:'Ý tưởng, tình huống và lời thoại'},
  {title:'Storyboard', description:'Chia cảnh và chọn ảnh tham chiếu'},
  {title:'Render', description:'Tạo chuyển động và dựng MP4'},
  {title:'Duyệt', description:'Kiểm tra lỗi trước khi xuất bản'},
];
const SECTIONS = [
  {key:'channels',label:'Dự án & Kênh'},
  {key:'characters',label:'Nhân vật'},
  {key:'production',label:'Sản xuất video'},
  {key:'library',label:'Thư viện Media'},
  {key:'models',label:'Model & Cấu hình'},
];

export function MediaStudio({onNavigate}) {
  const [tab,setTab]=useState('production');
  const [idea,setIdea]=useState('');
  return <Space direction="vertical" size="large" style={{width:'100%'}}>
    <Alert type="info" showIcon message="AI Media Studio · Giai đoạn dựng sườn"
      description="Đây là giao diện chuẩn bị cho workflow tạo video chuyển động thật. Chưa có backend quản lý nhân vật, upload ảnh hay image-to-video; không có video giả lập hoặc số liệu demo được tính là kết quả thật."/>
    <Row gutter={[16,16]}>
      <Col xs={24} lg={16}>
        <Card>
          <Space direction="vertical" size="small">
            <Tag color="blue">Dự án thử nghiệm</Tag>
            <Title level={3} style={{margin:0}}>Nhật ký 6 bé mèo</Title>
            <Paragraph type="secondary" style={{margin:0}}>Xây dựng series giải trí từ ảnh và video thật của 6 bé mèo. Duyệt từng bước trước khi sử dụng GPU hoặc đăng tải.</Paragraph>
          </Space>
        </Card>
      </Col>
      <Col xs={24} lg={8}>
        <Card title="Trạng thái triển khai">
          <Text>Giao diện: đang thiết lập</Text><br/>
          <Text type="secondary">Video AI: chưa tích hợp</Text><br/>
          <Text type="secondary">Model: chưa benchmark trên RTX 5070</Text>
        </Card>
      </Col>
    </Row>
    <Row gutter={[12,12]}>
      {SECTIONS.map(item=><Col xs={12} sm={8} lg={4} key={item.key}>
        <Button block type={tab===item.key?'primary':'default'} onClick={()=>setTab(item.key)}
          style={{height:'auto',minHeight:48,whiteSpace:'normal'}}>{item.label}</Button>
      </Col>)}
    </Row>
    {tab==='production'&&<Card title="Quy trình sản xuất video" extra={<Tag>Chưa chạy</Tag>}>
      <Steps responsive current={0} items={STAGES.map(s=>({...s,status:'wait'}))}/>
      <div style={{marginTop:24,maxWidth:760}}>
        <Title level={5}>Ý tưởng tập phim</Title>
        <Input.TextArea value={idea} onChange={e=>setIdea(e.target.value)}
          placeholder="Ví dụ: Bé mèo ham ăn lén lấy pate, đại ca phát hiện..."
          autoSize={{minRows:4,maxRows:9}} maxLength={5000} showCount/>
        <Paragraph type="secondary" style={{marginTop:12}}>Bản nháp chỉ nằm trong phiên giao diện này; chưa lưu vào backend. Nút chạy AI sẽ được bật khi có API và cơ chế duyệt thực tế.</Paragraph>
        <Button type="primary" icon={<PlayCircleOutlined/>} disabled>Chuẩn bị kịch bản AI</Button>
      </div>
    </Card>}
    {tab==='characters'&&<Card title="Hồ sơ 6 nhân vật" extra={<CameraOutlined/>}>
      <Empty description="Chưa có hồ sơ mèo. Giai đoạn tiếp theo sẽ cho phép upload ảnh gốc, đặt tên, tính cách và lưu ảnh tham chiếu theo từng bé."/>
      <Button disabled icon={<CloudUploadOutlined/>}>Thêm ảnh nhân vật (chưa tích hợp)</Button>
    </Card>}
    {tab==='channels'&&<Card title="Dự án & Kênh">
      <Text strong>Nhật ký 6 bé mèo</Text>
      <Paragraph type="secondary">Kênh thử nghiệm; chưa liên kết TikTok, YouTube hoặc Facebook. Việc đăng tải sẽ luôn cần phê duyệt.</Paragraph>
    </Card>}
    {tab==='library'&&<Card title="Thư viện Media">
      <Empty description="Chưa có thư viện riêng cho dự án. Ảnh gốc, ảnh AI và clip render sẽ được phân loại và lưu local sau khi tích hợp backend."/>
    </Card>}
    {tab==='models'&&<Card title="Model & Cấu hình" extra={<SettingOutlined/>}>
      <Paragraph>Đề xuất thử nghiệm: Qwen3 8B (kịch bản), FLUX.1 Schnell (ảnh), Wan 2.2 TI2V 5B (video), FFmpeg (dựng phim).</Paragraph>
      <Alert type="warning" showIcon message="Chưa xác nhận model đã cài hoặc hoạt động" description="Cần kiểm tra ComfyUI, checkpoint, VRAM và render một MP4 thật trước khi đánh dấu READY."/>
      <Button onClick={()=>onNavigate('models')}>Mở cấu hình AI hiện có</Button>
    </Card>}
  </Space>;
}
