import { Alert, Button, Card, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useResource, ResourceStatus } from '../use_resource.jsx';
import { useScreenRefresh } from '../refresh_scope.jsx';

const { Text } = Typography;

export function Projects() {
  const resource = useResource('/api/video-studio/projects');
  useScreenRefresh(resource.reload);
  const rows = resource.data?.projects || [];
  return <Space direction="vertical" size="large" style={{width:'100%'}}>
    <Alert type="info" showIcon message="Kho dự án video local"
      description="Film Studio là hướng sản xuất mới. Video V1.5 chỉ hiển thị lịch sử; không tự chuyển đổi, đăng tải hoặc xóa dữ liệu. Trạng thái kỹ thuật không xác nhận chất lượng hình ảnh."/>
    <Card title="Dự án & tập phim" extra={<Button icon={<ReloadOutlined/>}
      onClick={resource.reload} loading={resource.loading}>Làm mới</Button>}>
      <ResourceStatus resource={resource} label="danh sách dự án video"/>
      <Table rowKey="project_id" size="middle" pagination={{pageSize:10}}
        loading={resource.loading} dataSource={rows}
        locale={{emptyText:resource.error?'Không tải được dữ liệu':'Chưa có video project local'}}
        columns={[
          {title:'Dự án',dataIndex:'project_id',render:v=><Text code>{v}</Text>},
          {title:'Nguồn',dataIndex:'source',render:v=><Tag>{v==='film_studio'?'Film Studio':'Video V1.5'}</Tag>},
          {title:'Trạng thái',dataIndex:'state'},
          {title:'Quyền sửa',dataIndex:'legacy_read_only',render:v=>v?'Chỉ đọc':'Theo cơ chế Owner'},
        ]}/>
      <Text type="secondary">Danh sách chỉ đọc. Chưa có API sản xuất thống nhất hoặc kiểm chứng GPU đầu-cuối.</Text>
    </Card>
  </Space>;
}
