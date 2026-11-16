import { useState } from 'react';
import { Alert, Button, Card, Descriptions, Popover, Table } from 'antd';
import { AuditOutlined, BankOutlined, ClockCircleOutlined, FireOutlined,
  PlayCircleOutlined, InfoCircleOutlined, TeamOutlined } from '@ant-design/icons';
import { badge, fallback, StatTile } from '../components/shared.jsx';
import { buildOverview } from '../overview_data.js';
import { formatVietnamDateTime } from '../date_format.js';
import { useResource } from '../use_resource.jsx';
import { useScreenRefresh } from '../refresh_scope.jsx';

const SYSTEM_HELP={
  daemon:{
    title:'Bộ chạy tác vụ theo lịch',
    purpose:'Theo dõi lịch và kích hoạt công việc tự động khi đến giờ, nếu tiến trình nền đang chạy.',
    impact:'Nếu không có tín hiệu hoạt động mới, tác vụ theo lịch có thể không được kích hoạt. Công việc chạy thủ công không nhất thiết bị ảnh hưởng.',
    note:'Trạng thái được suy ra từ tín hiệu gần nhất; không phải phép kiểm tra trực tiếp tiến trình.',
  },
  autopilot:{
    title:'Chế độ tự động',
    purpose:'Cho phép AgentForge chủ động thực hiện những công việc thuộc phạm vi và giới hạn đã cấu hình.',
    impact:'Khi tắt, các luồng tự động phụ thuộc chế độ này sẽ không được tự khởi chạy. Khi bật, vẫn cần bộ chạy và các điều kiện khác hoạt động.',
    note:'Đã bật chỉ phản ánh cấu hình, không xác nhận có tác vụ đang chạy.',
  },
  model:{
    title:'Model AI',
    purpose:'Model AI xử lý các yêu cầu như phân tích, viết nội dung và hỗ trợ tạo sản phẩm.',
    impact:'Nếu model không sẵn sàng, những công việc cần AI có thể thất bại hoặc chờ xử lý.',
    note:'Dashboard chưa có phép kiểm tra model đang phục vụ theo thời gian thực.',
  },
  comfy:{
    title:'Hệ thống tạo ảnh / video',
    purpose:'ComfyUI là dịch vụ xử lý các quy trình tạo hình ảnh và một số quy trình video bằng AI.',
    impact:'Khi không kết nối được ComfyUI, các bước tạo ảnh/video phụ thuộc dịch vụ này có thể không chạy; các chức năng khác vẫn có thể hoạt động.',
    note:'Kết nối thành công không đồng nghĩa model, workflow hay khả năng render đã sẵn sàng.',
  },
  vram:{
    title:'Bộ nhớ GPU còn trống',
    purpose:'VRAM là bộ nhớ của card đồ họa dùng để tải và chạy model AI trên máy.',
    impact:'VRAM không đủ có thể khiến tác vụ tạo ảnh/video hoặc chạy model bị lỗi, chậm hoặc không khởi động.',
    note:'Đây chỉ là ảnh chụp tại thời điểm kiểm tra, không phải dung lượng được đảm bảo cho tác vụ tiếp theo.',
  },
  cost:{
    title:'Chi phí sử dụng AI',
    purpose:'Theo dõi chi phí gọi dịch vụ/model AI để kiểm soát ngân sách vận hành.',
    impact:'Nếu chưa đối soát, bạn không thể dùng số liệu ở đây để xác nhận tổng chi phí thực tế.',
    note:'Chưa có dữ liệu không có nghĩa chi phí bằng 0.',
  },
};
function SystemHelpLabel({item}) {
  const info=SYSTEM_HELP[item];
  return <span className="overview-system-label">
    <span>{info.title}</span>
    <Popover trigger={['hover','click']} placement="right" title={info.title}
      content={<div className="overview-system-help">
        <p><strong>Chức năng:</strong> {info.purpose}</p>
        <p><strong>Ảnh hưởng:</strong> {info.impact}</p>
        <p><strong>Lưu ý:</strong> {info.note}</p>
      </div>}>
      <Button type="text" shape="circle" size="small" className="overview-help-button" icon={<InfoCircleOutlined/>} aria-label={`Giải thích: ${info.title}`}/>
    </Popover>
  </span>;
}
function systemState(value) {
  return <span className="overview-system-value">{value}</span>;
}
function comfyState(status) {
  if (status==='COMFYUI_UNAVAILABLE') return 'Không kết nối được';
  if (status==='ACTIVE'||status==='READY'||status==='AVAILABLE') return 'Có phản hồi';
  if (!status||status==='UNKNOWN') return 'Chưa xác định';
  return 'Chưa xác định';
}

