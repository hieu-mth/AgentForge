import { useEffect, useState } from 'react';
import { acceptanceLabel } from '../acceptance.js';
import { AcceptanceStatus } from '../components/AcceptanceStatus.jsx';
import { Alert, Button, Card, Checkbox, Collapse, Drawer, Input, Space, Typography } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { badge, fallback } from '../components/shared.jsx';
import { PERMISSIONS, WORKERS, SKILLS, requiredPermissions, permissionsKnown, executionConsent } from '../permissions.js';
import { isVideoRequest, quotaForPrompt } from '../workspace_quota.js';
import {api} from '../api.js';
import {useReadSequence} from '../use_resource.jsx';
import { promptValidation } from '../prompt_validation.js';
const { Title, Text } = Typography;
const { TextArea } = Input;

const IDEAS = [
  {label:"Lưu báo cáo Markdown",prompt:"Tạo báo cáo workspace/e2e-test/report.md với nội dung: # Kiểm tra báo cáo local"},
  {label:'Tạo website',prompt:'Tạo website bán nệm hiện đại, tối ưu điện thoại, có danh mục sản phẩm, hình ảnh AI và nút liên hệ đặt hàng.'},
  {label:'Xây ứng dụng',prompt:'Tạo ứng dụng React tùy biến quản lý đơn hàng với danh sách sản phẩm, khách hàng, trạng thái đơn và tìm kiếm.'},
  {label:'Tạo video',prompt:'Làm video quảng cáo 30 giây cho cửa hàng nệm, bắt đầu bằng storyboard có thể duyệt và chỉnh sửa.'},
];
const MIN_PROMPT=20;
const GOAL_STATUS={
  PLANNED:'Chờ duyệt kế hoạch',WAITING_APPROVAL:'Cần bạn duyệt',
  APPROVED:'Sẵn sàng thực hiện',RUNNING:'Đang thực hiện',
  SUCCEEDED:'Đã thực thi',FAILED:'Thực hiện thất bại',
  INTERRUPTED:'Bị gián đoạn',REJECTED:'Đã từ chối',
};
export function goalAction(status) {
  if (status==='PLANNED') return 'Duyệt kế hoạch';
  if (status==='WAITING_APPROVAL') return 'Duyệt bước tiếp theo';
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
      onPlan(prompt).then(ok=>{if(ok)setPrompt(current=>current===prompt?'':current);});
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

function StepCapabilities({goalId}) {
  const [status,setStatus]=useState(null);
  const [loading,setLoading]=useState(false);
  const begin=useReadSequence();
  const check=async()=>{
    const current=begin();
    setLoading(true);
    setStatus(null);
    try {
      const result=await api('/api/goals/'+goalId+'/capabilities');
      if(current())setStatus(result);
    } catch {
      if(current())setStatus({status:'ERROR'});
    } finally {
      if(current())setLoading(false);
    }
  };
  return <Space wrap>
    <Button onClick={check} loading={loading}>Kiểm tra năng lực bước hiện tại</Button>
    {status&&<Text type="secondary">
      {badge(status.status)} {status.model} {status.loadability&&'· Chưa thử nạp model'}
    </Text>}
  </Space>;
}

const STEP_STATUS={SUCCEEDED:'Hoàn thành',FAILED:'Thất bại',RUNNING:'Đang chạy',WAITING_APPROVAL:'Chờ duyệt',APPROVED:'Đã duyệt',PLANNED:'Chưa chạy',INTERRUPTED:'Gián đoạn'};
export function GoalDrawer({goal, onClose, onApprove, onExecute, onViewResult, onRetry, busy, externalEnabled}) {
  const [grants,setGrants]=useState([]);
  useEffect(()=>{setGrants([]);},[goal?.goal_id,goal?.updated_at]);
  if(!goal)return null;
  const steps=goal.plan||[];
  const activeIndex=Number.isInteger(goal.current_step)?goal.current_step:0;
  const activeStep=steps[activeIndex];
  const runs=goal.step_runs||[];
  const required=requiredPermissions(activeStep?[activeStep]:[]);
  const known=permissionsKnown(required);
  const consent=executionConsent(required,grants);
  const complete=known&&required.every(permission=>grants.includes(permission));
  const sensitive=executionConsent(required,required).sensitive;
  const runnable=['APPROVED','WAITING_APPROVAL'].includes(goal.status);
  const failedStep=goal.status==='FAILED'&&['webapp.company','creative.storyboard'].includes(goal.template)
    ?runs.find(step=>step.step_index===activeIndex&&step.status==='FAILED'&&step.child_task_id):null;
  const developerReady=runs.some(step=>step.skill_id==='webapp.develop'&&step.status==='SUCCEEDED');
  const reviewerReady=runs.some(step=>step.skill_id==='webapp.review'&&step.status==='SUCCEEDED');
  const canRun=Boolean(activeStep&&goal.updated_at)&&complete&&(!sensitive||externalEnabled);
  const statusFor=(step,i)=>{
    const run=runs.find(item=>item.step_index===i);
    return STEP_STATUS[run?.status]|| (i===activeIndex&&runnable?'Cần bạn duyệt':i<activeIndex?'Đã qua bước':'Chưa thực hiện');
  };
  const action=goal.status==='PLANNED'
    ?<Button type="primary" block loading={busy} onClick={()=>onApprove(goal)}>Duyệt kế hoạch · chưa chạy AI</Button>
    :runnable?<Button type="primary" block loading={busy} disabled={!canRun}
      onClick={()=>onExecute(goal,consent)}>
      {goal.status==='APPROVED'?'Chạy':'Tiếp tục'} bước {activeIndex+1}: {SKILLS[activeStep?.skill_id]||activeStep?.skill_id}
    </Button>
    :failedStep?<Button block loading={busy} onClick={()=>onRetry(goal,failedStep)}>Chuẩn bị chạy lại bước {activeIndex+1}</Button>
    :null;
  return <Drawer title="Kế hoạch & phê duyệt" open={!!goal} onClose={onClose}
    size="min(680px, 100vw)" destroyOnHidden className="goal-owner-drawer"
    extra={badge(goal.status)}
    footer={action&&<div className="goal-owner-footer">
      <div className="goal-owner-footer-hint">{goal.status==='PLANNED'
        ?'Duyệt SHA kế hoạch; chưa cấp quyền thực thi.'
        :runnable?'Chỉ cấp quyền cho bước hiện tại. Mỗi bước cần được xác nhận riêng.'
        :'Chỉ chuẩn bị chạy lại bước thất bại.'}</div>
      {action}
      {runnable&&!canRun&&<Text type="secondary" className="subtle">
        {!activeStep||!goal.updated_at?'Chưa tải được thông tin bước. Hãy mở lại kế hoạch.'
          :!known?'Có quyền chưa được nhận diện. Không thể thực thi.'
          :sensitive&&!externalEnabled?'Backend đang khóa công cụ ngoài.'
          :'Hãy chọn đủ quyền được yêu cầu trước khi chạy.'}</Text>}
    </div>}>
    <div className="goal-owner-body">
      <section className="goal-owner-section">
        <Title level={4} className="goal-owner-title">{goal.title}</Title>
        <div className="goal-owner-summary">
          {badge(goal.status)}
          <Text type="secondary">Bước {Math.min(activeIndex+1,steps.length)}/{steps.length}</Text>
        </div>
        <AcceptanceStatus acceptance={goal.artifact_acceptance}/>
        {activeStep&&<StepCapabilities key={goal.goal_id+goal.updated_at} goalId={goal.goal_id}/>}
        {['FAILED','INTERRUPTED'].includes(goal.status)&&<Alert type="error" showIcon
          message="Thực thi chưa thành công"
          description={goal.execution_error||goal.error||'Xem Lịch sử tác vụ để kiểm tra nguyên nhân.'}/>}
      </section>
      <section className="goal-owner-section">
        <h3>Tiến độ thực hiện</h3>
        <div className="goal-owner-progress" role="list" aria-label="Tiến độ kế hoạch">
          {steps.map((step,i)=><span key={i} role="listitem"
            className={'goal-owner-progress-bar '+(runs.some(run=>run.step_index===i&&run.status==='SUCCEEDED')?'done':i===activeIndex?'active':'')}
            title={`Bước ${i+1}: ${statusFor(step,i)}`}/>)}
        </div>
        <div className="goal-owner-steps">
          {steps.map((step,i)=><div className={'goal-owner-step '+(i===activeIndex?'current':'')} key={i}>
            <span className="goal-owner-step-number">{i+1}</span>
            <div className="goal-owner-step-content">
              <strong>{SKILLS[step.skill_id]||step.skill_id}</strong>
              <span>{statusFor(step,i)} · {WORKERS[step.worker_id]||step.worker_id}</span>
              {i===activeIndex&&<small>{(step.required_permissions||[]).map(p=>PERMISSIONS[p]?.title||p).join(' · ')||'Chỉ đọc dữ liệu'}</small>}
            </div>
          </div>)}
        </div>
      </section>
      {(goal.status==='PLANNED'||runnable||failedStep)&&<section className="goal-owner-section">
        <h3>{goal.status==='PLANNED'?'Phê duyệt kế hoạch':failedStep?'Xử lý bước thất bại':'Phê duyệt bước hiện tại'}</h3>
        {goal.status==='PLANNED'&&<Text type="secondary">Duyệt bản kế hoạch theo SHA trước khi thực hiện. Sau đó, từng bước vẫn cần cấp quyền riêng.</Text>}
        {failedStep&&<Alert type="warning" showIcon message={`Bước ${activeIndex+1} thất bại`}
          description="Chỉ chuẩn bị chạy lại bước thất bại; các bước thành công được giữ nguyên. Lần gọi AI tiếp theo vẫn cần duyệt riêng."/>}
        {runnable&&<>
          <Text type="secondary">Bước {activeIndex+1}: {SKILLS[activeStep?.skill_id]||activeStep?.skill_id}. {activeStep?.estimated_model_calls?'Có sử dụng lượt model AI.':'Không yêu cầu lượt model.'}</Text>
          {!known&&<Alert type="error" showIcon message="Có quyền chưa được giải thích — không thể thực thi"/>}
          <div className="permission-list">
            {required.length===0&&<Text type="secondary">Chỉ đọc dữ liệu; không cần cấp thêm quyền.</Text>}
            {required.map(permission=>{
              const info=PERMISSIONS[permission];
              return <div className="permission-item" key={permission}>
                <Checkbox aria-label={info?.title||permission} checked={grants.includes(permission)} disabled={!info}
                  onChange={e=>setGrants(previous=>e.target.checked
                    ?[...new Set([...previous,permission])]
                    :previous.filter(value=>value!==permission))}/>
                <span className="permission-copy">
                  <strong>{info?.title||'Quyền chưa xác định'}</strong>
                  <span>{info?.description||'Không thể cho phép khi chưa rõ tác động.'}</span>
                  <small>{info?.impact||'Cần xác minh'} · <code>{permission}</code></small>
                </span>
              </div>;
            })}
          </div>
          {goal.template==='webapp.company'&&<Alert type="warning" showIcon
            message="V5: mỗi lượt model cần duyệt riêng"
            description="Quy trình dự kiến 3 lượt model: Architect, Developer và Reviewer. Mỗi lần Chạy/Tiếp tục chỉ duyệt tối đa một lượt; QA tĩnh không build hoặc chạy trình duyệt."/>}
          {required.includes('model.invoke')&&<Alert type="warning" showIcon
            message="Model local hoặc cloud"
            description="Backend quyết định model theo cấu hình. Nếu dùng cloud, dữ liệu có thể được gửi tới nhà cung cấp và phát sinh chi phí; chọn quyền này đồng thời xác nhận gọi model cho lượt chạy."/>}
          {sensitive&&!externalEnabled&&<Alert type="error" showIcon
            message="Backend đang khóa công cụ ngoài"
            description="Không thể mở khóa bằng checkbox; cần bật quyền tại backend."/>}
        </>}
      </section>}
      {(developerReady||reviewerReady||(goal.status==='SUCCEEDED'&&!developerReady))&&<section className="goal-owner-section">
        <h3>Kết quả & báo cáo</h3>
        <Space wrap>
          {developerReady&&<Button onClick={()=>onViewResult(goal)}>Xem source sản phẩm</Button>}
          {reviewerReady&&<Button onClick={()=>onViewResult(goal,'review')}>Xem báo cáo Reviewer</Button>}
          {goal.status==='SUCCEEDED'&&!developerReady&&<Button onClick={()=>onViewResult(goal)}>Xem kết quả công việc</Button>}
        </Space>
      </section>}
      <Collapse ghost className="goal-owner-technical" items={[{key:'technical',label:'Thông tin kỹ thuật · SHA, ID và dữ liệu kế hoạch',
        children:<div className="goal-owner-technical-content">
          <Text type="secondary">SHA-256 kế hoạch</Text>
          <code className="digest">{goal.plan_sha256}</code>
          <Text type="secondary">Template: {goal.template} · Goal ID: {goal.goal_id}</Text>
          <pre className="source-text">{JSON.stringify({inputs:goal.inputs,plan:goal.plan},null,2)}</pre>
        </div>}]}/>
    </div>
  </Drawer>;
}
