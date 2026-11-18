import {Alert, Button, Card, Empty, Progress, Table, Typography} from 'antd';
import {AppstoreOutlined, CloudServerOutlined, CodeOutlined, DatabaseOutlined,
  DesktopOutlined, HddOutlined, InfoCircleOutlined, ReloadOutlined,
  SafetyCertificateOutlined, ThunderboltOutlined} from '@ant-design/icons';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {formatGiB, formatMiB, percentUsed, formatChecked, displayStatus,
  statusTone} from '../environment_format.js';

const {Text,Title,Paragraph}=Typography;

function SectionTitle({icon,title,description}){
  return <div className="env-section-heading">
    <span className="env-section-icon" aria-hidden="true">{icon}</span>
    <div><div className="env-section-title">{title}</div>
      <div className="env-section-description">{description}</div></div>
  </div>;
}

function Status({value}){
  return <span className={'env-status tone-'+statusTone(value)} title={value||'UNKNOWN'}>
    <span className="env-status-dot" aria-hidden="true"/>{displayStatus(value)}
  </span>;
}

function Stat({icon,label,value,sub,progress}){
  return <div className="env-stat">
    <div className="env-stat-top"><span className="env-stat-icon" aria-hidden="true">{icon}</span>
      <span className="env-stat-label">{label}</span></div>
    <div className="env-stat-value" title={value}>{value}</div>
    <div className="env-stat-sub">{sub}</div>
    {progress!==null&&progress!==undefined&&
      <Progress percent={progress} showInfo={false} size="small" strokeColor="#7776ee"
        trailColor="var(--env-track)" aria-label={'Đã sử dụng '+progress+'%'} />}
  </div>;
}

function Detail({label,value}){
  return <div className="env-detail">
    <span className="env-detail-label">{label}</span>
    <span className="env-detail-value">{value||'Chưa xác định'}</span>
  </div>;
}

const softwareColumns=[
  {title:'Công cụ',dataIndex:'id',key:'name',width:170,
    render:value=><span className="env-runtime-name">{value}</span>},
  {title:'Trạng thái',dataIndex:'status',key:'status',width:180,
    render:value=><Status value={value}/>},
  {title:'Thông tin phát hiện',key:'details',render:(_,r)=>
    <span className="env-muted env-break">
      {[r.version,r.detail,r.scope].filter(Boolean).join(' · ')||'Chưa có thông tin'}
    </span>},
];
const serviceColumns=[
  {title:'Dịch vụ',dataIndex:'id',key:'name',width:170,
    render:value=><span className="env-runtime-name">{value}</span>},
  {title:'Trạng thái',dataIndex:'status',key:'status',width:180,
    render:value=><Status value={value}/>},
  {title:'Endpoint / chẩn đoán',key:'details',render:(_,r)=>
    <div className="env-service-detail"><span className="env-endpoint">{r.endpoint||'—'}</span>
      {r.error&&<span className="env-diagnostic">{r.error}</span>}
      {r.truncated&&<span className="env-diagnostic">Danh mục bị giới hạn</span>}
    </div>},
];
const modelColumns=[
  {title:'Model',dataIndex:'name',key:'name',
    render:value=><span className="env-runtime-name env-break">{value}</span>},
  {title:'Provider',dataIndex:'provider',key:'provider',width:120},
  {title:'Nhóm',dataIndex:'type',key:'type',width:160},
  {title:'Trạng thái',dataIndex:'status',key:'status',width:155,
    render:value=><Status value={value}/>},
  {title:'Dung lượng',dataIndex:'size_bytes',key:'size',width:130,
    render:value=>typeof value==='number'?formatGiB(value,2):'Chưa rõ'},
];
const profileColumns=[
  {title:'Profile',dataIndex:'id',key:'id',
    render:value=><span className="env-runtime-name env-break">{value}</span>},
  {title:'Model đích',dataIndex:'name',key:'name',
    render:value=><span className="env-break">{value}</span>},
  {title:'Provider',dataIndex:'provider',key:'provider',width:125},
  {title:'Trạng thái',dataIndex:'status',key:'status',width:160,
    render:value=><Status value={value}/>},
];

