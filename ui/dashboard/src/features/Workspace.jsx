import { useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Collapse, Divider, Drawer, Input, Space, Typography } from 'antd';
import { BulbOutlined, CheckCircleOutlined, FolderOpenOutlined, SafetyCertificateOutlined,
  SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { badge, clip, fallback, StatTile } from '../components/shared.jsx';
const { Title, Text } = Typography;
const { TextArea } = Input;

const MIN_PROMPT = 20;
const IDEAS = [
  'Thiết kế landing page nệm ngủ cao cấp, tối ưu điện thoại và có nút gọi nhanh.',
  'Viết storyboard video 30 giây giới thiệu cửa hàng cà phê rang xay thủ công.',
  'Tạo website portfolio tối giản cho nhiếp ảnh gia, tông màu ấm và nhiều khoảng trắng.',
];
const STEPS = [
  [<BulbOutlined key="1"/>, 'Bạn mô tả', 'Nói mục tiêu bằng ngôn ngữ tự nhiên.'],
  [<SafetyCertificateOutlined key="2"/>, 'Bạn duyệt', 'Xem kế hoạch, SHA và quyền cần cấp.'],
  [<ThunderboltOutlined key="3"/>, 'AI thực thi', 'Chỉ chạy sau khi bạn gật đầu.'],
];

function greeting() {
  const h = new Date().getHours();
  if (h < 11) return 'Chào buổi sáng';
  if (h < 14) return 'Chào buổi trưa';
  if (h < 18) return 'Chào buổi chiều';
  return 'Chào buổi tối';
}

export function Workspace({data, onPlan, openGoal, loading}) {
  const [prompt, setPrompt] = useState('');
  const goals = data?.goals || [];
  const waiting = goals.filter(g => ['PLANNED', 'WAITING_APPROVAL'].includes(g.status)).length;
  const done = goals.filter(g => g.status === 'SUCCEEDED').length;
  const length = prompt.trim().length;
  const submit = () => { if (length >= MIN_PROMPT && !loading) onPlan(prompt).then(ok => { if (ok) setPrompt(''); }); };
  return <div className="workspace-page">
    <section className="hero">
      <div className="hero-glow" aria-hidden="true"/>
      <div className="eyebrow"><span className="live-dot"/> {greeting().toUpperCase()}, OWNER</div>
      <h1 className="hero-title">Hôm nay, bạn muốn <em>rèn</em> điều gì?</h1>
      <p className="hero-caption">Mô tả mục tiêu bằng lời của bạn. AgentForge lập kế hoạch và dừng lại chờ bạn duyệt — không tự gọi AI, không tự chi tiền.</p>
      <div className="prompt-composer">
        <TextArea aria-label="Mô tả công việc" autoSize={{minRows:4, maxRows:10}} maxLength={600}
          value={prompt} variant="borderless" onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submit(); }}
          placeholder="Ví dụ: Thiết kế landing page nệm ngủ cao cấp cho ba tôi, tạo hình ảnh đẹp, tối ưu trên điện thoại và có nút gọi 0879547988..."/>
        <div className="composer-footer">
          <span className="composer-hint"><SafetyCertificateOutlined/> Lập kế hoạch miễn phí · Ctrl+Enter để gửi
            {length > 0 && length < MIN_PROMPT && <b> · cần thêm {MIN_PROMPT - length} ký tự</b>}</span>
          <span className="composer-count" aria-live="off">{prompt.length}/600</span>
          <Button type="primary" size="large" icon={<SendOutlined/>} loading={loading}
            disabled={length < MIN_PROMPT} onClick={submit}>Tạo kế hoạch</Button>
        </div>
      </div>
      <div className="idea-row" role="group" aria-label="Gợi ý nhanh">
        <span className="idea-label">Thử nhanh</span>
        {IDEAS.map(text => <button type="button" key={text} className="idea-chip"
          onClick={() => setPrompt(text)}>{text}</button>)}
      </div>
    </section>

    <div className="stat-grid compact">
      <StatTile label="Kế hoạch" value={goals.length} tone="info" hint="Tổng số mục tiêu"/>
      <StatTile label="Chờ duyệt" value={waiting} tone={waiting ? 'warn' : 'good'} hint={waiting ? 'Cần bạn xem xét' : 'Không có gì tồn đọng'}/>
      <StatTile label="Hoàn thành" value={done} tone="good" hint="Đã chạy thành công"/>
    </div>

    <div className="two-cols">
      <Card title="Kế hoạch gần đây" className="panel">
        {goals.length ? goals.slice(0, 8).map(g =>
          <div className="list-line" key={g.goal_id}>
            <div className="list-main"><strong>{g.title}</strong><div className="subtle">{g.template} · {clip(g.goal_id)}</div></div>
            <Space>{badge(g.status)}<Button size="small" onClick={() => openGoal(g.goal_id)}>Xem kế hoạch</Button></Space>
          </div>) : fallback('Chưa có kế hoạch nào — hãy bắt đầu bằng ô phía trên')}
      </Card>
      <Card title="Cách AgentForge làm việc" className="panel">
        <ol className="steps">{STEPS.map(([icon, title, desc], i) =>
          <li key={i}><span className="step-icon">{icon}</span>
            <div><strong>{title}</strong><div className="subtle">{desc}</div></div></li>)}</ol>
        <Divider style={{margin:'14px 0'}}/>
        <div className="feature-row"><CheckCircleOutlined/> Duyệt SHA kế hoạch trước khi gọi model</div>
        <div className="feature-row"><FolderOpenOutlined/> Thành phẩm lưu tại workspace local</div>
        <Text type="secondary" className="subtle">Hiện hỗ trợ website và storyboard. Workflow chuyên sâu nằm trong các mục Dự án, Kinh doanh và Cài đặt.</Text>
      </Card>
    </div>
  </div>;
}

