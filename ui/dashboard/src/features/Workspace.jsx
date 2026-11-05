import { useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Collapse, Divider, Drawer, Input, Space, Typography } from 'antd';
import { CheckCircleOutlined, FolderOpenOutlined, RobotOutlined, SafetyCertificateOutlined, SendOutlined } from '@ant-design/icons';
import { badge, clip, fallback } from '../components/shared.jsx';
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

export function Workspace({data, onPlan, openGoal, loading}) {
  const [prompt, setPrompt] = useState('');
  const goals = data?.goals || [];
  return <div className="workspace-page">
    <div className="hero">
      <div className="eyebrow"><RobotOutlined/> YOUR AI COMPANY</div>
      <Title className="hero-title">Bạn muốn AgentForge làm gì hôm nay?</Title>
      <Paragraph className="hero-caption">Mô tả mục tiêu bằng lời nói tự nhiên. AI Company sẽ tạo kế hoạch và chờ bạn duyệt trước khi thực hiện.</Paragraph>
      <div className="prompt-composer">
        <TextArea aria-label="Mô tả công việc" rows={5} maxLength={600} showCount value={prompt}
          onChange={e=>setPrompt(e.target.value)}
          placeholder="Ví dụ: Thiết kế landing page nệm ngủ cao cấp cho ba tôi, tạo hình ảnh đẹp, tối ưu trên điện thoại và có nút gọi 0879547988..."/>
        <div className="composer-footer">
          <span><SafetyCertificateOutlined/> Không tự gọi AI hoặc chi tiền khi lập kế hoạch</span>
          <Button type="primary" icon={<SendOutlined/>} loading={loading}
            disabled={prompt.trim().length < 20}
            onClick={()=>onPlan(prompt).then(ok=>{if(ok)setPrompt('');})}>Tạo kế hoạch</Button>
        </div>
      </div>
    </div>
    <div className="two-cols">
      <Card title="Kế hoạch gần đây" className="panel">
        {goals.length ? goals.slice(0,8).map(g=>
          <div className="list-line" key={g.goal_id}>
            <div><strong>{g.title}</strong><div className="subtle">{g.template} · {clip(g.goal_id)}</div></div>
            <Space>{badge(g.status)}<Button size="small" onClick={()=>openGoal(g.goal_id)}>Xem kế hoạch</Button></Space>
          </div>) : fallback('Chưa có kế hoạch nào')}
      </Card>
      <Card title="Kiểm soát trước khi chạy" className="panel">
        <div className="feature-row"><CheckCircleOutlined/> Duyệt kế hoạch SHA trước khi gọi model</div>
        <div className="feature-row"><SafetyCertificateOutlined/> Cấp quyền tạm thời cho từng lượt chạy</div>
        <div className="feature-row"><FolderOpenOutlined/> Thành phẩm ở workspace local</div>
        <Divider/>
        <Text type="secondary">Bản prompt-first hiện hỗ trợ website và storyboard. Các workflow chuyên sâu còn ở Control Center cũ.</Text>
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
    width={640} destroyOnHidden extra={badge(goal.status)}>
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
        options={['workspace.read','workspace.write','workspace.propose','model.invoke','network.search','network.read','browser.run','process.run']
          .map(value=>({label:value,value}))} className="grants"/>
      <Space direction="vertical" style={{marginTop:16,display:'flex'}}>
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

