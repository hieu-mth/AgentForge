import {useCallback,useEffect,useRef,useState} from 'react';
import {Alert,App as AntApp,Button,Card,Drawer,Form,Input,Layout,Menu,Space,Spin,Tabs,Typography} from 'antd';
import {AppstoreOutlined,ArrowRightOutlined,CodeOutlined,DashboardOutlined,LockOutlined,MenuOutlined,MoonOutlined,
  PlayCircleOutlined,ReloadOutlined,SendOutlined,SettingOutlined,
  SunOutlined,UserOutlined,VideoCameraOutlined} from '@ant-design/icons';
import {api,onAuthExpired,requestError} from './api.js';
import {useThemeMode} from './theme.jsx';
import {NAV_GROUPS,groupFor,defaultSection,parseSection,hashFor,tabsFor,labelFor} from './navigation.js';
import {MediaStudio} from './features/MediaStudio.jsx';
import {CharacterLibrary} from './features/CharacterLibrary.jsx';
import {Projects} from './features/Projects.jsx';
import {ModelHub} from './features/Models.jsx';
import {Orchestrator} from './features/Orchestrator.jsx';
import {Environment} from './features/Environment.jsx';
import {Publishing} from './features/Publishing.jsx';

const {Header,Sider,Content}=Layout;
const {Text}=Typography;
const NAV_ICONS={overview:<DashboardOutlined/>,studio:<VideoCameraOutlined/>,
  characters:<UserOutlined/>,products:<PlayCircleOutlined/>,business:<SendOutlined/>,
  settings:<SettingOutlined/>};
const MENU_ITEMS=NAV_GROUPS.map(g=>({key:g.key,label:g.label,icon:NAV_ICONS[g.key]}));

function Login({onLogin,error,busy}){
  const [edited,setEdited]=useState(false);
  const message=({
    invalid_credentials:'Mã Owner không đúng. Hãy kiểm tra mã trong PowerShell.',
    login_rate_limited:'Bạn đã thử quá nhiều lần. Hãy đợi một phút rồi thử lại.',
    NETWORK_UNAVAILABLE:'Mất kết nối với AgentForge. Hãy kiểm tra PowerShell rồi thử lại.',
  })[error?.code] || 'Chưa thể đăng nhập. Hãy kiểm tra AgentForge đang chạy rồi thử lại.';
  return <main className="login-screen">
    <div className="owner-login">
      <div className="owner-login-brand">
        <div className="owner-login-wordmark"><VideoCameraOutlined aria-hidden="true"/> AgentForge</div>
        <div className="owner-login-art" aria-hidden="true">
          <span/><span/><span/><PlayCircleOutlined/>
        </div>
        <div className="owner-login-product">Video Studio</div>
      </div>
      <section className="owner-login-panel" aria-labelledby="owner-login-title">
        <div className="owner-login-heading-icon"><LockOutlined aria-hidden="true"/></div>
        <h1 id="owner-login-title">Đăng nhập</h1>
        <p>Nhập mã Owner để mở dashboard.</p>
        <Form name="owner-login" layout="vertical" requiredMark={false}
          onValuesChange={()=>setEdited(true)}
          onFinish={values=>{setEdited(false);return onLogin(values);}}>
          <Form.Item name="code" label="Mã Owner" rules={[
            {required:true,message:'Hãy nhập mã Owner.'},
            {min:12,message:'Mã Owner cần ít nhất 12 ký tự.'},
          ]}>
            <Input.Password size="large" placeholder="Nhập mã Owner" autoComplete="off"
              autoCapitalize="off" spellCheck={false} disabled={busy}
              aria-describedby="owner-login-help"/>
          </Form.Item>
          {error&&!edited&&<Alert showIcon type="error" message={message}/>}
          <Button type="primary" size="large" htmlType="submit" loading={busy} block
            icon={<ArrowRightOutlined/>} iconPlacement="end">
            {busy?'Đang đăng nhập':'Mở dashboard'}
          </Button>
        </Form>
        <div className="owner-login-help" id="owner-login-help">
          <CodeOutlined aria-hidden="true"/>
          <span>Lấy mã từ cửa sổ PowerShell đang chạy AgentForge.</span>
        </div>
      </section>
    </div>
  </main>;
}

