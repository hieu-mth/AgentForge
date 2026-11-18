import {useCallback,useEffect,useState} from 'react';
import {Alert,Button,Card,Form,Input,Layout,Menu,Space,Spin,Tabs,Typography} from 'antd';
import {api,onAuthExpired,requestError} from './api.js';
import {useThemeMode} from './theme.jsx';
import {NAV_GROUPS,groupFor,defaultSection,parseSection,hashFor,tabsFor,labelFor} from './navigation.js';
import {MediaStudio} from './features/MediaStudio.jsx';
import {CharacterLibrary} from './features/CharacterLibrary.jsx';
import {Projects} from './features/Projects.jsx';
import {ModelHub} from './features/Models.jsx';
import {Environment} from './features/Environment.jsx';
import {Retention} from './features/Retention.jsx';
import {Publishing} from './features/Publishing.jsx';

const {Header,Sider,Content}=Layout;
const {Text,Title}=Typography;

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
  const navigate=next=>{window.location.hash=hashFor(next);setSection(parseSection(window.location.hash));};
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
    case 'retention':page=<Retention data={{}} mutate={mutate}/>;break;
    case 'channels':page=<Publishing data={{}} mutate={mutate}/>;break;
    case 'reviews':page=<Card title="Duyệt video"><Alert type="info" showIcon message="Duyệt video qua production receipt" description="Quy trình duyệt mới đang được hợp nhất với Film Studio. Không tự động phê duyệt hoặc xuất bản."/></Card>;break;
    case 'operations':page=<Card title="Vận hành"><Button onClick={refresh}>Kiểm tra phiên local</Button></Card>;break;
    case 'settings':page=<Card title="Cấu hình"><Text>Model và môi trường được cấu hình ở các trang bên cạnh.</Text></Card>;break;
    default:page=<Card title="Tổng quan Video Studio"><Space direction="vertical">
      <Text>Pipeline chính: Film Studio · Character Registry · Video Project.</Text>
      <Button type="primary" onClick={()=>navigate('media-studio')}>Mở Video Studio</Button>
      <Button onClick={()=>navigate('projects')}>Xem dự án video</Button>
    </Space></Card>;
  }
  return <Layout className="app-shell" style={{minHeight:'100vh'}}>
    <Sider breakpoint="lg" collapsedWidth="0" width={220}>
      <div className="brand" style={{padding:18}}><strong>AgentForge</strong></div>
      <Menu theme="dark" mode="inline" selectedKeys={[group]}
        items={NAV_GROUPS.map(g=>({key:g.key,label:g.label}))}
        onClick={({key})=>navigate(defaultSection(key))}/>
    </Sider>
    <Layout>
      <Header className="app-header" style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <Text strong>{labelFor(section)}</Text>
        <Space><Button onClick={refresh}>Làm mới</Button><Button onClick={toggle}>{mode==='dark'?'Sáng':'Tối'}</Button></Space>
      </Header>
      <Content style={{padding:24}}>
        {tabs.length>1&&<Tabs activeKey={section} items={tabs.map(t=>({key:t.key,label:t.label}))} onChange={navigate}/>}
        {error&&<Alert closable showIcon type="error" message={requestError(error)} onClose={()=>setError(null)} style={{marginBottom:16}}/>}
        {page}
      </Content>
    </Layout>
  </Layout>;
}
