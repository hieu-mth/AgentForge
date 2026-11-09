import { useCallback, useEffect, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Collapse, Descriptions, Drawer, Form, Grid, Input,
  Layout, Menu, Space, Spin, Table, Tabs, Tooltip, Typography } from 'antd';
import {
  BarChartOutlined, DashboardOutlined, FolderOpenOutlined,
  LeftOutlined, MenuOutlined, MoonOutlined, ReloadOutlined, RobotOutlined,
  SafetyCertificateOutlined, SettingOutlined, SunOutlined, TeamOutlined,
} from '@ant-design/icons';
import { api } from './api.js';
import { useThemeMode } from './theme.jsx';
import { badge, clip, PageHeader } from './components/shared.jsx';
import { Workspace, GoalDrawer } from './features/Workspace.jsx';
import { modelCallsForPrompt } from './workspace_quota.js';
import { Websites, ProposalDrawer } from './features/Websites.jsx';
import { WebappProposalDrawer } from './features/Webapps.jsx';
import { Overview, ReadOnlyPage } from './features/Operations.jsx';
import { Projects } from './features/Projects.jsx';
import { Retention } from './features/Retention.jsx';
import { Reviews } from './features/Reviews.jsx';
import { Schedules, OperationsControl, Intelligence, Growth, OwnerSettings, OwnerMemory } from './features/Management.jsx';
import { NAV_GROUPS, groupFor, labelFor, defaultSection, parseSection, hashFor, tabsFor } from './navigation.js';
import { PERMISSIONS } from './permissions.js';
import { AcceptanceStatus } from './components/AcceptanceStatus.jsx';