export default function App(){
  const {modal}=AntApp.useApp();
  const [section,setSection]=useState(()=>parseSection(window.location.hash));
  const [session,setSession]=useState(null);
  const [status,setStatus]=useState('loading');
  const [error,setError]=useState(null);
  const [busy,setBusy]=useState(false);
  const [mobileNavOpen,setMobileNavOpen]=useState(false);
  const [draftDirty,setDraftDirty]=useState(false);
  const discardOpen=useRef(false);
  const {mode,toggle}=useThemeMode();
  const refresh=useCallback(async(afterLogin=false)=>{
    setStatus('loading');
    try{
      const value=await api('/api/session');
      setSession(value);setStatus('ready');setError(null);
    }catch(e){
      setError(e.status===401&&!afterLogin?null:e);
      setSession(null);setStatus(e.status===401?'login':'offline');
    }
  },[]);
  useEffect(()=>{
    refresh();
    return onAuthExpired(()=>{
      setDraftDirty(false);setError(null);setSession(null);setStatus('login');
    });
  },[refresh]);
  const confirmDiscard=useCallback(action=>{
    if(!draftDirty){action();return;}
    if(discardOpen.current)return;
    discardOpen.current=true;
    modal.confirm({
      title:'Bỏ thay đổi chưa lưu?',
      content:'Bạn đang có bản nháp trong AI điều phối tác vụ.',
      okText:'Bỏ thay đổi',cancelText:'Ở lại chỉnh sửa',
      okButtonProps:{danger:true},autoFocusButton:'cancel',
      onOk:()=>{setDraftDirty(false);action();},
      afterClose:()=>{discardOpen.current=false;},
    });
  },[draftDirty,modal]);
  useEffect(()=>{
    const update=()=>{
      const next=parseSection(window.location.hash);
      if(next===section)return;
      if(!draftDirty){setSection(next);return;}
      window.history.replaceState(null,'',hashFor(section));
      confirmDiscard(()=>{
        window.history.replaceState(null,'',hashFor(next));
        setSection(next);
      });
    };
    window.addEventListener('hashchange',update);
    return ()=>window.removeEventListener('hashchange',update);
  },[section,draftDirty,confirmDiscard]);
  const navigate=next=>{
    setMobileNavOpen(false);
    if(next===section)return;
    confirmDiscard(()=>{
      window.history.pushState(null,'',hashFor(next));
      setSection(next);
    });
  };
  const mutate=async(path,body,{inlineError=false}={})=>{
    if(!session?.csrf)throw new Error('Phiên Owner chưa sẵn sàng');
    setBusy(true);
    try{
      const result=await api(path,{method:'POST',body,csrf:session.csrf});
      setError(null);return result;
    }catch(e){
      if(inlineError)throw e;
      setError(e);return null;
    }
    finally{setBusy(false);}
  };
  const login=async({code})=>{
    setBusy(true);setError(null);
    try{await api('/api/login',{method:'POST',body:{code}});await refresh(true);}
    catch(e){setError(e);}
    finally{setBusy(false);}
  };
  if(status==='loading')return <div className="loading-screen"><Spin size="large"/><Text>Đang kết nối AgentForge…</Text></div>;
  if(status==='login')return <Login onLogin={login} error={error} busy={busy}/>;
  if(status==='offline')return <div className="loading-screen"><Alert type="error" showIcon
    message="Không kết nối được backend local" description={requestError(error)}
    action={<Button onClick={()=>refresh()}>Thử kết nối lại</Button>}/></div>;
  const group=groupFor(section);
  const tabs=tabsFor(group);
  let page;
  switch(section){
    case 'media-studio':page=<MediaStudio onNavigate={navigate} mutate={mutate}/>;break;
    case 'characters':page=<CharacterLibrary mutate={mutate} onNavigate={navigate}/>;break;
    case 'projects':page=<Projects/>;break;
    case 'models':page=<ModelHub mutate={mutate}/>;break;
    case 'orchestrator':page=<Orchestrator mutate={mutate} dirty={draftDirty} setDirty={setDraftDirty}/>;break;
    case 'environment':page=<Environment onNavigate={navigate}/>;break;
    case 'channels':page=<Publishing mutate={mutate}/>;break;
    default:page=<Card title="Tổng quan Video Studio"><Space direction="vertical">
      <Text>Pipeline chính: Film Studio · Character Registry · Video Project.</Text>
      <Button type="primary" onClick={()=>navigate('media-studio')}>Mở Video Studio</Button>
      <Button onClick={()=>navigate('projects')}>Xem dự án video</Button>
    </Space></Card>;
  }
  const sidebar=<>
    <div className="af-brand">
      <span className="af-brand-mark" aria-hidden="true"><AppstoreOutlined/></span>
      <div><strong>AgentForge</strong><small>LOCAL-FIRST AI STUDIO</small></div>
    </div>
    <div className="af-sidebar-label">WORKSPACE</div>
    <Menu theme="dark" mode="inline" selectedKeys={[group]} items={MENU_ITEMS}
      onClick={({key})=>navigate(defaultSection(key))}/>
    <div className="af-sidebar-bottom">
      <span className="af-sidebar-bottom-indicator"/>
      <div><strong>Không gian local</strong><small>127.0.0.1 · Quyền Owner</small></div>
    </div>
  </>;
  return <Layout className="app-shell" style={{minHeight:'100vh'}}>
    <Sider className="af-sidebar" breakpoint="lg" collapsedWidth="0" width={244}
      trigger={null}>{sidebar}</Sider>
    <Drawer className="af-mobile-drawer" placement="left" width={256} title="Điều hướng"
      open={mobileNavOpen} onClose={()=>setMobileNavOpen(false)}>
      {sidebar}
    </Drawer>
    <Layout className="af-main-layout">
      <Header className="app-header">
        <div className="af-header-left">
          <Button className="af-mobile-nav-toggle" aria-label="Mở điều hướng"
            icon={<MenuOutlined/>} onClick={()=>setMobileNavOpen(true)}/>
          <div className="af-header-title">
            <span>AGENTFORGE / WORKSPACE</span><strong>{labelFor(section)}</strong>
          </div>
        </div>
        <Space className="af-header-actions" size={10}>
          <Button icon={<ReloadOutlined/>} onClick={()=>confirmDiscard(()=>refresh())}>Kiểm tra phiên</Button>
          <Button icon={mode==='dark'?<SunOutlined/>:<MoonOutlined/>}
            onClick={toggle}>{mode==='dark'?'Sáng':'Tối'}</Button>
        </Space>
      </Header>
      <Content className="af-content">
        <div className="af-page-container">
          {tabs.length>1&&<Tabs className="af-section-tabs" activeKey={section}
            items={tabs.map(t=>({key:t.key,label:t.label}))} onChange={navigate}/>}
          {error&&<Alert closable showIcon type="error" message={requestError(error)}
            onClose={()=>setError(null)} style={{marginBottom:16}}/>}
          {page}
        </div>
      </Content>
    </Layout>
  </Layout>;
}
