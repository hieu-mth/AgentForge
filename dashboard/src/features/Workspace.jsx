import { useEffect, useState } from 'react';
import { acceptedCount, acceptanceLabel } from '../acceptance.js';
import { AcceptanceStatus } from '../components/AcceptanceStatus.jsx';
import { Alert, Button, Card, Checkbox, Collapse, Divider, Drawer, Input, Space, Typography } from 'antd';
import { BulbOutlined, CheckCircleOutlined, FolderOpenOutlined, SafetyCertificateOutlined,
  SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { badge, clip, fallback, StatTile } from '../components/shared.jsx';
import { PERMISSIONS, WORKERS, SKILLS, requiredPermissions, permissionsKnown, executionConsent } from '../permissions.js';
import { quotaForPrompt } from '../workspace_quota.js';
const { Title, Text } = Typography;
const { TextArea } = Input;

const MIN_PROMPT = 20;
const IDEAS = [
  'AI Company V5: Tạo ứng dụng quản lý bán hàng React local với bảng sản phẩm, tìm kiếm, lọc và giỏ demo; yêu cầu Architect, Developer, QA và Reviewer phân tích độc lập.',
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

export function Workspace({data, onPlan, openGoal, onOpenSettings, prompt, setPrompt, loading}) {
  const limits = quotaForPrompt(prompt, data?.workspace_policy);
  const goals = data?.goals || [];
  const waiting = goals.filter(g => ['PLANNED', 'WAITING_APPROVAL'].includes(g.status)).length;
  const done = goals.filter(g => g.status === 'SUCCEEDED').length;
  const length = prompt.trim().length;
  const submit = () => {
    if (length >= MIN_PROMPT && !loading && !limits.blocked) {
      onPlan(prompt).then(ok => { if (ok) setPrompt(''); });
    }
  };
  return <div className="workspace-page">
    <section className="hero">
      <div className="hero-glow" aria-hidden="true"/>
      <div className="eyebrow"><span className="live-dot"/> {greeting().toUpperCase()}, OWNER</div>
      <h1 className="hero-title">Hôm nay, bạn muốn <em>rèn</em> điều gì?</h1>
      <p className="hero-caption">Mô tả mục tiêu bằng lời của bạn. AgentForge lập kế hoạch và dừng lại chờ bạn duyệt — không tự gọi AI, không tự chi tiền.</p>
      <div className="prompt-composer">
        <TextArea aria-label="Mô tả công việc" autoSize={{minRows:4, maxRows:10}} maxLength={6000}
          value={prompt} variant="borderless" onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submit(); }}
          placeholder="Ví dụ: Thiết kế landing page nệm ngủ cao cấp cho ba tôi, tạo hình ảnh đẹp, tối ưu trên điện thoại và có nút gọi 0879547988..."/>
        <div className="composer-footer">
          <span className="composer-hint"><SafetyCertificateOutlined/> Lập kế hoạch miễn phí · Ctrl+Enter để gửi
            {length > 0 && length < MIN_PROMPT && <b> · cần thêm {MIN_PROMPT - length} ký tự</b>}</span>
          <span className="composer-count" aria-live="off">{prompt.length.toLocaleString('vi-VN')}/6.000 ký tự</span>
          <Button type="primary" size="large" icon={<SendOutlined/>} loading={loading}
            disabled={length < MIN_PROMPT || limits.blocked} onClick={submit}>Tạo kế hoạch</Button>
        </div>
      </div>
      {length >= MIN_PROMPT && limits.blocked && <Alert
        type="warning" showIcon style={{marginTop:14}}
        message={`Giới hạn Workspace hiện là ${limits.allowed} lượt model/Goal, nhưng yêu cầu cần ${limits.required} lượt`}
        description={<Space direction="vertical" size={8}>
          <Text>{limits.isCompany
            ? 'AI Company V5 cần 3 lượt model: Architect, Developer và Reviewer. QA tĩnh không gọi model.'
            : 'Hãy chỉnh giới hạn cho phép lập kế hoạch trước khi gửi công việc.'}
            {' '}Không có AI nào được gọi; không tự thay đổi chính sách Owner.</Text>
          <Button size="small" onClick={onOpenSettings}>
            Mở Cài đặt → Prompt Workspace
          </Button>
        </Space>}
      />}
      <div className="idea-row" role="group" aria-label="Gợi ý nhanh">
        <span className="idea-label">Thử nhanh</span>
        {IDEAS.map(text => <button type="button" key={text} className="idea-chip"
          onClick={() => setPrompt(text)}>{text}</button>)}
      </div>
    </section>

    <div className="stat-grid compact">
      <StatTile label="Kế hoạch" value={goals.length} tone="info" hint="Tổng số mục tiêu"/>
      <StatTile label="Chờ duyệt" value={waiting} tone={waiting ? 'warn' : 'good'} hint={waiting ? 'Cần bạn xem xét' : 'Không có gì tồn đọng'}/>
      <StatTile label="Đã thực thi" value={done} tone="info" hint="Workflow chạy xong; chưa phải nghiệm thu"/>
      <StatTile label="Đã nghiệm thu" value={acceptedCount(goals)} tone="good" hint="Owner đã chấp nhận sản phẩm"/>
    </div>

    <div className="two-cols">
      <Card title="Kế hoạch gần đây" className="panel">
        {goals.length ? goals.slice(0, 8).map(g =>
          <div className="list-line" key={g.goal_id}>
            <div className="list-main"><strong>{g.title}</strong><div className="subtle">{g.template} · {clip(g.goal_id)}</div></div>
            <Space wrap>{badge(g.status)}{g.artifact_acceptance&&<span>{acceptanceLabel(g.artifact_acceptance.status)}</span>}<Button size="small" onClick={() => openGoal(g.goal_id)}>Xem kế hoạch</Button></Space>
          </div>) : fallback('Chưa có kế hoạch nào — hãy bắt đầu bằng ô phía trên')}
      </Card>
      <Card title="Cách AgentForge làm việc" className="panel">
        <ol className="steps">{STEPS.map(([icon, title, desc], i) =>
          <li key={i}><span className="step-icon">{icon}</span>
            <div><strong>{title}</strong><div className="subtle">{desc}</div></div></li>)}</ol>
        <Divider style={{margin:'14px 0'}}/>
        <div className="feature-row"><CheckCircleOutlined/> Duyệt SHA kế hoạch trước khi gọi model</div>
        <div className="feature-row"><FolderOpenOutlined/> Thành phẩm lưu tại workspace local</div>
        <Text type="secondary" className="subtle">Hiện hỗ trợ website, marketplace React demo, AI Developer tùy biến và AI Company V5 (3 lượt model riêng, cần tăng hạn mức ở Cài đặt). Không tự chạy mã AI. Workflow chuyên sâu nằm trong các mục Dự án, Kinh doanh và Cài đặt.</Text>
      </Card>
    </div>
  </div>;
}

