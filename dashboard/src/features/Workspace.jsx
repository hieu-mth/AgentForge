import { useEffect, useState } from 'react';
import { acceptanceLabel } from '../acceptance.js';
import { AcceptanceStatus } from '../components/AcceptanceStatus.jsx';
import { Alert, Button, Card, Checkbox, Collapse, Divider, Drawer, Input, Space, Typography } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { badge, fallback } from '../components/shared.jsx';
import { PERMISSIONS, WORKERS, SKILLS, requiredPermissions, permissionsKnown, executionConsent } from '../permissions.js';
import { isVideoRequest, quotaForPrompt } from '../workspace_quota.js';
import { promptValidation } from '../prompt_validation.js';
const { Title, Text } = Typography;
const { TextArea } = Input;

const MIN_PROMPT = 20;
const IDEAS = [
  {label:'Tạo website',prompt:'Tạo website bán nệm hiện đại, tối ưu điện thoại, có danh mục sản phẩm, hình ảnh AI và nút liên hệ đặt hàng.'},
  {label:'Xây ứng dụng',prompt:'Tạo ứng dụng React quản lý đơn hàng với danh sách sản phẩm, khách hàng, trạng thái đơn và tìm kiếm.'},
  {label:'Tạo video',prompt:'Làm video quảng cáo 30 giây cho cửa hàng nệm, bắt đầu bằng storyboard có thể duyệt và chỉnh sửa.'},
  {label:'Tạo hình ảnh',prompt:'Tạo bộ hình ảnh quảng cáo nệm phong cách hiện đại, phù hợp đăng website và mạng xã hội.'},
  {label:'Phân tích',prompt:'Phân tích kế hoạch kinh doanh bán nệm, đề xuất cách tăng đơn hàng và các chỉ số cần theo dõi.'},
];
const MIN_PROMPT=20;
const GOAL_STATUS={
  PLANNED:'Chờ duyệt kế hoạch',WAITING_APPROVAL:'Cần bạn duyệt',
  APPROVED:'Sẵn sàng thực hiện',RUNNING:'Đang thực hiện',
  SUCCEEDED:'Đã thực thi',FAILED:'Thực hiện thất bại',
  INTERRUPTED:'Bị gián đoạn',REJECTED:'Đã từ chối',
};
function goalAction(status) {
  if (['PLANNED','WAITING_APPROVAL'].includes(status)) return 'Duyệt kế hoạch';
  if (status==='APPROVED') return 'Tiếp tục thực hiện';
  if (status==='FAILED'||status==='INTERRUPTED') return 'Xem lỗi';
  if (status==='SUCCEEDED') return 'Xem kết quả';
  return 'Xem chi tiết';
}