const { Header, Sider, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

const GROUP_ICONS = {
  workspace: <RobotOutlined/>, overview: <DashboardOutlined/>,
  projects: <FolderOpenOutlined/>, business: <BarChartOutlined/>,
  team: <TeamOutlined/>, settings: <SettingOutlined/>,
};
const MENU_ITEMS = NAV_GROUPS.map(item => ({key: item.key, icon: GROUP_ICONS[item.key], label: item.label}));

function ErrorBoundary({error, onReset}) {
  if (!error) return null;
  return <Alert type="error" showIcon closable onClose={onReset} message="Không thể hoàn thành"
    description={error.message || String(error)} style={{marginBottom:20}}/>;
}

function Brand({collapsed}) {
  return <div className="brand"><span className="brand-glyph"><i/></span>
    {!collapsed&&<div><strong>AgentForge</strong><small>AI COMPANY</small></div>}</div>;
}

function Login({onLogin, busy}) {
  return <div className="login-screen">
    <section className="login-art" aria-hidden="true">
      <Brand/>
      <div className="login-copy">
        <h2>Rèn ý tưởng thành <em>sản phẩm</em>.</h2>
        <p>Một công ty AI chạy ngay trên máy của bạn: lập kế hoạch, thực thi và chỉ hành động khi bạn gật đầu.</p>
      </div>
      <ul className="login-points">
        <li>Duyệt SHA trước mọi lượt chạy</li><li>Dữ liệu ở lại localhost</li><li>Quyền cấp tạm thời, từng lần</li>
      </ul>
    </section>
    <section className="login-panel">
      <div className="login-card">
        <div className="chip"><SafetyCertificateOutlined/> LOCAL-FIRST · OWNER ACCESS</div>
        <Title level={2} style={{marginTop:18,marginBottom:8}}>Chào mừng trở lại</Title>
        <Paragraph type="secondary">Nhập mã Owner hiển thị trong PowerShell. Mã này không được lưu trên trình duyệt.</Paragraph>
        <Form layout="vertical" onFinish={onLogin} requiredMark={false}>
          <Form.Item label="Mã Owner" name="code" rules={[{required:true, min:12, message:'Mã cần ít nhất 12 ký tự'}]}>
            <Input.Password size="large" autoFocus autoComplete="off" placeholder="Mã phiên đăng nhập"/>
          </Form.Item>
          <Button size="large" type="primary" htmlType="submit" loading={busy} block>Vào Workspace</Button>
        </Form>
      </div>
    </section>
  </div>;
}

export default function App() {
  const {message,modal} = AntApp.useApp();
  const [csrf,setCsrf]=useState(null);
  const [data,setData]=useState(null);
  const [loginNeeded,setLoginNeeded]=useState(false);
  const [section,setSection]=useState(()=>parseSection(window.location.hash));
  // Preserve the Owner's request when navigating to quota Settings.
  const [workspacePrompt,setWorkspacePrompt]=useState('');
  const [goal,setGoal]=useState(null);
  const [proposal,setProposal]=useState(null);
  const [webapp,setWebapp]=useState(null);
  const [task,setTask]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState(null);
  const [collapsed,setCollapsed]=useState(false);
  const [navOpen,setNavOpen]=useState(false);
  const screens=Grid.useBreakpoint();
  const mobile=screens.lg===false;
  const {mode,toggle:toggleTheme}=useThemeMode();
  const authError = err => {
    if (err.status===401) {setLoginNeeded(true);setData(null);setCsrf(null);}
    else {setError(err);message.error(err.message || 'API error');}
  };
  const refresh=useCallback(async()=>{
    const [session,bootstrap] = await Promise.all([api('/api/session'),api('/api/bootstrap')]);
    setCsrf(session.csrf);setData(bootstrap);setLoginNeeded(false);
  },[]);
  useEffect(()=>{refresh().catch(e=>{if(e.status===401)setLoginNeeded(true);else setError(e);});},[refresh]);
  useEffect(()=>{
    const syncLocation=()=>setSection(parseSection(window.location.hash));
    window.addEventListener('hashchange',syncLocation);
    return ()=>window.removeEventListener('hashchange',syncLocation);
  },[]);
  const navigate=(target)=>{
    const next=hashFor(target);
    setSection(parseSection(next));
    if(window.location.hash!==next)window.location.hash=next;
    window.scrollTo?.({top:0});
  };
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
    try{
      const detail=await api('/api/goals/'+encodeURIComponent(id));
      const failedStep=(detail.step_runs||[]).find(s=>s.status==='FAILED'&&s.child_task_id);
      if(failedStep){
        try{
          const taskDetail=await api('/api/tasks/'+encodeURIComponent(failedStep.child_task_id));
          detail.execution_error=taskDetail.error||detail.error;
        }catch{detail.execution_error=detail.error;}
      }
      setGoal(detail);
    }catch(e){authError(e);}
  };
  const openGoalResult=async selectedGoal=>{
    const ordered=(selectedGoal.step_runs||[]).filter(step=>step.status==='SUCCEEDED'&&step.child_task_id);
    const completed=selectedGoal.template==='webapp.company'
      ? ordered.find(step=>step.skill_id==='webapp.review')||ordered.find(step=>step.skill_id==='webapp.develop')||ordered[0]
      : ordered[0];
    if(!completed){message.warning('Không tìm thấy thành phẩm của kế hoạch này');return;}
    try{
      const detail=await api('/api/tasks/'+encodeURIComponent(completed.child_task_id));
      if(detail.web_proposal?.proposal_id){
        // A successful web.create produces a reviewable *proposal*, not a
        // completed live website. Open the existing sandboxed visual preview.
        await openProposal(detail.web_proposal.proposal_id);
        setGoal(null);
      }else if(detail.report?.kind==='webapp'&&detail.report.proposal_id){
        await openWebapp(detail.report.proposal_id);
        setGoal(null);
      }else{
        setTask(detail);
      }
    }catch(e){authError(e);}
  };
  const plan=async prompt => {
    const outcome=await runAction(()=>post('/api/workspace/request',
      {ack:'PLAN_ONLY',prompt,
       max_model_calls:modelCallsForPrompt(prompt)}));
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
      <Paragraph><strong>Quyền được cấp:</strong></Paragraph>
      <ul>{permissions.grants.length ? permissions.grants.map(p=>
        <li key={p}>{PERMISSIONS[p]?.title||'Quyền không xác định'}</li>) :
        <li>Chỉ đọc dữ liệu</li>}</ul>
      {permissions.sensitive&&<Alert type="warning"
        message="Công việc có thể dùng AI, Internet hoặc công cụ ngoài"
        description="Chỉ xác nhận nếu bạn đồng ý với các tác động được mô tả. Lượt chạy vẫn phải tuân theo chính sách backend."/>}</>,
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
  const openWebapp=async id => {
    try{setWebapp(await api('/api/webapps/'+encodeURIComponent(id)));}
    catch(e){authError(e);}
  };
  const decideArtifact=(p,decision,namespace='webapps')=>ask(
    decision==='ACCEPTED'?'Owner chấp nhận sản phẩm?':'Từ chối sản phẩm?',
    'Quyết định chỉ áp dụng cho đúng phiên bản mã nguồn và bằng chứng QA đã xem. Không tự xuất bản.',
    async()=>{
      const acceptance=p.artifact_acceptance;
      const out=await runAction(()=>post('/api/artifacts/'+namespace+'/'+p.proposal_id+'/decision',{
        ack:decision==='ACCEPTED'?'ACCEPT_ARTIFACT':'REJECT_ARTIFACT', sha256:p.sha256,
        expected_revision:acceptance.revision, evidence_sha:acceptance.evidence_sha,
      }));
      if(out){if(namespace==='webapps')await openWebapp(p.proposal_id);else await openProposal(p.proposal_id);}
    });
  const validateArtifact=async(p,namespace='webapps')=>{
    const out=await runAction(()=>post('/api/artifacts/'+namespace+'/'+p.proposal_id+'/syntax',
      {ack:'VALIDATE_SYNTAX',sha256:p.sha256}));
    if(out){
      if(out.syntax.status==='PASS')message.info('Cú pháp hợp lệ; chưa xác nhận build hoặc tương tác.');
      else message.error('Source sai cú pháp: '+out.syntax.diagnostics.map(d=>`${d.path}:${d.line}:${d.column}`).join(', '));
      if(namespace==='webapps')await openWebapp(p.proposal_id);else await openProposal(p.proposal_id);
    }
  };
  const verifyWebapp=p=>ask('Lập kế hoạch QA container?',
    'Chỉ tạo Goal mới. Chạy container cần Docker Linux, image local được pin bằng SHA và quyền process.run được cấp riêng.',
    async()=>{
      const out=await runAction(()=>post('/api/goals/propose',{
        ack:'PROPOSE',title:'Kiểm thử nguồn React trong Docker offline',
        template:'webapp.qa',
        inputs:{proposal_id:p.proposal_id,sha256:p.sha256,confirm_external_run:true},
        max_model_calls:0,max_external_runs:1,
      }));
      if(out){setWebapp(null);message.success('Đã lập Goal QA sandbox');await openGoal(out.goal_id);}
    });
  const reviseWebapp=(p,feedback)=>ask('Duyệt việc tạo Goal sửa ứng dụng?',
    'Phiên bản gốc được giữ nguyên; Goal mới cần duyệt SHA và quyền gọi model riêng.',
    async()=>{const out=await runAction(()=>post('/api/webapps/'+p.proposal_id+'/revision',
      {ack:'REQUEST_REVISION',sha256:p.sha256,feedback:feedback.trim()}));
      if(out){setWebapp(null);message.success('Đã lập kế hoạch sửa ứng dụng');await openGoal(out.goal_id);}});
  const applyWebapp=p=>ask('Duyệt SHA và lưu mã nguồn React?',
    <><Paragraph>Mã nguồn sẽ được lưu vào workspace/webapps trong thư mục mới.</Paragraph>
       <Text code>{p.sha256}</Text>
       <Paragraph type="secondary">Hệ thống không tự chạy npm, cài package hay deploy.</Paragraph></>,
    async()=>{const out=await runAction(()=>post('/api/webapps/'+p.proposal_id+'/apply',
      {ack:'APPLY_WEBAPP',sha256:p.sha256}));
      if(out){setWebapp(null);message.success('Đã lưu mã nguồn: workspace/webapps/'+out.project_slug);}});
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

  // Sidebar shows only business-level destinations; all existing screens live in tabs.
  const group=groupFor(section);
  const groupTitle=NAV_GROUPS.find(item=>item.key===group)?.label || 'Tổng quan';
  const activeTabs=tabsFor(group);
  if(loginNeeded)return <><Login onLogin={async({code})=>{
    await runAction(async()=>{await api('/api/login',{method:'POST',body:{code}});await refresh();},
      {refreshData:false});}} busy={busy}/><ErrorBoundary error={error} onReset={()=>setError(null)}/></>;
  if(!data)return <div className="loading-screen"><Brand/><Spin size="large"/>
    <Text type="secondary">Đang kết nối AgentForge…</Text>
    <ErrorBoundary error={error} onReset={()=>setError(null)}/></div>;
  const title = labelFor(section);
  const goals = data.goals||[], tasks=data.tasks||[];
  const goTo=key=>{navigate(defaultSection(key));setNavOpen(false);};
  const menu=<Menu theme="dark" mode="inline" items={MENU_ITEMS} selectedKeys={[group]}
    onClick={e=>goTo(e.key)} className="app-menu"/>;
  const operations=data.company_v2?.operations;
  return <Layout className="app-shell">
    {!mobile&&<Sider theme="dark" collapsible collapsed={collapsed} onCollapse={setCollapsed}
      trigger={null} width={252} collapsedWidth={78} className="app-sider">
      <Brand collapsed={collapsed}/>
      {menu}
      <Tooltip title={collapsed?"Mở rộng menu":"Thu gọn menu"} placement="right">
        <button type="button" className="sider-toggle" aria-label={collapsed?"Mở rộng menu":"Thu gọn menu"}
          aria-expanded={!collapsed} onClick={()=>setCollapsed(v=>!v)}>
          <LeftOutlined className={collapsed?"sider-chevron rotated":"sider-chevron"}/>
        </button>
      </Tooltip>
      {!collapsed&&<div className="sider-foot"><span className="live-dot"/>
        <div><strong>Local-first</strong><small>Chỉ chạy trên localhost</small></div></div>}
    </Sider>}
    {mobile&&<Drawer placement="left" open={navOpen} onClose={()=>setNavOpen(false)} size={270}
      className="nav-drawer" closable={false} styles={{body:{padding:0}}}>
      <Brand/>{menu}</Drawer>}
    <Layout className="app-main">
      <Header className="app-header">
        <div className="crumbs">
          {mobile&&<Button type="text" aria-label="Mở menu" icon={<MenuOutlined/>} onClick={()=>setNavOpen(true)}/>}
          <Text type="secondary" className="crumb-root">{groupTitle}</Text>
          {title!==groupTitle&&<><span className="crumb-sep">/</span><Text strong>{title}</Text></>}
        </div>
        <Space size={8}>
          {operations&&<span className="header-status">{badge(operations)}</span>}
          <Tooltip title={mode==='dark'?'Chế độ sáng':'Chế độ tối'}>
            <Button shape="circle" aria-label="Đổi giao diện sáng/tối"
              icon={mode==='dark'?<SunOutlined/>:<MoonOutlined/>} onClick={toggleTheme}/></Tooltip>
          <Tooltip title="Làm mới dữ liệu">
            <Button shape="circle" aria-label="Làm mới" icon={<ReloadOutlined/>} loading={busy}
              onClick={()=>runAction(refresh,{refreshData:false})}/></Tooltip>
        </Space>
      </Header>
      <Content className="app-content">
        {section!=='workspace'&&<PageHeader eyebrow={(title!==groupTitle?groupTitle:'AgentForge').toUpperCase()} title={title}/>}
        <ErrorBoundary error={error} onReset={()=>setError(null)}/>
        {activeTabs.length>1&&
          <Tabs className="workspace-tabs" activeKey={section}
            items={activeTabs} onChange={navigate}/>}
        <div className="page-body" key={section}>
          {section==='workspace'&&<Workspace data={data} onPlan={plan} openGoal={openGoal}
              prompt={workspacePrompt} setPrompt={setWorkspacePrompt}
              onOpenSettings={()=>navigate('settings')} loading={busy}/>} 
          {section==='overview'&&<Overview data={data} onNavigate={navigate}/>}
          {section==='goals'&&<Card><Table dataSource={goals} rowKey="goal_id"
            pagination={{pageSize:10,hideOnSinglePage:true}} scroll={{x:'max-content'}}
            locale={{emptyText:'Chưa có kế hoạch nào'}}
            columns={[{title:'Mục tiêu',dataIndex:'title'}, {title:'Workflow',dataIndex:'template'},
              {title:'Trạng thái',dataIndex:'status',render:badge},
              {title:'Hành động',render:(_,g)=><Button onClick={()=>openGoal(g.goal_id)}>Xem & duyệt</Button>}]}/></Card>}
          {section==='tasks'&&<Card><Table dataSource={tasks} rowKey="task_id"
            pagination={{pageSize:10,hideOnSinglePage:true}} scroll={{x:'max-content'}}
            locale={{emptyText:'Chưa có tác vụ nào'}}
            columns={[{title:'Task',render:(_,t)=><code>{clip(t.task_id)}</code>},
              {title:'Skill',dataIndex:'skill_id'}, {title:'Trạng thái',dataIndex:'status',render:badge},
              {title:'Hành động',render:(_,t)=><Button onClick={()=>api('/api/tasks/'+t.task_id).then(setTask).catch(authError)}>Chi tiết</Button>}]}/></Card>}
          {section==='websites'&&<Websites data={data} showProposal={openProposal}/>}
          {section==='projects'&&<Projects mutate={mutate}/>}
          {section==='retention'&&<Retention data={data} mutate={mutate}/>}
          {section==='reviews'&&<Reviews data={data} mutate={mutate} onReload={refresh}/>}
          {section==='schedules'&&<Schedules data={data} mutate={mutate} onReload={refresh}/>}
          {section==='operations'&&<OperationsControl data={data} mutate={mutate} onReload={refresh}/>}
          {section==='intelligence'&&<Intelligence data={data}/>}
          {section==='growth'&&<Growth data={data} mutate={mutate} onReload={refresh}/>}
          {section==='settings'&&<OwnerSettings data={data} mutate={mutate} onReload={refresh}/>}
          {section==='memory'&&<OwnerMemory mutate={mutate}/>}
          {['finance','channels','team'].includes(section)&&<ReadOnlyPage section={section} data={data}/>}
        </div>
      </Content>
    </Layout>
    <GoalDrawer goal={goal} onClose={()=>setGoal(null)} onApprove={approve}
      onExecute={execute} onViewResult={openGoalResult} busy={busy} externalEnabled={!!data.external_actions_enabled}/>
    <ProposalDrawer proposal={proposal} onClose={()=>setProposal(null)} onDecide={(p,d)=>decideArtifact(p,d,'proposals')} onValidate={p=>validateArtifact(p,'proposals')}
      onRevise={revise} onApply={apply} busy={busy}/>
    <WebappProposalDrawer proposal={webapp} onClose={()=>setWebapp(null)} onDecide={decideArtifact} onValidate={validateArtifact}
      onRevise={reviseWebapp} onApply={applyWebapp}
      onVerify={verifyWebapp} busy={busy}/>
    <Drawer title="Chi tiết tác vụ" size={720} open={!!task} onClose={()=>setTask(null)}>
      {task && <><Descriptions bordered column={1} size="small" items={[
        {key:'1',label:'Task ID',children:<code>{task.task_id}</code>},
        {key:'2',label:'Skill',children:task.skill_id},
        {key:'3',label:'Thực thi',children:badge(task.status)},
        {key:'acceptance',label:'Nghiệm thu sản phẩm',children:<AcceptanceStatus acceptance={task.artifact_acceptance}/>},
        {key:'4',label:'Error',children:task.error||'Không có'},
      ]}/>
      {task.report?.kind==='v5_review'&&<Card title="V5 — AI Reviewer (chưa duyệt sản phẩm)" style={{marginTop:18}}>
        <Alert showIcon type="warning" message="Đánh giá mang tính tư vấn"
          description="Đã kiểm tra nguồn và QA tĩnh. Chưa xác nhận ứng dụng chạy đúng, chưa build, chưa kiểm thử trình duyệt hoặc kiểm toán bảo mật."/>
        <Descriptions bordered column={1} size="small" style={{marginTop:14}} items={[
          {key:'status',label:'Trạng thái',children:task.report.status},
          {key:'recommendation',label:'Đề xuất',children:task.report.recommendation},
          {key:'summary',label:'Nhận xét',children:task.report.summary},
        ]}/>
        {(task.report.missing_features||[]).length>0&&<Typography.Paragraph style={{marginTop:14}}>
          <strong>Chức năng có thể thiếu:</strong> {(task.report.missing_features||[]).join(' · ')}
        </Typography.Paragraph>}
        {(task.report.risks||[]).length>0&&<Typography.Paragraph>
          <strong>Rủi ro:</strong> {(task.report.risks||[]).join(' · ')}
        </Typography.Paragraph>}
        <Button onClick={()=>openWebapp(task.report.proposal_id)}>
          Mở mã nguồn React để Owner duyệt
        </Button>
      </Card>}
      {task.report?.kind==='v5_static_qa'&&<Card title="V5 — QA tĩnh" style={{marginTop:18}}>
        <Alert type="info" showIcon message="Chỉ kiểm tra mã nguồn, SHA và allowlist"
          description="Không chạy npm, không chạy trình duyệt và không bảo đảm chức năng hoạt động."/>
      </Card>}
      {task.report?.kind==='webapp_qa'&&<Card title="Kết quả QA React trong Docker"
        style={{marginTop:18}}>
        <Alert type={task.report.status==='PASS'?'success':'error'} showIcon
          message={task.report.status==='PASS'?'Đã chạy unit test và build trong container offline':'Không có kết quả QA hợp lệ'}
          description="Không có truy cập mạng, không mount mã nguồn ở chế độ ghi. Kết quả không có nghĩa là ứng dụng đã được deploy hoặc đã qua kiểm thử giao diện trên máy Owner."/>
        <Descriptions column={1} size="small" bordered style={{marginTop:14}} items={[
          {key:'sandbox',label:'Runtime',children:task.report.sandbox},
          {key:'network',label:'Mạng',children:task.report.network},
          {key:'source',label:'Nguồn',children:task.report.source_mount},
          {key:'checks',label:'Kiểm thử',children:(task.report.checks||[]).join(', ')},
        ]}/>
      </Card>}
      {task.report?.kind==='storyboard'&&<Card title={task.report.title||'Kịch bản video'}
        style={{marginTop:18}} extra={<Button onClick={()=>navigator.clipboard?.writeText(
          JSON.stringify({title:task.report.title,scenes:task.report.scenes},null,2)
        )}>Sao chép JSON</Button>}>
        <Alert type="info" showIcon style={{marginBottom:16}}
          message="Đây là kịch bản nháp, chưa phải video hoàn chỉnh"
          description="Nội dung AI chưa được xác minh; cần Owner duyệt trước khi sử dụng."/>
        {(task.report.scenes||[]).map((scene,index)=><div key={index}
          className="storyboard-scene">
          <Text type="secondary">Cảnh {index+1} · {scene.duration_seconds} giây</Text>
          <Typography.Title level={5} style={{margin:'8px 0'}}>{scene.headline}</Typography.Title>
          <Typography.Paragraph>{scene.caption}</Typography.Paragraph>
        </div>)}
      </Card>}
      {task.report?.kind==='webapp'&&<Card title={task.report.format==='agentforge.webapp.ai-code.v1'
        ? 'AI Developer thử nghiệm — mã React cần kiểm duyệt'
        : 'Ứng dụng React marketplace — bản nháp mã nguồn'}
        style={{marginTop:18}} extra={<Button onClick={()=>openWebapp(task.report.proposal_id)}>
          Xem mã nguồn & duyệt</Button>}>
        <Alert type="warning" showIcon
          message="Mã nguồn mới chỉ được tạo đề xuất, chưa thực thi"
          description={task.report.format==='agentforge.webapp.ai-code.v1'
            ? 'AI đã đề xuất mã JSX/CSS tùy biến. Mã không được thực thi hay chứng minh an toàn; không chạy npm trên máy chủ. Chỉ kiểm thử trong Docker với quyền riêng.'
            : 'V4.0b tạo dữ liệu demo do AI đề xuất và kết hợp với React code đã được kiểm tra. Chưa chạy npm, không có thanh toán thật.'}/>
        <Descriptions style={{marginTop:16}} column={1} bordered size="small" items={[
          {key:'project',label:'Dự án',children:task.report.project_slug},
          {key:'proposal',label:'Proposal',children:<code>{task.report.proposal_id}</code>},
          {key:'sha',label:'SHA duyệt riêng',children:<Text code copyable>{task.report.sha256}</Text>},
        ]}/>
        <Typography.Paragraph type="secondary" style={{marginTop:14}}>
          Kiểm tra proposal và mã nguồn trên máy Windows trước khi duyệt lưu:
        </Typography.Paragraph>
        <pre className="source-text">{(task.report.format==='agentforge.webapp.ai-code.v1'
          ? [
            'cd D:\\AgentForge',
            '.\\.venv\\Scripts\\python.exe -m agentforge.webapp_developer inspect '+task.report.proposal_id,
            'notepad .\\data\\company\\webapp_developer\\proposals\\'+task.report.proposal_id+'.json',
            '# REVIEW source; do not execute untrusted JSX on Windows.',
            '# Use the Dashboard sandbox QA Goal with separate process.run approval.',
          ] : [
            'cd D:\\AgentForge',
            '.\\.venv\\Scripts\\python.exe -m agentforge.webapp_builder inspect '+task.report.proposal_id,
            'notepad .\\data\\company\\webapp_builder\\proposals\\'+task.report.proposal_id+'.json',
            '.\\.venv\\Scripts\\python.exe -m agentforge.webapp_builder apply '+task.report.proposal_id+' --sha256 '+task.report.sha256+' --confirm-write',
            'cd workspace\\webapps\\'+task.report.project_slug,
            'npm.cmd install',
            'npm.cmd test',
            'npm.cmd run build',
            'npm.cmd run dev',
          ]).join('\n')}</pre>
        <Typography.Paragraph type="secondary">
          Lệnh apply là bước phê duyệt bổ sung; chỉ chạy sau khi tự xem mã nguồn. npm install và npm run dev không được AgentForge tự động gọi.
        </Typography.Paragraph>
      </Card>}
      <Collapse style={{marginTop:20}} items={[
        {key:'1',label:'Events & audit',children:<pre className="source-text">{JSON.stringify(task.events||[],null,2)}</pre>},
        {key:'2',label:'Kết quả',children:<pre className="source-text">{JSON.stringify(task.report||task.result||{},null,2)}</pre>},
      ]}/></>}
    </Drawer>
  </Layout>;
}