export function GoalDrawer({goal, onClose, onApprove, onExecute, onViewResult, onRetry, busy, externalEnabled}) {
  const [grants, setGrants] = useState([]);
  useEffect(()=>{setGrants([]);},[goal?.goal_id,goal?.current_step]);
  if (!goal) return null;
  const activeIndex = Number.isInteger(goal.current_step) ? goal.current_step : 0;
  const activeStep = goal.plan?.[activeIndex];
  // Explicit consent is scoped to the upcoming stage, not the entire Goal.
  const required = requiredPermissions(activeStep ? [activeStep] : []);
  const known = permissionsKnown(required);
  const consent = executionConsent(required, grants);
  const complete = known && required.every(permission=>grants.includes(permission));
  const sensitive = consent.sensitive;
  const runnable = ['APPROVED','WAITING_APPROVAL'].includes(goal.status);
  const runs = goal.step_runs||[];
  const failedStep = goal.status==='FAILED'
    ? runs.find(step=>step.step_index===activeIndex && step.status==='FAILED' && step.child_task_id)
    : null;
  const developerReady = runs.some(step=>step.skill_id==='webapp.develop' && step.status==='SUCCEEDED');
  return <Drawer title="Kế hoạch & phê duyệt" open={!!goal} onClose={onClose}
    size="min(640px, 96vw)" destroyOnHidden extra={badge(goal.status)}>
    <Title level={4}>{goal.title}</Title>
    <AcceptanceStatus acceptance={goal.artifact_acceptance}/>
    <Text type="secondary">{goal.template} · {goal.goal_id}</Text>
    <Divider/>
    {['FAILED','INTERRUPTED'].includes(goal.status) && <Alert type="error" showIcon
      style={{marginBottom:16}} message="Thực thi chưa thành công"
      description={goal.execution_error||goal.error||'Xem Task History để kiểm tra nguyên nhân.'}/>}
    <Alert type="info" showIcon message="SHA-256 kế hoạch" description={<code className="digest">{goal.plan_sha256}</code>}/>
    <div className="plan-steps">{(goal.plan||[]).map((step,i)=>
      <div className="plan-step" key={i}>
        <span className="step-number">{i+1}</span>
        <div><strong>{SKILLS[step.skill_id]||step.skill_id}</strong>
        <div className="subtle">{runs.find(run=>run.step_index===i)?.status|| (i===activeIndex?'Chờ chạy':'Chưa tới bước')}{i===activeIndex&&runnable?' · BƯỚC ĐANG CHỜ BẠN DUYỆT':''}</div>
        <div className="subtle">{WORKERS[step.worker_id]||step.worker_id}</div>
        <Text type="secondary">{(step.required_permissions||[]).map(p=>PERMISSIONS[p]?.title||p).join(' · ')||'Chỉ đọc dữ liệu'}</Text>
        <Collapse ghost size="small" items={[{key:'technical',label:'Thông tin kỹ thuật',
          children:<Text code>{step.skill_id} · {step.worker_id}</Text>}]}/></div>
      </div>)}</div>
    <Collapse ghost items={[{key:'1',label:'Xem chi tiết dữ liệu và plan (nâng cao)',
      children:<pre className="source-text">{JSON.stringify({inputs:goal.inputs,plan:goal.plan},null,2)}</pre>}]}/>
    <Divider/>
    {developerReady&&<Button type="primary" block onClick={()=>onViewResult(goal)}>
      Xem source sản phẩm ngay (Developer đã tạo xong)
    </Button>}
    {goal.status==='SUCCEEDED'&&!developerReady&&<Button type="primary" block
      onClick={()=>onViewResult(goal)}>Xem kết quả công việc</Button>}
    {failedStep&&<Alert type="warning" showIcon style={{marginTop:12}}
      message={`Bước ${activeIndex+1} thất bại: ${SKILLS[activeStep?.skill_id]||activeStep?.skill_id}`}
      description={<Space orientation="vertical">
        <Text>Chỉ bước thất bại được chạy lại. Các bước đã thành công được giữ nguyên. Lần gọi model tiếp theo vẫn cần cấp quyền riêng.</Text>
        <Button loading={busy} onClick={()=>onRetry(goal,failedStep)}>Chuẩn bị chạy lại bước {activeIndex+1}</Button>
      </Space>}/>}
    {goal.status==='PLANNED' && <Button type="primary" block loading={busy}
      onClick={()=>onApprove(goal)}>Duyệt SHA · chưa chạy AI</Button>}
    {runnable && <>
      <Title level={5}>Đang duyệt bước {activeIndex+1}/{goal.plan?.length}: {SKILLS[activeStep?.skill_id]||activeStep?.skill_id}</Title>
      <Alert type="info" showIcon
        message={activeStep?.estimated_model_calls ? 'Bước này có gọi model AI' : 'Bước này không yêu cầu lượt model'}
        description={`Chỉ cấp quyền cho bước ${activeIndex+1}. Không duyệt thay các bước tiếp theo.`}/>
      <Alert type="info" showIcon message="Chỉ yêu cầu quyền có trong kế hoạch đã duyệt"
        description="Các quyền chỉ có hiệu lực trong lượt chạy này. Bạn có thể bỏ chọn để chưa chạy."/>
      {!known && <Alert type="error" showIcon style={{marginTop:12}}
        message="Có quyền mới chưa được giải thích — không thể thực thi"
        description="Cần cập nhật giao diện để hiển thị đầy đủ quyền trước khi duyệt."/>}
      <div className="permission-list">
        {required.length===0 && <Text type="secondary">Công việc này chỉ đọc dữ liệu, không cần cấp thêm quyền.</Text>}
        {required.map(permission=>{
          const info=PERMISSIONS[permission];
          return <div className="permission-item" key={permission}>
            <Checkbox checked={grants.includes(permission)} disabled={!info}
              onChange={e=>setGrants(previous=>e.target.checked
                ? [...new Set([...previous,permission])]
                : previous.filter(value=>value!==permission))}/>
            <span className="permission-copy">
              <strong>{info?.title||'Quyền chưa xác định'}</strong>
              <span>{info?.description||'Không thể cho phép khi chưa rõ tác động.'}</span>
              <small>{info?.impact||'Cần xác minh'} · <code>{permission}</code></small>
            </span>
          </div>;
        })}
      </div>
      {goal.template==='webapp.company'&&<Alert type="warning" showIcon
        message="V5: duyệt từng lượt model riêng"
        description="Quy trình có 3 lượt model được tính vào kế hoạch; mỗi lần nhấn Chạy/Tiếp tục chỉ xác nhận tối đa 1 lượt. QA ở bước 3 chỉ kiểm tra tĩnh, không build hoặc chạy trình duyệt."/>}
      {required.includes('model.invoke')&&<Alert type="warning" showIcon
        message="AI local hay cloud?"
        description="AgentForge dùng model đang cấu hình trong backend. Nếu cấu hình cloud, nội dung gửi tới nhà cung cấp có thể có chi phí; việc tick quyền này cũng là xác nhận gọi model cho lượt chạy."/>}
      {sensitive && !externalEnabled && <Alert type="error" showIcon style={{marginTop:16}}
        message="Server đang khóa công cụ ngoài"
        description="Cần bật quyền ở backend trước khi thực thi. Không thể mở khóa bằng cách tick checkbox."/>}
      <Button type="primary" block style={{marginTop:20}} loading={busy}
        disabled={!complete||(sensitive&&!externalEnabled)}
        onClick={()=>onExecute(goal,consent)}>
        {goal.status==='APPROVED'?'Chạy bước '+(activeIndex+1)+': ':'Tiếp tục bước '+(activeIndex+1)+': '}{SKILLS[activeStep?.skill_id]||activeStep?.skill_id}
      </Button>
      {!complete && known && required.length>0 &&
        <Text type="secondary" className="subtle">Hãy đọc và chọn đủ {required.length} quyền được yêu cầu trước khi chạy.</Text>}
    </>}
  </Drawer>;
}
