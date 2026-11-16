import {Alert, Button, Card, Descriptions, Space, Table, Typography} from 'antd';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {badge} from '../components/shared.jsx';

const {Text} = Typography;

function bytes(value) {
  return Number.isFinite(value) ? (value / 2 ** 30).toLocaleString('vi-VN', {
    maximumFractionDigits: 2,
  }) + ' GiB' : 'Chưa xác định';
}

const statusColumn = {title:'Trạng thái', dataIndex:'status', render:badge};

export function Environment({onNavigate}) {
  const scan = useResource('/api/ops/discovery');
  useScreenRefresh(scan.reload);
  const snapshot = scan.data;
  const hw = snapshot?.hardware;
  return <Space orientation="vertical" size={16} style={{width:'100%'}}>
    <Card title="Máy chạy AgentForge" extra={<Button onClick={scan.reload} loading={scan.loading}>Quét lại</Button>}>
      <ResourceStatus resource={scan} label="môi trường"/>
      {hw && <>
        <Descriptions size="small" column={{xs:1, md:2}} items={[
          {key:'os', label:'Hệ điều hành', children:[hw.os, hw.os_release].join(' ')},
          {key:'cpu', label:'CPU', children:[hw.cpu, hw.logical_cpu_count && hw.logical_cpu_count+' luồng'].filter(Boolean).join(' · ')},
          {key:'ram', label:'RAM khả dụng / tổng', children:bytes(hw.memory.available_bytes)+' / '+bytes(hw.memory.total_bytes)},
          {key:'disk', label:'Ổ workspace trống / tổng', children:bytes(hw.disk.free_bytes)+' / '+bytes(hw.disk.total_bytes)},
          {key:'checked', label:'Lần kiểm tra', children:new Date(snapshot.checked_at).toLocaleString('vi-VN')},
          {key:'cuda', label:'CUDA Toolkit', children:hw.gpu.cuda_toolkit?.version || hw.gpu.cuda_toolkit?.status || 'Chưa xác định'},
        ]}/>
        <Table size="small" pagination={false} rowKey={(_,i)=>i} dataSource={hw.gpu.devices}
          locale={{emptyText:hw.gpu.error || 'Chưa xác minh GPU'}}
          scroll={{x:450}} columns={[
            {title:'GPU', dataIndex:'name'},
            {title:'Driver', dataIndex:'driver_version'},
            {title:'VRAM trống / tổng (MiB)', render:(_,g)=>
              [g.vram_free_mib ?? '—',g.vram_total_mib ?? '—'].join(' / ')},
          ]}/>
      </>}
    </Card>
    {snapshot && <>
      <Card title="Phần mềm và runtime">
        <Table size="small" pagination={false} rowKey={r=>r.id+':'+(r.endpoint||'')} scroll={{x:520}}
          dataSource={[...snapshot.software,...snapshot.services,{id:'Browser QA',...snapshot.browser_qa}]}
          columns={[
            {title:'Runtime', dataIndex:'id'},
            statusColumn,
            {title:'Chi tiết', render:(_,r)=>[r.endpoint,r.version,r.detail,r.error,r.scope].filter(Boolean).join(' · ')},
          ]}/>
      </Card>
      <Card title="Model tìm thấy" extra={<Button onClick={()=>onNavigate('models')}>Cấu hình model</Button>}>
        <Alert showIcon type="info" message="Danh sách từ runtime local"
          description="Trạng thái Installed xác nhận model được liệt kê. Loadability, chất lượng sinh và tốc độ cần smoke test riêng."/>
        {(snapshot.config_error||snapshot.endpoints_truncated||snapshot.services.some(s=>s.truncated))&&
          <Alert showIcon type="warning" message="Danh mục chưa đầy đủ" description={snapshot.config_error || 'Đã chạm giới hạn quét.'}/>}
        <Table size="small" rowKey="id" scroll={{x:640}} dataSource={snapshot.models}
          locale={{emptyText:'Không có model trong các endpoint đã quét'}}
          columns={[
            {title:'Model', dataIndex:'name'},
            {title:'Runtime', dataIndex:'provider'},
            {title:'Loại', dataIndex:'type'},
            statusColumn,
            {title:'Dung lượng', dataIndex:'size_bytes', render:bytes},
          ]}
          expandable={{expandedRowRender:model=><Text>
            {model.endpoint} · Loadability {model.loadability}{model.family&&' · Family '+model.family}
          </Text>}}/>
        <Table size="small" rowKey="id" scroll={{x:540}} pagination={false}
          dataSource={snapshot.configured_models}
          columns={[
            {title:'Profile cấu hình', dataIndex:'id'}, {title:'Model đích', dataIndex:'name'},
            {title:'Provider', dataIndex:'provider'}, statusColumn,
          ]}/>
      </Card>
    </>}
  </Space>;
}
