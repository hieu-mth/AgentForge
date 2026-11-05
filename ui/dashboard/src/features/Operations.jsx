import { Alert, Button, Card, Descriptions, Divider, Statistic, Table, Typography } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import { badge, fallback } from '../components/shared.jsx';
const { Text } = Typography;

export function Overview({data, onNavigate}) {
  const company=data?.company_v2||{}, biz=company.business||{}, content=company.content||{};
  const cards=[
    ['AI đang chờ duyệt',content.pending_ai_reviews??0],
    ['Video cần xem',content.videos_waiting_for_owner??0],
    ['Chiến dịch thật',biz.real_campaigns??0],
    ['Lead owner ghi nhận',biz.owner_recorded_leads??0],
  ];
  return <>
    <div className="metric-grid">{cards.map(([label,value])=>
      <Card key={label} className="metric"><Statistic title={label} value={value}/></Card>)}</div>
    <div className="two-cols">
      <Card title="Tình trạng hệ thống">
        <Descriptions column={1} size="small" items={[
          {key:'1',label:'Operations',children:badge(company.operations)},
          {key:'2',label:'Autopilot',children:badge(company.autopilot?.enabled?'ACTIVE':'OFF')},
          {key:'3',label:'Website public',children:biz.public_website_deployment_verified?'Đã xác minh':'Chưa xác minh'},
          {key:'4',label:'Lợi nhuận bank-verified',children:'Chưa có đối soát'},
        ]}/>
      </Card>
      <Card title="Cần làm tiếp" extra={<Button size="small" onClick={()=>onNavigate('workspace')}>Giao việc</Button>}>
        {(company.next_owner_actions||[]).length?
          (company.next_owner_actions||[]).map(x=><p key={x}><ClockCircleOutlined/> {x}</p>):
          fallback('Không có hành động mới')}
      </Card>
    </div>
  </>;
}

export function ReadOnlyPage({section,data}) {
  const company=data?.company_v2||{}, b=company.business||{};
  if(section==='finance') return <div className="metric-grid">
    <Card><Statistic title="Campaign thật" value={b.real_campaigns||0}/></Card>
    <Card><Statistic title="Bài đăng owner khai báo" value={b.owner_attested_publications||0}/></Card>
    <Card><Statistic title="Lợi nhuận xác minh" value="Chưa xác minh"/></Card>
    <Card><Statistic title="Provider billing" value="Chưa kết nối"/></Card>
    <Alert type="info" className="full-row" message="Số liệu hiện có chưa phải báo cáo ngân hàng. Không tự giao dịch, chi tiền hoặc đăng quảng cáo."/>
  </div>;
  if(section==='channels') return <Card title="Kênh xuất bản">
    <Alert type="warning" showIcon message="YouTube và TikTok chưa kết nối OAuth"
      description="AgentForge hiện chỉ chuẩn bị gói upload thủ công. Không hiển thị nút kết nối giả."/>
  </Card>;
  if(section==='team') return <Card title="Danh mục AI Workforce">
    <Table rowKey={s=>s.id} dataSource={data?.skills||[]} pagination={{pageSize:10}}
      columns={[{title:'Skill',dataIndex:'id'},{title:'Role/Worker',dataIndex:'worker'},
        {title:'Chế độ',dataIndex:'mode',render:badge}]}/>
  </Card>;
  if(section==='settings') return <Card title="Giới hạn & chính sách">
    <Descriptions column={1} bordered items={[
      {key:'1',label:'Lượt model tối đa cho prompt/Goal',children:data?.workspace_policy?.max_estimated_model_calls??1},
      {key:'2',label:'Website intake',children:data?.workspace_policy?.website_enabled?'Bật':'Tắt'},
      {key:'3',label:'Storyboard intake',children:data?.workspace_policy?.storyboard_enabled?'Bật':'Tắt'},
      {key:'4',label:'Autopilot daily cap',children:data?.autopilot_policy?.daily_cap??0},
    ]}/>
    <Alert style={{marginTop:18}} type="info" message="Cấu hình nâng cao vẫn ở Control Center cũ trong giai đoạn chuyển đổi."/>
  </Card>;
  return fallback('Không có dữ liệu');
}