export function GoalDrawer({goal, onClose, onApprove, onExecute, busy, externalEnabled}) {
  const [grants, setGrants] = useState([]);
  const [confirmModel, setConfirmModel] = useState(false);
  const [confirmBrowser, setConfirmBrowser] = useState(false);
  const [confirmProcess, setConfirmProcess] = useState(false);
  useEffect(()=>{setGrants([]);setConfirmModel(false);setConfirmBrowser(false);setConfirmProcess(false);},[goal?.goal_id]);
  if (!goal) return null;
  const required = [...new Set((goal.plan||[]).flatMap(x=>x.required_permissions||[]))];
  const sensitive = required.some(p=>['model.invoke','network.search','network.read','browser.run','process.run'].includes(p));
  const runnable = ['APPROVED','WAITING_APPROVAL'].includes(goal.status);
  return <Drawer title="Kế hoạch & phê duyệt" open={!!goal} onClose={onClose}
    size="min(640px, 96vw)" destroyOnHidden extra={badge(goal.status)}>
    <Title level={4}>{goal.title}</Title>
    <Text type="secondary">{goal.template} · {goal.goal_id}</Text>
    <Divider/>
    <Alert type="info" showIcon message="SHA-256 kế hoạch" description={<code className="digest">{goal.plan_sha256}</code>}/>
    <div className="plan-steps">{(goal.plan||[]).map((step,i)=>
      <div className="plan-step" key={i}>
        <span className="step-number">{i+1}</span>
        <div><strong>{step.skill_id}</strong><div className="subtle">{step.worker_id}</div>
        <Text type="secondary">{(step.required_permissions||[]).join(', ')||'read_only'}</Text></div>
      </div>)}</div>
    <Collapse ghost items={[{key:'1',label:'Xem chi tiết dữ liệu và plan (nâng cao)',
      children:<pre className="source-text">{JSON.stringify({inputs:goal.inputs,plan:goal.plan},null,2)}</pre>}]}/>
    <Divider/>
    {goal.status==='PLANNED' && <Button type="primary" block loading={busy}
      onClick={()=>onApprove(goal)}>Duyệt SHA · chưa chạy AI</Button>}
    {runnable && <>
      <Title level={5}>Quyền cho lần chạy này</Title>
      <Alert type="warning" showIcon message="Phê duyệt riêng từng quyền; không cấp quyền vĩnh viễn."/>
      <Checkbox.Group value={grants} onChange={setGrants}
        options={['workspace.write','workspace.propose','model.invoke','network.search','network.read','browser.run','process.run']
          .map(value=>({label:value,value}))} className="grants"/>
      <Space orientation="vertical" style={{marginTop:16,display:'flex'}}>
        <Checkbox checked={confirmModel} onChange={e=>setConfirmModel(e.target.checked)}>Cho phép gọi model</Checkbox>
        <Checkbox checked={confirmBrowser} onChange={e=>setConfirmBrowser(e.target.checked)}>Cho phép browser</Checkbox>
        <Checkbox checked={confirmProcess} onChange={e=>setConfirmProcess(e.target.checked)}>Cho phép process/FFmpeg</Checkbox>
      </Space>
      {sensitive && !externalEnabled && <Alert type="error" showIcon style={{marginTop:16}}
        message="Server đang khóa external tools. Cần bật khi khởi động backend."/>}
      <Button type="primary" block style={{marginTop:20}} loading={busy}
        disabled={sensitive&&!externalEnabled}
        onClick={()=>onExecute(goal,{grants,confirmModel,confirmBrowser,confirmProcess,sensitive})}>
        {goal.status==='APPROVED'?'Chạy kế hoạch':'Tiếp tục từ approval gate'}
      </Button>
    </>}
  </Drawer>;
}
