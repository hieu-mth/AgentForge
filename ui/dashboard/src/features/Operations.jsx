import { Alert, Button, Card, Descriptions, Table } from 'antd';
import { AuditOutlined, BankOutlined, ClockCircleOutlined, FireOutlined,
  PlayCircleOutlined, TeamOutlined } from '@ant-design/icons';
import { badge, fallback, StatTile } from '../components/shared.jsx';

export function Overview({data, onNavigate}) {
  const company=data?.company_v2||{}, biz=company.business||{}, content=company.content||{};
  const pending=content.pending_ai_reviews??0, videos=content.videos_waiting_for_owner??0;
  const actions=company.next_owner_actions||[];
  return <>
    <div className="stat-grid">
      <StatTile label="AI đang chờ duyệt" value={pending} icon={<AuditOutlined/>} tone={pending?'warn':'good'}
        hint={pending?'Cần bạn xem xét':'Đã xử lý hết'}/>
      <StatTile label="Video cần xem" value={videos} icon={<PlayCircleOutlined/>} tone={videos?'warn':'good'}/>
      <StatTile label="Chiến dịch thật" value={biz.real_campaigns??0} icon={<FireOutlined/>} tone="info"/>
      <StatTile label="Lead owner ghi nhận" value={biz.owner_recorded_leads??0} icon={<TeamOutlined/>} tone="info"/>
    </div>
    <div className="two-cols">
      <Card title="Tình trạng hệ thống" className="panel">
        <Descriptions column={1} size="small" items={[
          {key:'1',label:'Operations',children:badge(company.operations)},
          {key:'2',label:'Autopilot',children:badge(company.autopilot?.enabled?'ACTIVE':'OFF')},
          {key:'3',label:'Website public',children:biz.public_website_deployment_verified?'Đã xác minh':'Chưa xác minh'},
          {key:'4',label:'Lợi nhuận bank-verified',children:'Chưa có đối soát'},
        ]}/>
      </Card>
      <Card title="Cần làm tiếp" className="panel"
        extra={<Button size="small" type="primary" ghost onClick={()=>onNavigate('workspace')}>Giao việc</Button>}>
        {actions.length ?
          <ul className="todo-list">{actions.map(x=><li key={x}><ClockCircleOutlined/> {x}</li>)}</ul> :
          fallback('Không có hành động mới')}
      </Card>
    </div>
  </>;
}

export function ReadOnlyPage({section,data}) {
  const company=data?.company_v2||{}, b=company.business||{};
  if(section==='finance') return <>
    <div className="stat-grid">
      <StatTile label="Campaign thật" value={b.real_campaigns||0} icon={<FireOutlined/>}/>
      <StatTile label="Bài đăng owner khai báo" value={b.owner_attested_publications||0} icon={<AuditOutlined/>}/>
      <StatTile label="Lợi nhuận xác minh" value="Chưa xác minh" tone="warn" icon={<BankOutlined/>}/>
      <StatTile label="Provider billing" value="Chưa kết nối" tone="warn"/>
    </div>
    <Alert showIcon type="info" message="Số liệu hiện có chưa phải báo cáo ngân hàng. Không tự giao dịch, chi tiền hoặc đăng quảng cáo."/>
  </>;
  if(section==='channels') return <Card title="Kênh xuất bản" className="panel">
    <Alert type="warning" showIcon message="YouTube và TikTok chưa kết nối OAuth"
      description="AgentForge hiện chỉ chuẩn bị gói upload thủ công. Không hiển thị nút kết nối giả."/>
  </Card>;
  if(section==='team') return <Card title="Danh mục AI Workforce" className="panel">
    <Table rowKey={s=>s.id} dataSource={data?.skills||[]} scroll={{x:'max-content'}}
      pagination={{pageSize:10,hideOnSinglePage:true}}
      columns={[{title:'Skill',dataIndex:'id',render:v=><code>{v}</code>},{title:'Role/Worker',dataIndex:'worker'},
        {title:'Chế độ',dataIndex:'mode',render:badge}]}/>
  </Card>;
  if(section==='settings') return <Card title="Giới hạn & chính sách" className="panel">
    <Descriptions column={{xs:1,md:1}} bordered items={[
      {key:'1',label:'Lượt model tối đa cho prompt/Goal',children:data?.workspace_policy?.max_estimated_model_calls??1},
      {key:'2',label:'Website intake',children:data?.workspace_policy?.website_enabled?'Bật':'Tắt'},
      {key:'3',label:'Storyboard intake',children:data?.workspace_policy?.storyboard_enabled?'Bật':'Tắt'},
      {key:'4',label:'Autopilot daily cap',children:data?.autopilot_policy?.daily_cap??0},
    ]}/>
    <Alert style={{marginTop:18}} type="info" message="Cấu hình nâng cao vẫn ở Control Center cũ trong giai đoạn chuyển đổi."/>
  </Card>;
  return fallback('Không có dữ liệu');
}
