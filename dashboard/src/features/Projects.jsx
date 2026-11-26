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
      description="Danh sách chung của bản nháp Studio và tập phim dựng thủ công. Trạng thái kỹ thuật không xác nhận chất lượng hình ảnh hoặc video."/>
    <Card title="Dự án & tập phim" extra={<Button icon={<ReloadOutlined/>}
      onClick={resource.reload} loading={resource.loading}>Làm mới</Button>}>
      <ResourceStatus resource={resource} label="danh sách dự án video"/>
      <Table rowKey="project_id" size="middle" pagination={{pageSize:10}}
        loading={resource.loading} dataSource={rows}
        locale={{emptyText:resource.error?'Không tải được dữ liệu':'Chưa có video project local'}}
        columns={[
          {title:'Dự án',dataIndex:'project_id',render:v=><Text code>{v}</Text>},
          {title:'Tên phim',dataIndex:'film_slug',render:v=><Text>{v}</Text>},
          {title:'Nguồn',dataIndex:'source',render:v=><Tag>{v==='studio_draft'?'Studio':'Dựng thủ công'}</Tag>},
          {title:'Trạng thái',dataIndex:'state'},
          
        ]}/>
      <Text type="secondary">Danh sách chỉ đọc, ưu tiên bản nháp Studio gần nhất. Kiểm chứng GPU và chất lượng phim cần nghiệm thu thực tế.</Text>
    </Card>
  </Space>;
}
