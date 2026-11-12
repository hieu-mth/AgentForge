import { Alert, Button, Card, Descriptions, Table } from 'antd';
import { AuditOutlined, BankOutlined, ClockCircleOutlined, FireOutlined,
  PlayCircleOutlined, TeamOutlined } from '@ant-design/icons';
import { badge, fallback, StatTile } from '../components/shared.jsx';
import { buildOverview } from '../overview_data.js';
import { formatVietnamDateTime } from '../date_format.js';
import { useResource } from '../use_resource.jsx';
import { useScreenRefresh } from '../refresh_scope.jsx';

export function Overview({data, onNavigate, onRefresh}) {
  const motion=useResource('/api/film/motion');
  useScreenRefresh(motion.reload);
  const summary=buildOverview(data);
  const {counts,issues,recent,trend,scope}=summary;
  const ready=Boolean(data);
  const daemon=data?.daemon||{};
  const autopilot=data?.autopilot_policy||{};
  const tiles=[
    ['Đang thực hiện',counts.running,<PlayCircleOutlined/>,'info'],
    ['Chờ Owner duyệt',counts.waiting,<AuditOutlined/>,counts.waiting?'warn':'good'],
    ['Hoàn thành hôm nay',counts.doneToday,<ClockCircleOutlined/>,'good'],
    ['Lỗi trong mẫu',counts.problems,<FireOutlined/>,counts.problems?'bad':'info'],
  ];
  const max=Math.max(1,...trend.map(d=>d.succeeded+d.failed));
  return <div className="overview-command-center">
    <Alert type="info" showIcon style={{marginBottom:16}}
      message="Bảng điều hành dựa trên dữ liệu local"
      description={ready?`KPI tác vụ dựa trên ${scope.tasks} tác vụ gần nhất trong bootstrap; không phải tổng lịch sử. Mục chờ duyệt và lỗi được tổng hợp từ các nguồn riêng, có thể không bao phủ toàn bộ dữ liệu cũ.`:'Chưa tải được dữ liệu bootstrap. Không hiển thị số liệu giả.'}/>
    <div className="stat-grid">
      {tiles.map(([label,value,icon,tone])=><StatTile key={label} label={label}
        value={ready?value:'—'} icon={icon} tone={tone}/>)}
    </div>
    <div className="two-cols">
      <Card className="panel" title="Cần bạn xử lý"
        extra={<Button size="small" onClick={onRefresh}>Làm mới</Button>}>
        {!ready?fallback('Chưa có dữ liệu'):issues.length?
          <div className="overview-issues">{issues.slice(0,8).map(item=>
            <div className="overview-issue" key={item.id}>
              <div><strong>{item.title}</strong><div>{badge(item.status)}</div></div>
              <Button size="small" onClick={()=>onNavigate(item.section)}>Mở</Button>
            </div>)}</div>:fallback('Không có mục cần xử lý trong dữ liệu hiện tại')}
        {ready&&issues.length>8&&<p>Còn {issues.length-8} mục. Mở các trang duyệt và lịch sử để xem thêm.</p>}
      </Card>
      <Card className="panel" title="Hoạt động gần đây"
        extra={<Button size="small" onClick={()=>onNavigate('tasks')}>Lịch sử</Button>}>
        {!ready?fallback('Chưa có dữ liệu'):recent.length?
          <div className="overview-activity">{recent.map(task=>
            <div className="overview-activity-row" key={task.task_id}>
              <div><strong>{task.skill_id||task.kind||'Tác vụ'}</strong>
                <div className="overview-muted">{formatVietnamDateTime(task.updated_at||task.created_at)}</div></div>
              {badge(task.status)}
            </div>)}</div>:fallback('Chưa có hoạt động')}
      </Card>
    </div>
    <div className="two-cols">
      <Card className="panel" title="Sức khỏe & giới hạn hệ thống">
        <Descriptions size="small" column={1} items={[
          {key:'daemon',label:'Daemon lịch',children:daemon.fresh?badge(daemon.status||'ACTIVE'):badge('NOT_RUNNING')},
          {key:'autopilot',label:'Autopilot (cấu hình)',children:badge(autopilot.enabled?'ACTIVE':'OFF')},
          {key:'model',label:'Model đang phục vụ',children:'Chưa kiểm tra runtime'},
          {key:'comfy',label:'ComfyUI / GPU',children:motion.loading?'Đang kiểm tra':motion.error?'Không kiểm tra được':badge(motion.data?.gpu?.status||'UNKNOWN')},
          {key:'vram',label:'VRAM trống (ảnh chụp)',children:typeof motion.data?.gpu?.vram_free_snapshot_gib==='number'?motion.data.gpu.vram_free_snapshot_gib+' GiB':'Chưa có dữ liệu'},
          {key:'cost',label:'Chi phí AI đã xác minh',children:'Chưa có dữ liệu đối soát'},
        ]}/>
        <Alert style={{marginTop:12}} type="warning" showIcon
          message="ComfyUI chỉ kiểm tra kết nối/GPU; không xác nhận khả năng render video hoặc hiệu năng model."/>
        <Button style={{marginTop:12}} onClick={()=>onNavigate('operations')}>Xem vận hành</Button>
      </Card>
      <Card className="panel" title="Hiệu suất tác vụ · 7 ngày gần nhất">
        <p className="overview-muted">Số tác vụ trong mẫu hiện tại, tính theo ngày cập nhật. Không phải thống kê lịch sử đầy đủ.</p>
        <div className="overview-chart" role="img" aria-label="Biểu đồ tác vụ hoàn thành và lỗi trong 7 ngày">
          {trend.map(point=><div className="overview-chart-day" key={point.day}>
            <div className="overview-chart-bars">
              <span className="overview-bar overview-bar-good" style={{height:`${100*point.succeeded/max}%`}} title={`Hoàn thành: ${point.succeeded}`}/>
              <span className="overview-bar overview-bar-bad" style={{height:`${100*point.failed/max}%`}} title={`Lỗi: ${point.failed}`}/>
            </div>
            <small>{point.day?.slice(5)||'—'}</small>
          </div>)}
        </div>
        <div className="overview-legend">■ Hoàn thành &nbsp; · &nbsp; Lỗi / gián đoạn</div>
      </Card>
    </div>
  </div>;
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
