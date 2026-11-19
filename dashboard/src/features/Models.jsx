import { useState } from 'react';
import { App as AntApp, Alert, Button, Card, Empty, Grid,
  Space, Table, Tooltip, Typography } from 'antd';
import {AppstoreOutlined,DeleteOutlined,DesktopOutlined,HistoryOutlined,PlusOutlined,ReloadOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus,Stat} from '../components/settings.jsx';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {displayStatus} from '../environment_format.js';
import {ModelProfileDialog} from './ModelProfileDialog.jsx';
import {FluxProbeDialog,fluxStatus} from './FluxProbeDialog.jsx';

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
          if(path==='/api/model-hub/check') {
            setChecked(old=>({...old,[body.profile_id]:{...result,revision:hub?.revision}}));
          }else if(path==='/api/model-hub/probe') {
            setProbes(old=>({...old,[body.profile_id]:result}));
          }else {
            setHub(result);setChecked({});setProbes({});
          }
          if(path!=='/api/model-hub/probe') {
            message.success(path==='/api/model-hub/check'?'Đã kiểm tra metadata local':'Đã lưu cấu hình local');
          }
          onSuccess?.();
        } else {
          await reload();
        }
      },
    });
  };

  const editProfile=profile=>setEditor({profile,revision:hub.revision});
  const saveProfile=async(profile,revision,apiKey)=>{
    const result=await mutate('/api/model-hub/profile',{
      ack:'SAVE_MODEL_PROFILE',expected_revision:revision,profile,
      ...(apiKey?{api_key:apiKey}:{}),
    },{inlineError:true});
    setHub(result);setChecked({});setProbes({});setEditor(null);
    message.success('Đã lưu hồ sơ model');
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
    {row.flux&&<Button size="small" onClick={()=>update('/api/model-hub/check',{
      ack:'CHECK_LOCAL_MODEL',profile_id:row.id,
    },'Kiểm tra ComfyUI local?','Đọc thông tin GPU và danh sách model của các node loader.')}>
      Kiểm tra ComfyUI
    </Button>}
    {row.flux&&<Button size="small" disabled={!row.enabled}
      onClick={()=>setFluxProbe({profile:row,revision:hub.revision})}>Chạy thử</Button>}
    {byAdapter[row.provider]?.local_probe&&<>
      <Tooltip title="Đọc danh sách model từ Ollama local">
        <Button size="small" onClick={()=>update('/api/model-hub/check',{
          ack:'CHECK_LOCAL_MODEL',profile_id:row.id,
        },'Kiểm tra Ollama local?','Chỉ đọc danh sách model từ localhost trong 3 giây; không inference, không tải model.')}>
          Kiểm tra
        </Button>
      </Tooltip>
      <Button size="small" disabled={!row.enabled} onClick={()=>update('/api/model-hub/probe',{
        ack:'RUN_LOCAL_MODEL_PROBE',profile_id:row.id,expected_revision:hub.revision,
      },'Chạy thử model Ollama?',
      'Gọi một lượt local tối đa 32 token đầu ra bằng câu kiểm tra cố định. Có thể nạp model vào RAM hoặc VRAM. Backend cần bật quyền công cụ ngoài.')}>
        Chạy thử
      </Button>
    </>}
    <Button size="small" disabled={!byAdapter[row.provider]} onClick={()=>editProfile(row)}>Sửa</Button>
    <Button size="small" danger icon={<DeleteOutlined/>}
      onClick={()=>deleteProfile(row)}>Xóa</Button>
  </Space>;

  return <div className="environment-page model-hub">
    <SettingsHeading title="Model AI" eyebrow="HỒ SƠ MODEL"
      description="Chỉ hiển thị model Owner đã đăng ký trong SQLite; không có model mặc định hoặc tự tải."
      actions={<>
        <Button icon={<ReloadOutlined/>} onClick={reload} loading={loading}>Làm mới</Button>
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
      <Table className="hub-table" size="middle" rowKey="id" dataSource={profiles} scroll={desktop?{x:980}:undefined}
        pagination={{pageSize:8,hideOnSinglePage:true}} locale={{emptyText:<Empty description="Chưa đăng ký model. Chọn Đăng ký model để bắt đầu."/>}}
        columns={[
          {title:'Hồ sơ',dataIndex:'id',width:170,render:(id,row)=><Space direction="vertical" size={4}>
            <span className="env-runtime-name">{id}</span>
            {desktop?<Text type="secondary">Owner đăng ký</Text>:
              <details className="hub-details"><summary>Chi tiết</summary>
                <div>{byAdapter[row.provider]?.label||row.provider}</div>
                <div>{row.model}</div>
                <div>Owner đăng ký</div>
              </details>}
            {!desktop&&profileActions(row)}
          </Space>},
          {title:'Nhà cung cấp',dataIndex:'provider',width:205,responsive:desktopColumns,
            render:p=><Text type="secondary">{byAdapter[p]?.label||p}</Text>},
          {title:'Model / Checkpoint',dataIndex:'model',width:220,responsive:desktopColumns,render:m=><Text>{m}</Text>},
          {title:'Trạng thái',width:145,render:(_,row)=><Space direction="vertical" size={2}>
            <SettingsStatus tone={row.enabled?'info':'neutral'}>{row.enabled?'Đã bật':'Đã tắt'}</SettingsStatus>
            {byAdapter[row.provider]?.local_probe&&<Text type="secondary" style={{fontSize:12}}>
              {checked[row.id]&&checked[row.id].revision===hub?.revision
                ?checked[row.id].status==='LOCAL_MODEL_FOUND'?'Đã phát hiện qua Ollama':displayStatus(checked[row.id].status)
                :'Chưa kiểm tra Ollama'}
            </Text>}
            {row.flux&&<Text type="secondary" style={{fontSize:12}}>
              {checked[row.id]?.revision===hub?.revision
                ? <>{fluxStatus[checked[row.id].status]??checked[row.id].status}
                    {checked[row.id].checked_at&&<><br/>Lần kiểm tra: {
                      new Date(checked[row.id].checked_at).toLocaleString('vi-VN')}</>}</>
                : 'Chưa kiểm tra ComfyUI'}
            </Text>}
            {byAdapter[row.provider]?.connection==='cloud'&&
              <Text type="secondary" className="env-muted">Chưa xác minh kết nối</Text>}
            {probes[row.id]&&probes[row.id].revision===hub?.revision&&<Text type="secondary" style={{fontSize:11}}>
              {probes[row.id].status==='PASS_RUNTIME'?'Đã chạy thử thành công':'Chạy thử: '+displayStatus(probes[row.id].status)}
              {' · '}{new Date(probes[row.id].checked_at).toLocaleTimeString('vi-VN')}
            </Text>}
          </Space>},
          {title:'Thao tác',width:250,responsive:desktopColumns,render:(_,row)=>profileActions(row)},
        ]}/>
    </Card>
    <div className="model-history">
      <Button type="text" size="small" icon={<HistoryOutlined/>} disabled={!hub?.revision} onClick={rollback}>
        Khôi phục phiên bản trước
      </Button>
    </div>
    {editor&&<ModelProfileDialog adapters={adapters} profile={editor.profile}
      profiles={profiles} revision={editor.revision} onCancel={()=>setEditor(null)} onSave={saveProfile}/>}
    {fluxProbe&&<FluxProbeDialog {...fluxProbe} mutate={mutate} onCancel={()=>setFluxProbe(null)}/>}
  </div>;
}
