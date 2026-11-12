import { Alert, Button, Card, Col, Empty, Row, Space, Steps, Tag, Typography } from 'antd';
import { CameraOutlined, DatabaseOutlined, ExperimentOutlined, PlusOutlined } from '@ant-design/icons';
const { Title, Paragraph, Text } = Typography;

export function CharacterLibrary({onNavigate}) {
  return <Space direction="vertical" size="large" style={{width:'100%'}}>
    <Alert type="info" showIcon message="Thư viện nhân vật · Khung giao diện"
      description="Hồ sơ, ảnh tham chiếu, phiên bản và model nhân vật sẽ được lưu local sau khi có API. Chưa có hồ sơ nào được tạo hoặc lưu ở phiên bản này."/>
    <Row gutter={[16,16]}>
      <Col xs={24} md={8}><Card><Text type="secondary">Nhân vật đã lưu</Text><Title level={2} style={{marginBottom:0}}>0</Title><Text type="secondary">Chưa có backend hồ sơ</Text></Card></Col>
      <Col xs={24} md={8}><Card><Text type="secondary">Bộ ảnh tham chiếu</Text><Title level={2} style={{marginBottom:0}}>0</Title><Text type="secondary">Chưa upload</Text></Card></Col>
      <Col xs={24} md={8}><Card><Text type="secondary">Model/LoRA đã xác minh</Text><Title level={2} style={{marginBottom:0}}>0</Title><Text type="secondary">Chưa huấn luyện hoặc đăng ký</Text></Card></Col>
    </Row>
    <Card title="Nhân vật của tôi" extra={<Button type="primary" disabled icon={<PlusOutlined/>}>Tạo nhân vật</Button>}>
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Chưa có nhân vật. Sau khi tích hợp lưu trữ, bạn sẽ tạo hồ sơ cho từng bé mèo hoặc nhân vật AI khác."/>
    </Card>
    <Card title="Cấu trúc hồ sơ nhân vật">
      <Row gutter={[16,16]}>
        <Col xs={24} md={8}><Space direction="vertical"><CameraOutlined style={{fontSize:24}}/><Text strong>Danh tính & tham chiếu</Text><Paragraph type="secondary">Tên, loài, ngoại hình, tính cách, ảnh gốc, ảnh chuẩn và những chi tiết không được thay đổi.</Paragraph></Space></Col>
        <Col xs={24} md={8}><Space direction="vertical"><DatabaseOutlined style={{fontSize:24}}/><Text strong>Phiên bản & tài sản</Text><Paragraph type="secondary">Ảnh/video tham chiếu, lịch sử chỉnh sửa, hash tệp, nguồn ảnh và dự án sử dụng.</Paragraph></Space></Col>
        <Col xs={24} md={8}><Space direction="vertical"><ExperimentOutlined style={{fontSize:24}}/><Text strong>Cấu hình AI</Text><Paragraph type="secondary">Model nền, adapter/LoRA tùy chọn, prompt nhân vật, seed và kết quả kiểm tra nhất quán.</Paragraph></Space></Col>
      </Row>
    </Card>
    <Card title="Quy trình chuẩn bị nhân vật">
      <Steps responsive current={0} items={[
        {title:'Tạo hồ sơ',status:'wait'},
        {title:'Ảnh tham chiếu',status:'wait'},
        {title:'Kiểm tra AI',status:'wait'},
        {title:'Sẵn sàng sử dụng',status:'wait'},
      ]}/>
      <Paragraph type="secondary" style={{marginTop:16}}>Không mặc định mỗi nhân vật cần một model huấn luyện riêng. Thử ảnh tham chiếu trước, chỉ dùng LoRA khi có bằng chứng cần thiết.</Paragraph>
      <Button onClick={()=>onNavigate('media-studio')}>Mở AI Media Studio</Button>
      <Tag style={{marginLeft:12}}>Chưa có tính năng tạo nhân vật thật</Tag>
    </Card>
  </Space>;
}
