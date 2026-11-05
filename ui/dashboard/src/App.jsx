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
import { badge, clip } from './components/shared.jsx';
import { Workspace, GoalDrawer } from './features/Workspace.jsx';
import { Websites, ProposalDrawer } from './features/Websites.jsx';
import { Overview, ReadOnlyPage } from './features/Operations.jsx';
import { Projects } from './features/Projects.jsx';
import { Reviews } from './features/Reviews.jsx';
import { Schedules, OperationsControl, Intelligence, Growth, OwnerSettings, OwnerMemory } from './features/Management.jsx';

const { Header, Sider, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

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
  const mutate=(path,body)=>runAction(()=>post(path,body));
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
    {key:'goals',icon:<AuditOutlined/>,label:'Goals & Duyệt'},
    {key:'tasks',icon:<ClockCircleOutlined/>,label:'Task History'},
    {key:'reviews',icon:<CheckCircleOutlined/>,label:'AI & Video Review'},
    {key:'websites',icon:<GlobalOutlined/>,label:'Websites'},
    {key:'projects',icon:<FolderOpenOutlined/>,label:'Projects & AI Images'},
    {type:'divider'},
    {key:'team',icon:<TeamOutlined/>,label:'Team & Roles'},
    {key:'intelligence',icon:<AppstoreOutlined/>,label:'Intelligence'},
    {key:'growth',icon:<BarChartOutlined/>,label:'Growth & Revenue'},
    {key:'schedules',icon:<ClockCircleOutlined/>,label:'Schedules'},
    {key:'operations',icon:<SafetyCertificateOutlined/>,label:'Operations'},
    {key:'channels',icon:<PlayCircleOutlined/>,label:'Channels'},
    {key:'finance',icon:<BarChartOutlined/>,label:'Finance'},
    {key:'settings',icon:<SettingOutlined/>,label:'Settings'},
    {key:'memory',icon:<FileTextOutlined/>,label:'Owner Memory'},
  ];
  const titles={workspace:'Giao việc',overview:'Tổng quan',goals:'Kế hoạch',tasks:'Task History',
    reviews:'AI & Video Review',websites:'Websites',projects:'Projects & AI Images',
    team:'Team & Roles',intelligence:'Intelligence',growth:'Growth & Revenue',
    schedules:'Schedules',operations:'Operations',channels:'Channels',
    finance:'Finance',settings:'Settings',memory:'Owner Memory'};
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
        {section==='projects'&&<Projects mutate={mutate}/>}
        {section==='reviews'&&<Reviews data={data} mutate={mutate} onReload={refresh}/>}
        {section==='schedules'&&<Schedules data={data} mutate={mutate} onReload={refresh}/>}
        {section==='operations'&&<OperationsControl data={data} mutate={mutate} onReload={refresh}/>}
        {section==='intelligence'&&<Intelligence data={data}/>}
        {section==='growth'&&<Growth data={data} mutate={mutate} onReload={refresh}/>}
        {section==='settings'&&<OwnerSettings data={data} mutate={mutate} onReload={refresh}/>}
        {section==='memory'&&<OwnerMemory mutate={mutate}/>}
        {['finance','channels','team'].includes(section)&&<ReadOnlyPage section={section} data={data}/>}
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