export function Workspace({data, onPlan, openGoal, onOpenSettings, prompt, setPrompt, loading}) {
  const limits=quotaForPrompt(prompt,data?.workspace_policy);
  const videoIntent=isVideoRequest(prompt);
  const goals=data?.goals||[];
  const validation=promptValidation(prompt);
  const length=validation.characters;
  const [showAll,setShowAll]=useState(false);
  const [showGuide,setShowGuide]=useState(false);
  const submit=()=>{
    if(!validation.error&&!loading&&!limits.blocked) {
      onPlan(prompt).then(ok=>{if(ok)setPrompt('');});
    }
  };
  const countLabel=length.toLocaleString('vi-VN')+'/6.000 ký tự';
  return <div className="workspace-page workspace-owner">
    <section className="hero workspace-owner-hero">
      <div className="eyebrow">WORKSPACE · AGENTFORGE</div>
      <h1 className="hero-title">Giao việc cho <em>đội ngũ AI</em></h1>
      <p className="hero-caption">Mô tả kết quả bạn muốn nhận. AgentForge lập kế hoạch trước, chỉ thực hiện sau khi bạn duyệt.</p>
      <div className="prompt-composer">
        <label className="workspace-prompt-label" htmlFor="workspace-prompt">Bạn muốn AgentForge làm gì?</label>
        <TextArea id="workspace-prompt" aria-label="Mô tả công việc"
          autoSize={{minRows:6,maxRows:14}} value={prompt} variant="borderless"
          onChange={e=>setPrompt(e.target.value)}
          onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();submit();}}}
          placeholder="Ví dụ: Tạo website bán nệm cho gia đình tôi, có ảnh AI, danh sách sản phẩm, nút đặt hàng và giao diện đẹp trên điện thoại..."/>
        <div className="composer-footer">
          <span className="composer-hint">Ctrl + Enter để gửi · Chưa gọi AI ở bước lập kế hoạch</span>
          <span className="composer-count" aria-live="polite">{countLabel}</span>
          <Button type="primary" size="large" icon={<SendOutlined/>} loading={loading}
            disabled={!!validation.error||limits.blocked} onClick={submit}>Lập kế hoạch</Button>
        </div>
      </div>
      {length>0&&validation.error&&<Alert style={{marginTop:12}} type="warning" showIcon message={validation.error}/>}
      {length>0&&!validation.error&&limits.blocked&&<Alert style={{marginTop:12}} type="warning" showIcon
        message="Cần điều chỉnh giới hạn lượt AI"
        description={<Space orientation="vertical" size={8}>
          <Text>Yêu cầu này dự kiến cần {limits.required} lượt model, nhưng cấu hình hiện cho phép {limits.allowed} lượt. Chưa có model nào được gọi.</Text>
          <Button size="small" onClick={onOpenSettings}>Mở cài đặt giới hạn</Button>
        </Space>}/>}
      {length>=MIN_PROMPT&&videoIntent&&<Alert style={{marginTop:12}} type="info" showIcon
        message="Video sẽ bắt đầu bằng storyboard"
        description="Bạn duyệt kịch bản trước; tạo tư liệu và xuất MP4 là những bước riêng có yêu cầu cấp quyền."/>}
      <div className="idea-row" role="group" aria-label="Mẫu yêu cầu">
        <span className="idea-label">Bắt đầu nhanh</span>
        {IDEAS.map(idea=><button type="button" key={idea.label} className="idea-chip"
          onClick={()=>setPrompt(idea.prompt)} title={idea.prompt}>{idea.label}</button>)}
      </div>
      <div className="workspace-help-note">
        <span>Yêu cầu dài được giữ nguyên; kế hoạch lưu trữ có giới hạn riêng và sẽ được backend kiểm tra.</span>
        <Button type="link" size="small" onClick={()=>setShowGuide(v=>!v)}>
          {showGuide?'Ẩn hướng dẫn':'AgentForge hoạt động thế nào?'}
        </Button>
      </div>
      {showGuide&&<div className="workspace-guide">
        <div><strong>1. Bạn mô tả</strong><span>Nêu mục tiêu và tiêu chí thành công.</span></div>
        <div><strong>2. Bạn duyệt</strong><span>Xem kế hoạch, quyền cần cấp và phạm vi tác động.</span></div>
        <div><strong>3. AI thực hiện</strong><span>Chạy từng bước được cho phép; kết quả lưu tại máy local.</span></div>
      </div>}
    </section>
    <Card className="panel workspace-recent" title="Công việc gần đây"
      extra={<span className="workspace-recent-count">{goals.length} kế hoạch trong dữ liệu hiện tại</span>}>
      {goals.length?<>
        {goals.slice(0,showAll?goals.length:5).map(g=><div className="workspace-recent-row" key={g.goal_id}>
          <div className="workspace-recent-main">
            <strong>{g.title||'Công việc chưa có tên'}</strong>
            <span>{GOAL_STATUS[g.status]||'Đang cập nhật trạng thái'}{g.artifact_acceptance?' · '+acceptanceLabel(g.artifact_acceptance.status):''}</span>
          </div>
          <Button size="small" type={['PLANNED','WAITING_APPROVAL'].includes(g.status)?'primary':'default'}
            onClick={()=>openGoal(g.goal_id)}>{goalAction(g.status)}</Button>
        </div>)}
        {goals.length>5&&<Button type="link" className="workspace-show-more" onClick={()=>setShowAll(v=>!v)}>
          {showAll?'Thu gọn':`Xem thêm ${goals.length-5} công việc`}
        </Button>}
      </>:fallback('Chưa có công việc nào. Hãy mô tả mục tiêu ở ô phía trên.')}
    </Card>
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
    {runs.some(step=>step.skill_id==='webapp.review'&&step.status==='SUCCEEDED')&&
      <Button block onClick={()=>onViewResult(goal,'review')}>Xem báo cáo AI Reviewer</Button>}
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
