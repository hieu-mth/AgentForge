import {useCallback,useEffect,useState} from 'react';
import {Alert,Button,Card,Drawer,Form,Input,Layout,Menu,Space,Spin,Tabs,Typography} from 'antd';
import {AppstoreOutlined,DashboardOutlined,MenuOutlined,MoonOutlined,
  PlayCircleOutlined,ReloadOutlined,SendOutlined,SettingOutlined,
  SunOutlined,UserOutlined,VideoCameraOutlined} from '@ant-design/icons';
import {api,onAuthExpired,requestError} from './api.js';
import {useThemeMode} from './theme.jsx';
import {NAV_GROUPS,groupFor,defaultSection,parseSection,hashFor,tabsFor,labelFor} from './navigation.js';
import {MediaStudio} from './features/MediaStudio.jsx';
import {CharacterLibrary} from './features/CharacterLibrary.jsx';
import {Projects} from './features/Projects.jsx';
import {ModelHub} from './features/Models.jsx';
import {Environment} from './features/Environment.jsx';
import {Publishing} from './features/Publishing.jsx';

const {Header,Sider,Content}=Layout;
const {Text,Title}=Typography;
const NAV_ICONS={overview:<DashboardOutlined/>,studio:<VideoCameraOutlined/>,
  characters:<UserOutlined/>,products:<PlayCircleOutlined/>,business:<SendOutlined/>,
  settings:<SettingOutlined/>};
const MENU_ITEMS=NAV_GROUPS.map(g=>({key:g.key,label:g.label,icon:NAV_ICONS[g.key]}));

function Login({onLogin,error,busy}){
  return <div className="login-screen"><Card style={{maxWidth:460,margin:'8vh auto'}}>
    <Title level={3}>AgentForge · Video Studio</Title>
    <Text type="secondary">Nhập mã Owner từ PowerShell. Mã không lưu trong trình duyệt.</Text>
    <Form layout="vertical" onFinish={onLogin} style={{marginTop:24}}>
      <Form.Item name="code" label="Mã Owner" rules={[{required:true,min:12}]}>
        <Input.Password autoComplete="off"/>
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={busy} block>Đăng nhập</Button>
    </Form>
    {error&&<Alert showIcon type="error" message={requestError(error)}/>}
  </Card></div>;
}

export default function App(){
  const [section,setSection]=useState(()=>parseSection(window.location.hash));
  const [session,setSession]=useState(null);
  const [status,setStatus]=useState('loading');
  const [error,setError]=useState(null);
  const [busy,setBusy]=useState(false);
  const [mobileNavOpen,setMobileNavOpen]=useState(false);
  const {mode,toggle}=useThemeMode();
  const refresh=useCallback(async()=>{
    setStatus('loading');
    try{
      const value=await api('/api/session');
      setSession(value);setStatus('ready');setError(null);
    }catch(e){setError(e);setSession(null);setStatus(e.status===401?'login':'offline');}
  },[]);
  useEffect(()=>{refresh();return onAuthExpired(()=>{setSession(null);setStatus('login');});},[refresh]);
  useEffect(()=>{
    const update=()=>setSection(parseSection(window.location.hash));
    window.addEventListener('hashchange',update);
    return ()=>window.removeEventListener('hashchange',update);
  },[]);
  const navigate=next=>{window.location.hash=hashFor(next);setSection(parseSection(window.location.hash));setMobileNavOpen(false);};
  const mutate=async(path,body)=>{
    if(!session?.csrf)throw new Error('Phiên Owner chưa sẵn sàng');
    setBusy(true);
    try{
      const result=await api(path,{method:'POST',body,csrf:session.csrf});
      setError(null);return result;
    }catch(e){setError(e);return null;}
    finally{setBusy(false);}
  };
  const login=async({code})=>{
    setBusy(true);
    try{await api('/api/login',{method:'POST',body:{code}});await refresh();}
    catch(e){setError(e);}
    finally{setBusy(false);}
  };
  if(status==='loading')return <div className="loading-screen"><Spin size="large"/><Text>Đang kết nối AgentForge…</Text></div>;
  if(status==='login')return <Login onLogin={login} error={error} busy={busy}/>;
  if(status==='offline')return <div className="loading-screen"><Alert type="error" showIcon
    message="Không kết nối được backend local" description={requestError(error)}
    action={<Button onClick={refresh}>Thử kết nối lại</Button>}/></div>;
  const group=groupFor(section);
  const tabs=tabsFor(group);
  let page;
  switch(section){
    case 'media-studio':page=<MediaStudio onNavigate={navigate}/>;break;
    case 'characters':page=<CharacterLibrary mutate={mutate} onNavigate={navigate}/>;break;
    case 'projects':page=<Projects/>;break;
    case 'models':page=<ModelHub mutate={mutate}/>;break;
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
          <Button icon={<ReloadOutlined/>} onClick={refresh}>Kiểm tra phiên</Button>
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
