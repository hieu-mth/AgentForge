import { Alert, Button, Card, Col, Row, Space, Steps, Tag, Typography } from 'antd';
import { ArrowRightOutlined, PictureOutlined, TeamOutlined, SafetyCertificateOutlined, SettingOutlined } from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;

// The studio is a workflow entry point, not a simulated video-production runtime.
// All destinations are existing Owner routes and retain their own authorization gates.
const WORKFLOW = [
  {title:'Giao ý tưởng',description:'Tạo kế hoạch và duyệt từng bước',route:'workspace',action:'Giao việc',icon:<ArrowRightOutlined/>},
  {title:'Chuẩn bị tư liệu',description:'Tạo và kiểm tra ảnh AI trên máy',route:'projects',action:'Mở kho ảnh',icon:<PictureOutlined/>},
  {title:'Kiểm tra thành phẩm',description:'Duyệt storyboard và video đã tạo',route:'reviews',action:'Mở nơi duyệt',icon:<SafetyCertificateOutlined/>},
];
const LINKS = [
  {title:'Thư viện nhân vật',description:'Quản lý hồ sơ nhân vật local',route:'characters',icon:<TeamOutlined/>},
  {title:'Model & cấu hình',description:'Xem model đã đăng ký và khả năng kết nối thực tế',route:'models',icon:<SettingOutlined/>},
];
export function MediaStudio({onNavigate}) {
  return <Space direction="vertical" size="large" style={{width:'100%'}}>
    <div>
      <Tag>AI Media Studio</Tag>
      <Title level={3} style={{margin:'10px 0 6px'}}>Sản xuất video</Title>
      <Paragraph type="secondary" style={{margin:0}}>Đi từ ý tưởng đến tư liệu và bản duyệt bằng các công cụ hiện có của AgentForge.</Paragraph>
    </div>
    <Alert type="info" showIcon message="Trung tâm điều hướng, không phải trình render"
      description="Trang này không tự tạo video, không xác nhận GPU/model đã sẵn sàng. Mỗi bước mở đúng màn hình thực tế; quyền chạy AI, tiến trình ngoài và duyệt thành phẩm vẫn được kiểm soát riêng."/>
    <Card title="Quy trình đề xuất">
      <Steps responsive current={-1} items={WORKFLOW.map(x=>({title:x.title,description:x.description,status:'wait'}))}/>
      <Row gutter={[12,12]} style={{marginTop:22}}>
        {WORKFLOW.map(item=><Col xs={24} md={8} key={item.route}>
          <Card size="small" style={{height:'100%'}}>
            <Space direction="vertical" style={{width:'100%'}}>
              <Text strong>{item.title}</Text>
              <Text type="secondary">{item.description}</Text>
              <Button block icon={item.icon} onClick={()=>onNavigate(item.route)}>{item.action}</Button>
            </Space>
          </Card>
        </Col>)}
      </Row>
    </Card>
    <Row gutter={[12,12]}>
      {LINKS.map(item=><Col xs={24} md={12} key={item.route}>
        <Card title={item.title} extra={item.icon}>
          <Paragraph type="secondary">{item.description}</Paragraph>
          <Button onClick={()=>onNavigate(item.route)}>Mở {item.title.toLowerCase()}</Button>
        </Card>
      </Col>)}
    </Row>
    <Alert type="warning" showIcon message="Chưa xác minh khả năng tạo video AI đầu-cuối"
      description="Trước khi đánh dấu sẵn sàng cần kiểm tra checkpoint, ComfyUI, GPU, tạo video thật và QA MP4 trên máy Owner. Không coi storyboard hoặc ảnh tĩnh là video chuyển động đã hoàn thành."/>
  </Space>;
}