export function Environment({onNavigate}){
  const scan=useResource('/api/ops/discovery');
  useScreenRefresh(scan.reload);
  const snapshot=scan.data;
  const hw=snapshot?.hardware;
  const gpu=hw?.gpu||{};
  const devices=Array.isArray(gpu.devices)?gpu.devices:[];
  const primaryGpu=devices[0];
  const services=Array.isArray(snapshot?.services)?snapshot.services:[];
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
    <div className="env-page-heading">
      <div>
        <div className="env-eyebrow"><span className="env-eyebrow-dot"/> KIỂM TRA HỆ THỐNG · LOCAL</div>
        <Title level={2} className="env-page-title">Môi trường & Tài nguyên</Title>
        <Paragraph className="env-page-subtitle">
          Tổng quan phần cứng, công cụ và model được phát hiện trên máy này.
          Thông tin kiểm tra không đồng nghĩa AI đã được benchmark.
        </Paragraph>
      </div>
      <div className="env-page-actions">
        <span className="env-checked" aria-live="polite">
          {snapshot?'Lần quét: '+formatChecked(snapshot.checked_at):'Chưa có lượt quét'}
        </span>
        <Button type="primary" icon={<ReloadOutlined/>} onClick={scan.reload}
          loading={scan.loading}>Quét lại</Button>
      </div>
    </div>

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
            (gpu.error||'Chưa có số liệu GPU')}/>
        <Stat icon={<ThunderboltOutlined/>} label="VRAM khả dụng"
          value={primaryGpu?formatMiB(primaryGpu.vram_free_mib):'Chưa xác định'}
          sub={primaryGpu?'Tổng '+formatMiB(primaryGpu.vram_total_mib)+
            (vramUsage!==null?' · Đã dùng '+vramUsage+'%':''):'Đợi phát hiện GPU'}
          progress={vramUsage}/>
        <Stat icon={<DatabaseOutlined/>} label="RAM khả dụng"
          value={formatGiB(memory.available_bytes)}
          sub={'Tổng '+formatGiB(memory.total_bytes)+
            (memoryUsage!==null?' · Đã dùng '+memoryUsage+'%':'')}
          progress={memoryUsage}/>
        <Stat icon={<HddOutlined/>} label="Ổ đĩa workspace"
          value={formatGiB(disk.free_bytes)}
          sub={'Tổng '+formatGiB(disk.total_bytes)+
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
        <div className="env-subheading">Card đồ họa <span>{devices.length} GPU phát hiện</span></div>
        <Table className="env-table" size="middle" rowKey={(_,i)=>String(i)}
          scroll={{x:580}} pagination={false} dataSource={devices}
          locale={{emptyText:gpu.error||'Chưa phát hiện GPU bằng nvidia-smi'}}
          columns={[
            {title:'Thiết bị',dataIndex:'name',key:'gpu',
              render:name=><span className="env-runtime-name">{name}</span>},
            {title:'Driver',dataIndex:'driver_version',key:'driver',width:130},
            {title:'VRAM trống / tổng',key:'vram',width:255,
              render:(_,r)=><div className="env-gpu-memory">
                <span>{formatMiB(r.vram_free_mib)} / {formatMiB(r.vram_total_mib)}</span>
                {percentUsed(r.vram_free_mib,r.vram_total_mib)!==null&&
                  <Progress percent={percentUsed(r.vram_free_mib,r.vram_total_mib)}
                    showInfo={false} size="small" strokeColor="#7776ee"
                    trailColor="var(--env-track)"/>}
              </div>},
          ]}/>
      </Card>

      <Card className="env-panel" title={<SectionTitle icon={<CloudServerOutlined/>}
        title="Phần mềm & dịch vụ"
        description="Tách biệt công cụ đã cài đặt và dịch vụ đang phản hồi"/>}>
        <div className="env-subheading">Công cụ cục bộ <span>{software.length} công cụ</span></div>
        <Table className="env-table" size="middle" pagination={false}
          rowKey={r=>r.id+':'+(r.endpoint||'cli')} scroll={{x:650}}
          dataSource={software} columns={softwareColumns}
          locale={{emptyText:'Chưa có dữ liệu công cụ'}}/>
        <div className="env-subheading env-subheading-separated">
          Dịch vụ local <span>{services.length} endpoint</span>
        </div>
        <Table className="env-table" size="middle" pagination={false}
          rowKey={r=>r.id+':'+(r.endpoint||'service')} scroll={{x:650}}
          dataSource={services} columns={serviceColumns}
          locale={{emptyText:'Chưa phát hiện dịch vụ local'}}/>
      </Card>

      <Card className="env-panel" title={<SectionTitle icon={<AppstoreOutlined/>}
        title="Model được phát hiện"
        description="Danh mục đọc từ Ollama, ComfyUI và profile Owner"/>}
        extra={<Button icon={<CodeOutlined/>} onClick={()=>onNavigate('models')}>
          Cấu hình model
        </Button>}>
        <div className="env-inline-note"><InfoCircleOutlined/>
          <span>Đã phát hiện không có nghĩa model chạy được. Chưa xác minh
            tốc độ, độ phù hợp VRAM hoặc chất lượng sinh.</span>
        </div>
        <div className="env-subheading">Model từ runtime <span>{models.length} model</span></div>
        <Table className="env-table" size="middle" rowKey="id" scroll={{x:760}}
          dataSource={models} pagination={{pageSize:8,hideOnSinglePage:true}}
          columns={modelColumns}
          locale={{emptyText:'Chưa phát hiện model tại các endpoint đã quét'}}
          expandable={{expandedRowRender:model=><Text className="env-break">
            {model.endpoint||'Không rõ endpoint'} · Loadability: {model.loadability||'UNKNOWN'}
            {model.family?' · Family: '+model.family:''}
          </Text>}}/>
        <div className="env-subheading env-subheading-separated">
          Profile đã cấu hình <span>{configured.length} profile</span>
        </div>
        <Table className="env-table" size="middle" rowKey="id" scroll={{x:650}}
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
