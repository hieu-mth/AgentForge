import {Alert, Button, Card, Empty, Grid, Table, Tooltip, Typography} from 'antd';
import {AppstoreOutlined, CloudServerOutlined, CodeOutlined, DatabaseOutlined,
  DesktopOutlined, HddOutlined, InfoCircleOutlined, ReloadOutlined,
  SafetyCertificateOutlined, ThunderboltOutlined} from '@ant-design/icons';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {formatCapacity, formatMemory, formatVram, percentUsed, formatChecked, displayStatus,
  statusTone} from '../environment_format.js';

import {SectionTitle,SettingsHeading,SettingsStatus,Stat} from '../components/settings.jsx';

const {Text}=Typography;

function Status({value}){
  return <SettingsStatus tone={statusTone(value)} title={value||'UNKNOWN'}>
    {displayStatus(value)}
  </SettingsStatus>;
}

function Detail({label,value}){
  return <div className="env-detail">
    <span className="env-detail-label">{label}</span>
    <span className="env-detail-value">{value||'Chưa xác định'}</span>
  </div>;
}

function MobileDetails({children}){
  if(!children)return null;
  return <details className="env-mobile-details">
    <summary>Chi tiết</summary>
    <div className="env-break">{children}</div>
  </details>;
}

const diagnosticLabels={
  NVIDIA_SMI_NOT_FOUND:'Không tìm thấy công cụ NVIDIA',
  CONNECTION_REFUSED:'Dịch vụ không nhận kết nối',
  TIMEOUT:'Dịch vụ phản hồi quá chậm',
  COMFYUI_TIMEOUT:'ComfyUI phản hồi quá chậm',
  COMFYUI_UNAVAILABLE:'Không kết nối được ComfyUI',
  AUTH_REQUIRED:'ComfyUI yêu cầu xác thực',
  COMFYUI_HTTP_ERROR:'ComfyUI trả lỗi HTTP',
  COMFYUI_INVALID_RESPONSE:'Phản hồi ComfyUI không hợp lệ',
  INVALID_OR_UNAVAILABLE_RESPONSE:'Dịch vụ không trả về dữ liệu hợp lệ',
};
function Diagnostic({code}){
  return <details className="env-diagnostic env-break">
    <summary>{diagnosticLabels[code]??'Không đọc được dữ liệu chẩn đoán'}</summary>
    <code>{code}</code>
  </details>;
}

const desktopColumns=['sm'];
const softwareDetails=row=>
  [row.version,row.detail,row.scope].filter(Boolean).join(' · ')||'Chưa có thông tin';
const serviceDetails=row=><div className="env-service-detail">
  <span className="env-endpoint">{row.endpoint||'—'}</span>
  {row.checked_at&&<span className="env-muted">Lần kiểm tra: {formatChecked(row.checked_at)}</span>}
  {row.error&&<Diagnostic code={row.error}/>}
  {Object.keys(row.catalog_errors??{}).length>0&&
    <span className="env-diagnostic">Chưa đọc được một phần danh mục model</span>}
  {row.truncated&&<span className="env-diagnostic">Danh mục bị giới hạn</span>}
</div>;
const modelSize=value=>typeof value==='number'?formatCapacity(value,2):'Chưa rõ';
const servicePriority=row=>({bad:0,warn:1})[statusTone(row.status)]??2;

const softwareColumns=[
  {title:'Công cụ',dataIndex:'id',key:'name',width:170,
    render:(value,row)=><><span className="env-runtime-name env-break">{value}</span>
      <MobileDetails>{softwareDetails(row)}</MobileDetails></>},
  {title:'Trạng thái',dataIndex:'status',key:'status',width:180,
    render:value=><Status value={value}/>},
  {title:'Thông tin phát hiện',key:'details',responsive:desktopColumns,
    render:(_,row)=><span className="env-muted env-break">{softwareDetails(row)}</span>},
];
const serviceColumns=[
  {title:'Dịch vụ',dataIndex:'id',key:'name',width:170,
    render:(value,row)=><><span className="env-runtime-name env-break">{value}</span>
      <MobileDetails>{serviceDetails(row)}</MobileDetails></>},
  {title:'Tại lần kiểm tra',dataIndex:'status',key:'status',width:180,
    render:(value,row)=>row.scanPending?'Đang kiểm tra…':row.scanFailed?'Bản quét cũ':<Status value={value}/>},
  {title:'Endpoint / chẩn đoán',key:'details',responsive:desktopColumns,
    render:(_,row)=>serviceDetails(row)},
];
const modelColumns=[
  {title:'Model',dataIndex:'name',key:'name',
    render:value=><span className="env-runtime-name env-break">{value}</span>},
  {title:'Provider',dataIndex:'provider',key:'provider',width:120,responsive:desktopColumns},
  {title:'Nhóm',dataIndex:'type',key:'type',width:160,responsive:desktopColumns},
  {title:'Trạng thái',dataIndex:'status',key:'status',width:155,
    render:(value,row)=><><Status value={value==='INSTALLED'?'LOCAL_MODEL_FOUND':value}/>
      {(!row.loadability||row.loadability==='UNKNOWN')&&
        <div className="env-model-verification">Chưa xác minh khả năng chạy</div>}</>},
  {title:'Dung lượng',dataIndex:'size_bytes',key:'size',width:130,responsive:desktopColumns,
    render:modelSize},
];
const profileColumns=[
  {title:'Profile',dataIndex:'id',key:'id',
    render:(value,row)=><><span className="env-runtime-name env-break">{value}</span>
      <MobileDetails>{[row.name,row.provider].filter(Boolean).join(' · ')}</MobileDetails></>},
  {title:'Model đích',dataIndex:'name',key:'name',responsive:desktopColumns,
    render:value=><span className="env-break">{value}</span>},
  {title:'Provider',dataIndex:'provider',key:'provider',width:125,responsive:desktopColumns},
  {title:'Trạng thái',dataIndex:'status',key:'status',width:160,
    render:value=><Status value={value}/>},
];