export function Overview({data, onNavigate, onRefresh}) {
  const [showAllIssues,setShowAllIssues]=useState(false);
  const [showAllActivity,setShowAllActivity]=useState(false);
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
    <div className="overview-balanced-row">
      <Card className="panel overview-balanced-card" title="Cần bạn xử lý"
        extra={<Button size="small" onClick={onRefresh}>Làm mới</Button>}>
        {!ready?fallback('Chưa có dữ liệu'):issues.length?
          <div className="overview-issues">{issues.slice(0,showAllIssues?issues.length:5).map(item=>
            <div className="overview-issue" key={item.id}>
              <div><strong>{item.title}</strong><div>{badge(item.status)}</div></div>
              <Button size="small" onClick={()=>onNavigate(item.section)}>Mở</Button>
            </div>)}</div>:fallback('Không có mục cần xử lý trong dữ liệu hiện tại')}
        {ready&&issues.length>5&&<Button className="overview-more" type="link" onClick={()=>setShowAllIssues(v=>!v)}>{showAllIssues?'Thu gọn':`Xem thêm ${issues.length-5} mục`}</Button>}
      </Card>
      <Card className="panel overview-balanced-card" title="Hoạt động gần đây"
        extra={<Button size="small" onClick={()=>onNavigate('tasks')}>Lịch sử</Button>}>
        {!ready?fallback('Chưa có dữ liệu'):recent.length?
          <div className="overview-activity">{recent.slice(0,showAllActivity?recent.length:5).map(task=>
            <div className="overview-activity-row" key={task.task_id}>
              <div><strong>{task.skill_id||task.kind||'Tác vụ'}</strong>
                <div className="overview-muted">{formatVietnamDateTime(task.updated_at||task.created_at)}</div></div>
              {badge(task.status)}
            </div>)}</div>:fallback('Chưa có hoạt động')}
        {ready&&recent.length>5&&<Button className="overview-more" type="link" onClick={()=>setShowAllActivity(v=>!v)}>{showAllActivity?'Thu gọn':`Xem thêm ${recent.length-5} hoạt động`}</Button>}
      </Card>
    </div>
    <div className="overview-full-panels">
      <Card className="panel" title="Trạng thái hệ thống">
        <Descriptions size="small" column={1} items={[
          {key:'daemon',label:<SystemHelpLabel item="daemon"/>,children:systemState(!ready?'Chưa có dữ liệu':daemon.fresh?'Có tín hiệu hoạt động':'Chưa ghi nhận hoạt động gần đây')},
          {key:'autopilot',label:<SystemHelpLabel item="autopilot"/>,children:systemState(!ready?'Chưa có dữ liệu':autopilot.enabled?'Đã bật':'Đã tắt')},
          {key:'model',label:<SystemHelpLabel item="model"/>,children:systemState('Chưa kiểm tra')},
          {key:'comfy',label:<SystemHelpLabel item="comfy"/>,children:systemState(motion.loading?'Đang kiểm tra':motion.error?'Không kiểm tra được':comfyState(motion.data?.gpu?.status))},
          {key:'vram',label:<SystemHelpLabel item="vram"/>,children:systemState(typeof motion.data?.gpu?.vram_free_snapshot_gib==='number'?motion.data.gpu.vram_free_snapshot_gib+' GiB':'Chưa có dữ liệu')},
          {key:'cost',label:<SystemHelpLabel item="cost"/>,children:systemState('Chưa có dữ liệu đối soát')},
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
        <div className="overview-legend" aria-label="Chú thích biểu đồ">
          <span className="overview-legend-item"><i className="overview-legend-swatch overview-bar-good" aria-hidden="true"/>Hoàn thành</span>
          <span className="overview-legend-item"><i className="overview-legend-swatch overview-bar-bad" aria-hidden="true"/>Lỗi / gián đoạn</span>
        </div>
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
