import {AppTooltip} from '../components/AppTooltip.jsx';
import { useState } from 'react';
import { App as AntApp, Alert, Button, Card, Empty, Grid, Select,
  Space, Table, Typography } from 'antd';
import {AppstoreOutlined,DeleteOutlined,DesktopOutlined,HistoryOutlined,PlusOutlined,ReloadOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus,Stat} from '../components/settings.jsx';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {displayStatus} from '../environment_format.js';
import {ModelProfileDialog} from './ModelProfileDialog.jsx';
import {FluxProbeDialog} from './FluxProbeDialog.jsx';
import {configurableProfiles,outputSummary,profileCapability,readinessLabels,readinessReason} from '../model_hub_ui.js';
import {requestError} from '../api.js';

const { Text, Paragraph } = Typography;
const desktopColumns=['md'];

export function ModelHub({mutate}) {
  const {message,modal}=AntApp.useApp();
  const {md:desktop}=Grid.useBreakpoint();
  const hubResource=useResource('/api/model-hub');
  const setHub=hubResource.setData;
  const hub=hubResource.data;
  const loading=hubResource.loading;
  const [checked,setChecked]=useState({});
  const [probes,setProbes]=useState({});
  const [editor,setEditor]=useState(null);
  const [fluxProbe,setFluxProbe]=useState(null);

  const reload=hubResource.reload;
  useScreenRefresh(reload);

  const profiles=hub?.profiles||[];
  const adapters=hub?.adapters||[];
  const byAdapter=Object.fromEntries(adapters.map(adapter=>[adapter.id,adapter]));
  const capabilities=hub?.orchestrator?.capabilities??[];
  const labels=Object.fromEntries(capabilities.map(item=>[item.id,item.label]));
  const assigned=row=>capabilities.filter(item=>item.model_ref===row.id);
  const checkKey=(id,revision)=>revision+':'+id;
  const checkResult=row=>checked[checkKey(row.id,hub.revision)];
  const localProfiles=profiles.filter(p=>byAdapter[p.provider]?.connection==='local').length;

  const update=(path,body,title,description,onSuccess)=>{
    modal.confirm({
      title,content:<Space direction="vertical" style={{width:'100%'}}>
        <Paragraph>{description}</Paragraph>
        <Alert type="info" showIcon message={'Revision đang lưu: '+(hub?.revision??'?')}
          description="Nếu Dashboard khác đã đổi cấu hình, backend sẽ từ chối revision cũ. Không tự retry."/>
      </Space>,
      okText:'Xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const result=await mutate(path,body);
        if(result){
          if(path==='/api/model-hub/probe') {
            setProbes(old=>({...old,[body.profile_id]:result}));
          }else {
            setHub(result);setChecked({});setProbes({});
          }
          if(path!=='/api/model-hub/probe') {
            message.success('Đã lưu cấu hình');
          }
          onSuccess?.();
        } else {
          await reload();
        }
      },
    });
  };

  const editProfile=profile=>setEditor({profile,revision:hub.revision});
  const reloadEditor=async(candidateId)=>{
    const current=await reload();
    if(!current)throw new Error('Chưa tải được cấu hình hiện tại. Hãy thử lại.');
    return {profile:current.profiles.find(item=>item.id===candidateId)??null,revision:current.revision};
  };
  const checkProfile=async(row,revision=hub.revision)=>{
    const capability=profileCapability(row)?.capability;
    if(!capability)return;
    const key=checkKey(row.id,revision);
    setChecked(old=>({...old,[key]:{pending:true}}));
    try{
      const result=await mutate('/api/model-hub/readiness',{
        ack:'CHECK_CAPABILITY_READINESS',profile_id:row.id,capability,expected_revision:revision,
      },{inlineError:true});
      if(result?.revision!==revision||result.profile_id!==row.id||result.capability!==capability)
        throw new Error('Kết quả kiểm tra không khớp hồ sơ và phiên bản đã yêu cầu.');
      setChecked(old=>({...old,[key]:result}));
    }catch(error){
      setChecked(old=>({...old,[key]:{error:requestError(error)}}));
    }
  };
  const saveProfile=async(profile,revision,apiKey,checkAfterSave)=>{
    const result=await mutate('/api/model-hub/profile',{
      ack:'SAVE_MODEL_PROFILE',expected_revision:revision,profile,intent:editor.profile?'edit':'create',
      ...(apiKey?{api_key:apiKey}:{}),
    },{inlineError:true});
    setHub(result);setChecked({});setProbes({});setEditor(null);
    message.success('Đã lưu hồ sơ model');
    if(checkAfterSave){
      const saved=result.profiles.find(item=>item.id===profile.id);
      if(saved)void checkProfile(saved,result.revision);
    }
  };

  const deleteProfile=row=>update('/api/model-hub/profile/delete',{
    ack:'DELETE_MODEL_PROFILE',expected_revision:hub.revision,profile_id:row.id,
  },'Xóa hồ sơ model '+row.id+'?',
  'Chỉ xóa hồ sơ cấu hình khỏi SQLite. Không xóa weights hay file của Owner. Nếu hồ sơ đang được phân công, backend sẽ từ chối.');

  const rollback=()=>update('/api/model-hub/rollback',{
    ack:'ROLLBACK_MODEL_HUB',expected_revision:hub.revision,target_revision:hub.revision-1,
  },'Khôi phục cấu hình về phiên bản '+(hub.revision-1)+'?',
  'Danh sách model và chính sách điều phối sẽ được khôi phục cùng nhau. Hệ thống sẽ lưu kết quả thành một phiên bản mới.');

  const profileActions=row=><Space wrap size={6}>
    {profileCapability(row)?.runtime_compatible&&
      <AppTooltip title="Kiểm tra metadata endpoint; không sinh nội dung">
        <Button size="small" loading={checkResult(row)?.pending}
          aria-label={checkResult(row)?.error?'Thử lại':'Kiểm tra'}
          onClick={()=>checkProfile(row)}>{checkResult(row)?.error?'Thử lại':'Kiểm tra'}</Button>
      </AppTooltip>}
    {row.flux&&<Button size="small" disabled={!row.enabled}
      onClick={()=>setFluxProbe({profile:row,revision:hub.revision})}>Chạy thử</Button>}
    {byAdapter[row.provider]?.local_probe&&<>
      <Button size="small" disabled={!row.enabled} onClick={()=>update('/api/model-hub/probe',{
        ack:'RUN_LOCAL_MODEL_PROBE',profile_id:row.id,expected_revision:hub.revision,
      },'Chạy thử model Ollama?',
      'Gọi một lượt local tối đa 32 token đầu ra bằng câu kiểm tra cố định. Có thể nạp model vào RAM hoặc VRAM. Backend cần bật quyền công cụ ngoài.')}>
        Chạy thử
      </Button>
    </>}
    {byAdapter[row.provider]?.cloud_probe&&<Button size="small" disabled={!row.enabled}
      onClick={()=>update('/api/model-hub/probe',{
        ack:'RUN_CLOUD_MODEL_PROBE',profile_id:row.id,expected_revision:hub.revision,
      },'Chạy thử API cloud?',
      'Gửi một prompt JSON cố định tới endpoint đã đăng ký. Có thể phát sinh phí; không gửi nội dung production.')}>Chạy thử</Button>}
    <Button size="small" disabled={!byAdapter[row.provider]} onClick={()=>editProfile(row)}>Sửa</Button>
    <Button size="small" danger icon={<DeleteOutlined/>}
      onClick={()=>deleteProfile(row)}>Xóa</Button>
  </Space>;

  const readiness=row=>{
    const result=checkResult(row);
    const contract=profileCapability(row);
    const status=result?.status??'NOT_CHECKED';
    const reason=result?.reason??(!row.enabled?'DISABLED':null);
    return <Space direction="vertical" size={3} className="model-readiness">
      <SettingsStatus tone={status==='METADATA_COMPATIBLE'?'good':status==='NOT_CHECKED'?'neutral':'warn'}>
        {result?.pending?'Đang kiểm tra…':readinessLabels[status]??status}
      </SettingsStatus>
      {result?.error?<Text type="danger" role="alert">{result.error}</Text>:reason&&
        <Text type="secondary">{readinessReason(reason)}</Text>}
      {result?.checked_at&&<time dateTime={result.checked_at}>{new Date(result.checked_at).toLocaleString('vi-VN')}</time>}
      {contract?.workflow_sha256&&<details className="model-workflow-details"><summary>Workflow và giới hạn</summary>
        <div>{outputSummary(contract.output_limits)}</div><code>{contract.workflow_sha256}</code></details>}
    </Space>;
  };
  const profileInfo=row=><>
    <div>{byAdapter[row.provider]?.connection==='cloud'?'Cloud':'Local'} · {byAdapter[row.provider]?.label||row.provider}</div>
    <div>{row.model}</div>
    {row.capability_contracts&&<div className="model-capability-meta">
      <div>Adapter thực thi: {row.capability_contracts.filter(item=>item.runtime_compatible)
        .map(item=>labels[item.capability]??item.capability).join(', ')||'Không có'}</div>
      <div>Đang gán: {assigned(row).map(item=>item.label).join(', ')||'Chưa gán'}</div>
    </div>}
  </>;

  return <div className="environment-page model-hub">
    <SettingsHeading title="Model AI" eyebrow="HỒ SƠ MODEL"
      description="Chỉ hiển thị model Owner đã đăng ký trong SQLite; không có model mặc định hoặc tự tải."
      actions={<>
        <Button aria-label="Làm mới" icon={<ReloadOutlined/>} onClick={reload} loading={loading}>Làm mới</Button>
        <Button type="primary" icon={<PlusOutlined/>} disabled={!adapters.length} onClick={()=>editProfile(null)}>
          Đăng ký model
        </Button>
      </>}/>
    <ResourceStatus resource={hubResource} label="cấu hình model"/>
    <div className="env-stat-grid model-stat-grid" aria-label="Tổng quan hồ sơ model">
      <Stat icon={<AppstoreOutlined/>} label="Model đã đăng ký" value={hub?profiles.length:'—'}/>
      <Stat icon={<DesktopOutlined/>} label="Hồ sơ local" value={hub?localProfiles:'—'}/>
      <Stat icon={<HistoryOutlined/>} label="Phiên bản cấu hình" value={hub?.revision??'—'}/>
    </div>
    <Card className="env-panel" title={<SectionTitle icon={<AppstoreOutlined/>} title="Danh sách model"
      description="Hồ sơ đã đăng ký và kết quả kiểm tra trong phiên này"/>} loading={loading}>
      <Table className="hub-table" size="middle" rowKey="id" dataSource={profiles}
        pagination={{pageSize:8,hideOnSinglePage:true}} locale={{emptyText:<Empty description="Chưa đăng ký model. Chọn Đăng ký model để bắt đầu."/>}}
        columns={[
          {title:'Hồ sơ',dataIndex:'id',width:170,render:(id,row)=><Space direction="vertical" size={4}>
            <span className="env-runtime-name">{id}</span>
            {!desktop&&
              <details className="hub-details"><summary>Chi tiết</summary>
                {profileInfo(row)}
              </details>}
            {!desktop&&profileActions(row)}
          </Space>},
          {title:'Model và năng lực',responsive:desktopColumns,render:(_,row)=>profileInfo(row)},
          {title:'Trạng thái',render:(_,row)=><Space direction="vertical" size={4}>
            <SettingsStatus tone={row.enabled?'info':'neutral'}>{row.enabled?'Đã bật':'Đã tắt'}</SettingsStatus>
            {readiness(row)}
            {probes[row.id]&&probes[row.id].revision===hub?.revision&&<Text type="secondary" style={{fontSize:11}}>
              {probes[row.id].status==='PASS_RUNTIME'?'Đã chạy thử thành công':'Chạy thử: '+displayStatus(probes[row.id].status)}
              {' · '}{new Date(probes[row.id].checked_at).toLocaleTimeString('vi-VN')}
            </Text>}
          </Space>},
          {title:'Thao tác',responsive:desktopColumns,render:(_,row)=>profileActions(row)},
        ]}/>
    </Card>
    {profiles.length>0&&hub?.routes?.some(route=>route.kind!=='rules')&&<Card className="env-panel"
      title={<SectionTitle icon={<AppstoreOutlined/>} title="Phân công model"
        description="Chọn hồ sơ tương thích cho từng năng lực. Việc phân công chỉ lưu cấu hình."/>}>
      <div className="model-route-list">{hub.routes.filter(route=>route.kind!=='rules').map(route=>{
        const options=configurableProfiles(profiles,route.id);
        return <label key={route.id} className="model-route">
          <strong>{route.label}</strong>
          <Select aria-label={'Model cho '+route.label} value={route.model_ref??''}
            options={[{value:'',label:'Chưa gán'},...options.map(profile=>({value:profile.id,
              label:profile.id+(byAdapter[profile.provider]?.connection==='cloud'?' · Cloud':'')})),
              ...(route.model_ref&&!options.some(profile=>profile.id===route.model_ref)
                ?[{value:route.model_ref,label:route.model_ref+' · Không khả dụng',disabled:true}]:[])]}
            onChange={model=>update(model?'/api/model-hub/route':'/api/model-hub/reset',{
              ack:model?'SET_MODEL_ROUTE':'RESET_MODEL_ROUTE',expected_revision:hub.revision,task_id:route.id,
              ...(model?{model_ref:model}:{}),
            },'Cập nhật phân công model?',route.label+' · '+(model||'Chưa gán'))}/>
        </label>;
      })}</div>
    </Card>}
    <div className="model-history">
      <Button type="text" size="small" icon={<HistoryOutlined/>} disabled={!hub?.revision} onClick={rollback}>
        Khôi phục phiên bản trước
      </Button>
    </div>
    {editor&&<ModelProfileDialog adapters={adapters} profile={editor.profile}
      profiles={profiles} revision={editor.revision} labels={labels} onCancel={()=>setEditor(null)} onSave={saveProfile}
      onReload={reloadEditor}
      onUseRevision={revision=>setEditor(old=>({...old,revision}))}
      onPreview={(profile,revision)=>mutate('/api/model-hub/profile/preview',{
        ack:'PREVIEW_MODEL_PROFILE',expected_revision:revision,profile,
      },{inlineError:true})}/>}
    {fluxProbe&&<FluxProbeDialog {...fluxProbe} mutate={mutate} onCancel={()=>setFluxProbe(null)}/>}
  </div>;
}