export function Environment({onNavigate}){
  const scan=useResource('/api/ops/discovery');
  const {sm}=Grid.useBreakpoint();
  useScreenRefresh(scan.reload);
  const snapshot=scan.data;
  const hw=snapshot?.hardware;
  const gpu=hw?.gpu||{};
  const devices=Array.isArray(gpu.devices)?gpu.devices:[];
  const primaryGpu=devices[0];
  const services=Array.isArray(snapshot?.services)?snapshot.services:[];
  const orderedServices=services.map(row=>({...row,scanPending:scan.loading,scanFailed:Boolean(scan.error)}))
    .sort((a,b)=>servicePriority(a)-servicePriority(b));
  const software=Array.isArray(snapshot?.software)?snapshot.software:[];
  const models=Array.isArray(snapshot?.models)?snapshot.models:[];
  const configured=Array.isArray(snapshot?.configured_models)?snapshot.configured_models:[];
  const memory=hw?.memory||{};
  const disk=hw?.disk||{};
  const vramUsage=primaryGpu?percentUsed(primaryGpu.vram_free_mib,primaryGpu.vram_total_mib):null;
  const memoryUsage=percentUsed(memory.available_bytes,memory.total_bytes);
  const diskUsage=percentUsed(disk.free_bytes,disk.total_bytes);
  const incomplete=snapshot&&(snapshot.config_error||snapshot.endpoints_truncated||
    services.some(s=>s.truncated));

  return <div className="environment-page" data-testid="environment-page">
    <SettingsHeading title="Môi trường & Tài nguyên" eyebrow="KIỂM TRA HỆ THỐNG · LOCAL"
      description="Tổng quan phần cứng, công cụ và model được phát hiện trên máy này. Thông tin kiểm tra không đồng nghĩa AI đã được benchmark."
      actions={<>
        <span className="env-checked" aria-live="polite">
          {snapshot?'Lần quét: '+formatChecked(snapshot.checked_at):'Chưa có lượt quét'}
        </span>
        <Button type="primary" icon={<ReloadOutlined/>} onClick={scan.reload}
          loading={scan.loading}>Quét lại</Button>
      </>}/>

    <ResourceStatus resource={scan} label="môi trường"/>
    {!snapshot&&<Card className="env-panel">
      {scan.loading?<div className="env-placeholder" role="status">
        Đang kiểm tra môi trường local…</div>:
        <Empty description="Chưa có dữ liệu hệ thống">
          <Button onClick={scan.reload}>Thử quét lại</Button>
        </Empty>}
    </Card>}

    {snapshot&&<>
      {incomplete&&<Alert className="env-warning" type="warning" showIcon
        message="Danh mục chưa đầy đủ" description={snapshot.config_error||
          'Một số endpoint hoặc danh mục model chưa được quét đầy đủ.'}/>}

      <div className="env-stat-grid" aria-label="Chỉ số tài nguyên">
        <Stat icon={<DesktopOutlined/>} label="GPU chính"
          value={primaryGpu?.name||'Chưa phát hiện'}
          sub={primaryGpu?'Driver '+(primaryGpu.driver_version||'chưa rõ'):
            (gpu.error?<Diagnostic code={gpu.error}/>:'Chưa có số liệu GPU')}/>
        <Stat icon={<ThunderboltOutlined/>} label="VRAM khả dụng"
          value={primaryGpu?formatVram(primaryGpu.vram_free_mib):'Chưa xác định'}
          sub={primaryGpu?'Tổng '+formatVram(primaryGpu.vram_total_mib)+
            (vramUsage!==null?' · Đã dùng '+vramUsage+'%':''):'Đợi phát hiện GPU'}
          progress={vramUsage}/>
        <Stat icon={<DatabaseOutlined/>} label="RAM khả dụng"
          value={formatMemory(memory.available_bytes)}
          sub={'Tổng '+formatMemory(memory.total_bytes)+
            (memoryUsage!==null?' · Đã dùng '+memoryUsage+'%':'')}
          progress={memoryUsage}/>
        <Stat icon={<HddOutlined/>} label={<>Ổ đĩa workspace <Tooltip
          title="Ổ đĩa, RAM và VRAM dùng hệ 1.024 như Windows. Dung lượng model dùng hệ 1.000."
          trigger={['hover','focus']}><button className="env-unit-help" type="button"
            aria-label="Quy ước đơn vị dung lượng"><InfoCircleOutlined/></button></Tooltip></>}
          value={formatMemory(disk.free_bytes)}
          sub={'Tổng '+formatMemory(disk.total_bytes)+
            (diskUsage!==null?' · Đã dùng '+diskUsage+'%':'')}
          progress={diskUsage}/>
      </div>

      <Card className="env-panel" title={<SectionTitle icon={<DesktopOutlined/>}
        title="Máy chạy AgentForge"
        description="Thông số phần cứng phát hiện tại lượt quét gần nhất"/>}>
        <div className="env-detail-grid">
          <Detail label="Hệ điều hành" value={[hw?.os,hw?.os_release].filter(Boolean).join(' ')}/>
          <Detail label="CPU" value={[hw?.cpu,
            hw?.logical_cpu_count?hw.logical_cpu_count+' luồng':''].filter(Boolean).join(' · ')}/>
          <Detail label="Kiến trúc" value={hw?.architecture}/>
          <Detail label="CUDA Toolkit" value={gpu.cuda_toolkit?.version||
            gpu.cuda_toolkit?.status||'Chưa xác minh'}/>
        </div>
      </Card>

      <Card className="env-panel" title={<SectionTitle icon={<CloudServerOutlined/>}
        title="Phần mềm & dịch vụ"
        description="Tách biệt công cụ đã cài đặt và dịch vụ đang phản hồi"/>}>
        <div className="env-subheading">Công cụ cục bộ <span>{software.length} công cụ</span></div>
        <Table className="env-table" size="middle" pagination={false}
          rowKey={r=>r.id+':'+(r.endpoint||'cli')} scroll={sm?{x:650}:undefined}
          dataSource={software} columns={softwareColumns}
          locale={{emptyText:'Chưa có dữ liệu công cụ'}}/>
        <div className="env-subheading env-subheading-separated">
          Dịch vụ local <span>{services.length} endpoint</span>
        </div>
        <Table className="env-table" size="middle" pagination={false}
          rowKey={r=>r.id+':'+(r.endpoint||'service')} scroll={sm?{x:650}:undefined}
          dataSource={orderedServices} columns={serviceColumns}
          locale={{emptyText:'Chưa phát hiện dịch vụ local'}}/>
      </Card>

      <Card className="env-panel" title={<SectionTitle icon={<AppstoreOutlined/>}
        title="Model & cấu hình"
        description="Danh mục đọc từ Ollama, ComfyUI và profile Owner"/>}
        extra={<Button icon={<CodeOutlined/>} onClick={()=>onNavigate('models')}>
          Cấu hình model
        </Button>}>
        <div className="env-subheading">Model từ runtime <span>{models.length} model</span></div>
        <Table className="env-table" size="middle" rowKey="id" scroll={sm?{x:760}:undefined}
          dataSource={models} pagination={{pageSize:8,hideOnSinglePage:true}}
          columns={modelColumns}
          locale={{emptyText:'Chưa phát hiện model tại các endpoint đã quét'}}
          expandable={{expandedRowRender:model=><div className="env-break">
            <Text>Endpoint: {model.endpoint||'Chưa rõ'} · Khả năng chạy: {displayStatus(model.loadability||'UNKNOWN')}</Text>
            {model.family&&<div>Họ model: {model.family}</div>}
            {!sm&&<div>{[model.provider,model.type,modelSize(model.size_bytes)].filter(Boolean).join(' · ')}</div>}
          </div>}}/>
        <div className="env-subheading env-subheading-separated">
          Profile đã cấu hình <span>{configured.length} profile</span>
        </div>
        <Table className="env-table" size="middle" rowKey="id" scroll={sm?{x:650}:undefined}
          pagination={{pageSize:6,hideOnSinglePage:true}} dataSource={configured}
          columns={profileColumns}
          locale={{emptyText:'Chưa có profile model trong cấu hình'}}/>
      </Card>
      <div className="env-disclaimer"><SafetyCertificateOutlined/>
        Chỉ đọc dữ liệu local. Lượt quét không kích hoạt model, không dựng video và
        không kết nối dịch vụ cloud.
      </div>
    </>}
  </div>;
}
