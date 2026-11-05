import { useCallback, useEffect, useMemo, useState } from 'react';
import { App as AntApp, Alert, Badge, Button, Card, Checkbox, Collapse, ConfigProvider,
  Descriptions, Divider, Drawer, Empty, Form, Input, Layout, Menu, Modal,
  Segmented, Select, Space, Spin, Statistic, Table, Tag, Typography } from 'antd';
import {
  AppstoreOutlined, AuditOutlined, BarChartOutlined, CheckCircleOutlined,
  ClockCircleOutlined, CodeOutlined, DashboardOutlined, FileTextOutlined,
  FolderOpenOutlined, GlobalOutlined, LogoutOutlined, MenuFoldOutlined,
  MenuUnfoldOutlined, PlayCircleOutlined, ReloadOutlined, RobotOutlined,
  SafetyCertificateOutlined, SendOutlined, SettingOutlined, TeamOutlined,
} from '@ant-design/icons';
import { api } from './api.js';

const { Header, Sider, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

function stateColor(status) {
  if (['SUCCEEDED', 'ACTIVE', 'APPROVED', 'ATTACHED', 'PASS_HEURISTIC'].includes(status)) return 'green';
  if (['FAILED', 'INTERRUPTED', 'REJECTED'].includes(status)) return 'red';
  if (['PLANNED', 'WAITING_APPROVAL', 'PENDING', 'PROPOSED_NOT_APPLIED'].includes(status)) return 'gold';
  return 'blue';
}
const badge = value => <Tag color={stateColor(value)}>{value || 'UNKNOWN'}</Tag>;
const clip = id => String(id || '').slice(0, 12);
const needPreviewId = id => /^[a-f0-9]{32}$/.test(String(id || ''));
const fallback = text => <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={text}/>;

function ErrorBoundary({error, onReset}) {
  if (!error) return null;
  return <Alert type="error" showIcon closable onClose={onReset} message="Không thể hoàn thành"
    description={error.message || String(error)} style={{marginBottom:20}}/>;
}

function Login({onLogin, busy}) {
  return <div className="login-screen">
    <Card className="login-card" bordered={false}>
      <div className="brand-large"><span className="brand-glyph">A</span> AgentForge</div>
      <Tag color="blue">LOCAL-FIRST · OWNER ACCESS</Tag>
      <Title level={2} style={{marginTop:22,marginBottom:8}}>Chào mừng trở lại.</Title>
      <Paragraph type="secondary">Điều hành AI Company trên máy của bạn. Nhập mã Owner được hiển thị trong PowerShell; mã này không được lưu trên trình duyệt.</Paragraph>
      <Form layout="vertical" onFinish={onLogin}>
        <Form.Item label="Mã Owner" name="code" rules={[{required:true, min:12}]}>
          <Input.Password autoComplete="off" placeholder="Mã phiên đăng nhập"/>
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={busy} block>Vào Workspace</Button>
      </Form>
    </Card>
  </div>;
}

function Workspace({data, onPlan, openGoal, loading}) {
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

function GoalDrawer({goal, onClose, onApprove, onExecute, busy, externalEnabled}) {
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
        options={['workspace.write','workspace.propose','model.invoke','network.search','network.read','browser.run','process.run']
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

function Websites({data, showProposal}) {
  const proposals=(data?.tasks||[]).filter(x=>x.web_proposal);
  return <Card title="Landing page AI" extra={<Text type="secondary">Chỉ duyệt sau khi xem bản preview</Text>}>
    <Table rowKey={x=>x.task_id} pagination={{pageSize:8}} dataSource={proposals}
      locale={{emptyText:'Chưa có bản nháp website.'}} columns={[
        {title:'Project',render:(_,t)=><b>{t.web_proposal.slug}</b>},
        {title:'Proposal',render:(_,t)=><code>{clip(t.web_proposal.proposal_id)}</code>},
        {title:'Trạng thái',render:()=>badge('PROPOSED_NOT_APPLIED')},
        {title:'Hành động',render:(_,t)=><Button type="primary" ghost
          onClick={()=>showProposal(t.web_proposal.proposal_id)}>Xem website</Button>},
      ]}/>
  </Card>;
}

function ProposalDrawer({proposal, onClose, onRevise, onApply, busy}) {
  const [device,setDevice]=useState('desktop');
  const [feedback,setFeedback]=useState('');
  useEffect(()=>{setFeedback('');setDevice('desktop');},[proposal?.proposal_id]);
  if (!proposal) return null;
  const id=proposal.proposal_id, allowed=needPreviewId(id);
  return <Drawer title="Xem trước & phê duyệt website" open={!!proposal} onClose={onClose}
    width="min(1120px, 96vw)" destroyOnHidden extra={badge(proposal.status)}>
    <Space direction="vertical" style={{width:'100%'}} size={18}>
      <div className="preview-toolbar">
        <div><Title level={4} style={{marginBottom:0}}>{proposal.project_slug}</Title>
          <Text type="secondary">Bản nháp được cách ly, không chạy script hoặc tải tài nguyên ngoài</Text></div>
        <Segmented options={[{label:'Desktop',value:'desktop'},{label:'Mobile',value:'mobile'}]}
          value={device} onChange={setDevice}/>
      </div>
      <div className="preview-stage">
        {allowed ? <iframe className={'preview-iframe '+(device==='mobile'?'mobile':'desktop')}
          title={'Xem trước website '+proposal.project_slug} sandbox=""
          referrerPolicy="no-referrer" src={'/api/proposals/'+id+'/preview'}/> :
          <Alert type="error" message="Proposal ID không hợp lệ"/>}
      </div>
      <Collapse items={[{key:'source',label:'Mã nguồn và SHA (nâng cao)',
        children:<>
          <Text code className="digest">{proposal.sha256}</Text>
          {(proposal.files||[]).map(f=><div key={f.path}><Text strong>{f.path}</Text>
            <pre className="source-text">{f.content}</pre></div>)}
        </>} ]}/>
      <Card size="small" className="feedback-card">
        <Title level={5}>Chưa ưng? Yêu cầu AI chỉnh sửa</Title>
        <Paragraph type="secondary">Góp ý sẽ tạo bản kế hoạch mới để duyệt; proposal cũ được giữ nguyên.</Paragraph>
        <TextArea rows={3} maxLength={360} showCount value={feedback}
          onChange={e=>setFeedback(e.target.value)}
          placeholder="Ví dụ: Hero nhìn còn thô, thay bố cục cho sang trọng hơn, có hình ảnh nệm và CTA rõ ràng trên điện thoại..."/>
        <Space wrap style={{marginTop:20,justifyContent:'flex-end',width:'100%'}}>
          <Button loading={busy} disabled={feedback.trim().length<10}
            onClick={()=>onRevise(proposal,feedback)}>Yêu cầu chỉnh sửa</Button>
          <Button type="primary" loading={busy} onClick={()=>onApply(proposal)}>
            Duyệt & lưu website local</Button>
        </Space>
      </Card>
    </Space>
  </Drawer>;
}

function Overview({data, onNavigate}) {
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

function ReadOnlyPage({section,data}) {
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

export default function App() {
  const {message,modal} = AntApp.useApp();
  const [csrf,setCsrf]=useState(null);
  const [data,setData]=useState(null);
  const [loginNeeded,setLoginNeeded]=useState(false);
  const [section,setSection]=useState('workspace');
  const [goal,setGoal]=useState(null);
  const [proposal,setProposal]=useState(null);
  const [task,setTask]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState(null);
  const [collapsed,setCollapsed]=useState(false);
  const authError = err => {
    if (err.status===401) {setLoginNeeded(true);setData(null);setCsrf(null);}
    else {setError(err);message.error(err.message || 'API error');}
  };
  const refresh=useCallback(async()=>{
    const [session,bootstrap] = await Promise.all([api('/api/session'),api('/api/bootstrap')]);
    setCsrf(session.csrf);setData(bootstrap);setLoginNeeded(false);
  },[]);
  useEffect(()=>{refresh().catch(e=>{if(e.status===401)setLoginNeeded(true);else setError(e);});},[refresh]);
  const runAction=async(fn,{refreshData=true}={})=>{
    setBusy(true);setError(null);
    try{const result=await fn();if(refreshData)await refresh();return result;}
    catch(e){authError(e);return null;}
    finally{setBusy(false);}
  };
  const post=(path,body)=>api(path,{method:'POST',body,csrf});
  const ask=(title,content,onOk)=>modal.confirm({title,content,okText:'Xác nhận',cancelText:'Hủy',onOk});
  const openGoal=async id => {
    try{setGoal(await api('/api/goals/'+encodeURIComponent(id)));}catch(e){authError(e);}
  };
  const plan=async prompt => {
    const outcome=await runAction(()=>post('/api/workspace/request',
      {ack:'PLAN_ONLY',prompt,max_model_calls:1}));
    if(!outcome)return false;
    if(outcome.status==='NEEDS_CLARIFICATION'){message.warning(outcome.message);return false;}
    message.success('Đã lập kế hoạch, chưa gọi model');await openGoal(outcome.goal_id);return true;
  };
  const approve=goal=>ask('Duyệt SHA kế hoạch?',
    <><Paragraph>Hành động này chỉ duyệt kế hoạch, chưa gọi model hoặc chạy skill.</Paragraph>
      <code className="digest">{goal.plan_sha256}</code></>,
    async()=>{const out=await runAction(()=>post('/api/goals/'+goal.goal_id+'/approve',
      {ack:'APPROVE',plan_sha256:goal.plan_sha256}));
      if(out){message.success('Đã duyệt');await openGoal(goal.goal_id);}});
  const execute=(goal,permissions)=>ask('Cho phép thực thi Goal này?',
    <><Paragraph>Chỉ cấp quyền trong lượt chạy này. Có thể gọi model hoặc tiến trình ngoài nếu bạn đã bật.</Paragraph>
      <Paragraph>Grants: {permissions.grants.join(', ')||'read-only'}</Paragraph>
      {permissions.sensitive&&<Alert type="warning" message="Có quyền model/network/process — kiểm tra trước khi duyệt"/>}</>,
    async()=>{const action=goal.status==='APPROVED'?'run':'resume';
      const payload={ack:action.toUpperCase(),plan_sha256:goal.plan_sha256,
        grants:permissions.grants,confirm_model_call:permissions.confirmModel,
        confirm_browser_run:permissions.confirmBrowser,confirm_external_run:permissions.confirmProcess,
        ack_external:permissions.sensitive?'AUTHORIZE_EXTERNAL_TOOLS':''};
      const out=await runAction(()=>post('/api/goals/'+goal.goal_id+'/'+action,payload));
      if(out){message.success('Trạng thái: '+out.status);await openGoal(goal.goal_id);}});
  const openProposal=async id => {
    try{setProposal(await api('/api/proposals/'+encodeURIComponent(id)));}
    catch(e){authError(e);}
  };
  const revise=(p,feedback)=>ask('Tạo kế hoạch chỉnh sửa?',
    'Đề xuất cũ được giữ nguyên. Bạn sẽ duyệt kế hoạch mới trước khi gọi model.',
    async()=>{const out=await runAction(()=>post('/api/proposals/'+p.proposal_id+'/revision',
      {ack:'REQUEST_REVISION',sha256:p.sha256,feedback:feedback.trim()}));
      if(out){setProposal(null);message.success('Đã tạo yêu cầu sửa');await openGoal(out.goal_id);}});
  const apply=p=>ask('Duyệt & lưu website local?',
    <><Paragraph>SHA: <code className="digest">{p.sha256}</code></Paragraph>
      <Text type="secondary">Không tự deploy website hoặc ghi đè dự án khác.</Text></>,
    async()=>{const out=await runAction(()=>post('/api/proposals/'+p.proposal_id+'/apply',
      {ack:'APPLY_PROPOSAL',sha256:p.sha256}));
      if(out){setProposal(null);message.success('Đã lưu vào workspace/products');}});
  const menuItems=[
    {key:'workspace',icon:<RobotOutlined/>,label:'Giao việc'},
    {key:'overview',icon:<DashboardOutlined/>,label:'Tổng quan'},
    {key:'goals',icon:<AuditOutlined/>,label:'Goals'},
    {key:'tasks',icon:<ClockCircleOutlined/>,label:'Tasks'},
    {key:'websites',icon:<GlobalOutlined/>,label:'Websites'},
    {key:'projects',icon:<FolderOpenOutlined/>,label:'Projects & Files'},
    {type:'divider'},
    {key:'team',icon:<TeamOutlined/>,label:'Team & Roles'},
    {key:'channels',icon:<PlayCircleOutlined/>,label:'Channels'},
    {key:'finance',icon:<BarChartOutlined/>,label:'Finance'},
    {key:'settings',icon:<SettingOutlined/>,label:'Settings'},
  ];
  const titles={workspace:'Giao việc',overview:'Tổng quan',goals:'Kế hoạch',tasks:'Task History',
    websites:'Websites',projects:'Projects & Files',team:'Team & Roles',channels:'Channels',
    finance:'Finance',settings:'Settings'};
  if(loginNeeded)return <><Login onLogin={async({code})=>{
    await runAction(async()=>{await api('/api/login',{method:'POST',body:{code}});await refresh();},
      {refreshData:false});}} busy={busy}/><ErrorBoundary error={error} onReset={()=>setError(null)}/></>;
  if(!data)return <div className="loading-screen"><Spin size="large"/><Text type="secondary">Đang kết nối AgentForge…</Text><ErrorBoundary error={error} onReset={()=>setError(null)}/></div>;
  const title = titles[section] || 'Dashboard';
  const goals = data.goals||[], tasks=data.tasks||[];
  return <Layout className="app-shell">
    <Sider theme="light" collapsible collapsed={collapsed} onCollapse={setCollapsed}
      breakpoint="lg" width={242} className="app-sider">
      <div className="brand"><span className="brand-glyph">A</span>{!collapsed&&<div><strong>AgentForge</strong><small>AI COMPANY</small></div>}</div>
      <Menu theme="light" mode="inline" items={menuItems} selectedKeys={[section]}
        onClick={e=>setSection(e.key)} className="app-menu"/>
      {!collapsed && <div className="sider-foot"><Badge status="success" text="Local-first"/><div>Chỉ sử dụng trên localhost</div></div>}
    </Sider>
    <Layout>
      <Header className="app-header">
        <div><Text type="secondary">Workspace / </Text><Text strong>{title}</Text></div>
        <Space><Button icon={<ReloadOutlined/>} loading={busy} onClick={()=>runAction(refresh,{refreshData:false})}>Làm mới</Button>
          <Button href="/" target="_blank" icon={<CodeOutlined/>}>Giao diện cũ</Button></Space>
      </Header>
      <Content className="app-content">
        <div className="page-heading"><div><div className="eyebrow">AGENTFORGE / OWNER WORKSPACE</div>
          {section!=='workspace'&&<Title level={2}>{title}</Title>}</div></div>
        <ErrorBoundary error={error} onReset={()=>setError(null)}/>
        {section==='workspace'&&<Workspace data={data} onPlan={plan} openGoal={openGoal} loading={busy}/>}
        {section==='overview'&&<Overview data={data} onNavigate={setSection}/>}
        {section==='goals'&&<Card><Table dataSource={goals} rowKey="goal_id" pagination={{pageSize:10}}
          columns={[{title:'Mục tiêu',dataIndex:'title'}, {title:'Workflow',dataIndex:'template'},
            {title:'Trạng thái',dataIndex:'status',render:badge},
            {title:'Hành động',render:(_,g)=><Button onClick={()=>openGoal(g.goal_id)}>Xem & duyệt</Button>}]}/></Card>}
        {section==='tasks'&&<Card><Table dataSource={tasks} rowKey="task_id" pagination={{pageSize:10}}
          columns={[{title:'Task',render:(_,t)=><code>{clip(t.task_id)}</code>},
            {title:'Skill',dataIndex:'skill_id'}, {title:'Trạng thái',dataIndex:'status',render:badge},
            {title:'Hành động',render:(_,t)=><Button onClick={()=>api('/api/tasks/'+t.task_id).then(setTask).catch(authError)}>Chi tiết</Button>}]}/></Card>}
        {section==='websites'&&<Websites data={data} showProposal={openProposal}/>}
        {section==='projects'&&<Card title="Projects & Files"><Alert type="info"
          message="Kho tài sản hiện được xem trong Control Center cũ"
          description="Không xóa hay di chuyển dữ liệu khi chuyển frontend. Phần duyệt website hiện đã có ở React."
          action={<Button href="/" target="_blank">Mở kho local</Button>}/></Card>}
        {['finance','channels','team','settings'].includes(section)&&<ReadOnlyPage section={section} data={data}/>}
      </Content>
    </Layout>
    <GoalDrawer goal={goal} onClose={()=>setGoal(null)} onApprove={approve}
      onExecute={execute} busy={busy} externalEnabled={!!data.external_actions_enabled}/>
    <ProposalDrawer proposal={proposal} onClose={()=>setProposal(null)}
      onRevise={revise} onApply={apply} busy={busy}/>
    <Drawer title="Chi tiết tác vụ" width={720} open={!!task} onClose={()=>setTask(null)}>
      {task && <><Descriptions bordered column={1} size="small" items={[
        {key:'1',label:'Task ID',children:<code>{task.task_id}</code>},
        {key:'2',label:'Skill',children:task.skill_id},
        {key:'3',label:'Status',children:badge(task.status)},
        {key:'4',label:'Error',children:task.error||'Không có'},
      ]}/><Collapse style={{marginTop:20}} items={[
        {key:'1',label:'Events & audit',children:<pre className="source-text">{JSON.stringify(task.events||[],null,2)}</pre>},
        {key:'2',label:'Kết quả',children:<pre className="source-text">{JSON.stringify(task.report||task.result||{},null,2)}</pre>},
      ]}/></>}
    </Drawer>
  </Layout>;
}
