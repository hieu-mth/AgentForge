import { useCallback, useEffect, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Collapse, Descriptions, Empty,
  Space, Table, Tag, Typography } from 'antd';
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { api } from '../api.js';
import { badge, clip } from '../components/shared.jsx';
const { Paragraph, Text }=Typography;

export function Retention({data,mutate}) {
  const {message,modal}=AntApp.useApp();
  const [inventory,setInventory]=useState(null);
  const [backups,setBackups]=useState(null);
  const [inspection,setInspection]=useState(null);
  const [verified,setVerified]=useState({});
  const [busy,setBusy]=useState(false);
  const paused=data?.operations?.mode==='PAUSED';

  const refresh=useCallback(async()=>{
    setBusy(true);
    try{
      const [items,receipts]=await Promise.all([
        api('/api/retention/inventory'),api('/api/retention/backups')]);
      setInventory(items);
      setBackups(receipts);
    }catch(e){message.error(e.message);}
    finally{setBusy(false);}
  },[message]);
  useEffect(()=>{refresh();},[refresh]);

  const inspect=async(record)=>{
    setBusy(true);
    try{
      const result=await api('/api/retention/inspect/'+record.kind+'/'+record.id);
      setInspection(result); // Server also binds the exact tree SHA to this owner session.
    }catch(e){message.error(e.message);}
    finally{setBusy(false);}
  };
  const backup=()=>{
    if(!inspection)return;
    const inspected=inspection;
    modal.confirm({
      title:'Tạo backup cho một thành phẩm?',
      content:<>
        <Paragraph>Chụp bản ZIP local với SHA từng file. Source không bị thay đổi.
          Backup có thể chứa dữ liệu kinh doanh và không được upload lên cloud.</Paragraph>
        <Paragraph><b>{inspected.kind}: {inspected.id}</b></Paragraph>
        <Text code className="digest">{inspected.tree_sha256}</Text>
      </>,okText:'Tạo bản sao local',cancelText:'Hủy',
      onOk:async()=>{
        const out=await mutate('/api/retention/backup',{
          ack:'BACKUP_ARTIFACT',kind:inspected.kind,id:inspected.id,
          tree_sha:inspected.tree_sha256});
        if(out){message.success('Đã backup, source vẫn giữ nguyên');setInspection(null);await refresh();}
      },
    });
  };
  const verify=async(receipt)=>{
    setBusy(true);
    try{
      const out=await api('/api/retention/verify/'+receipt.backup_id);
      if(out.verified===true){
        setVerified(current=>({...current,[receipt.backup_id]:out.tree_sha256}));
        message.success('ZIP, manifest và SHA từng file hợp lệ');
      }else message.error('Chưa thể xác minh backup');
    }catch(e){message.error(e.message);}
    finally{setBusy(false);}
  };
  const change=(receipt,action)=>{
    const isQuarantine=action==='quarantine';
    if(!paused){message.warning('Chuyển Operations sang PAUSED trước khi thao tác.');return;}
    if(verified[receipt.backup_id]!==receipt.tree_sha256){
      message.warning('Phải xác minh đúng backup trong phiên owner này.');return;
    }
    modal.confirm({
      title:isQuarantine?'Chuyển sản phẩm sang vùng cách ly?':'Phục hồi sản phẩm?',
      content:<>
        <Alert type="warning" showIcon message={isQuarantine?
          'Không xóa vĩnh viễn, nhưng sản phẩm sẽ biến mất khỏi workspace active.':
          'Chỉ phục hồi nếu đường dẫn gốc đang trống, không ghi đè sản phẩm khác.'}/>
        <Paragraph style={{marginTop:12}}>{receipt.kind}: <b>{receipt.id}</b></Paragraph>
        <Text code className="digest">{receipt.tree_sha256}</Text>
        <Paragraph type="secondary">Backup ZIP đã xác minh sẽ được giữ nguyên.</Paragraph>
      </>,
      okText:isQuarantine?'Xác nhận cách ly':'Xác nhận phục hồi',cancelText:'Hủy',
      onOk:async()=>{
        const out=await mutate('/api/retention/'+action,{
          ack:isQuarantine?'QUARANTINE_ARTIFACT':'RESTORE_ARTIFACT',
          backup_id:receipt.backup_id,tree_sha:receipt.tree_sha256});
        if(out){
          message.success(isQuarantine?'Đã chuyển vào vùng cách ly':'Đã phục hồi thành phẩm');
          setVerified(current=>({...current,[receipt.backup_id]:null}));
          await refresh();
        }
      },
    });
  };
  const items=inventory?.items||[],receipts=backups?.items||[];
  return <Space direction="vertical" style={{width:'100%'}} size={18}>
    <Alert type="info" showIcon message="Retention an toàn — không có nút xóa vĩnh viễn"
      description="Workflow: kiểm kê → kiểm tra SHA → tạo ZIP backup → xác minh → tạm dừng Operations → cách ly có thể phục hồi. Không đụng dữ liệu SQLite, proposal history hoặc mã nguồn."/>
    {!paused&&<Alert showIcon type="warning" message="Operations hiện ACTIVE"
      description="Bạn vẫn có thể backup. Muốn cách ly hoặc phục hồi, phải Pause Operations ở trang Operations trước."/>}
    <Card title="Thành phẩm đang hoạt động" extra={<Button icon={<ReloadOutlined/>}
      onClick={refresh} loading={busy}>Làm mới</Button>}>
      <Table rowKey={x=>x.kind+':'+x.id} dataSource={items} pagination={{pageSize:10}}
        columns={[
          {title:'Loại',dataIndex:'kind'},
          {title:'ID',dataIndex:'id',render:v=><Text code>{v}</Text>},
          {title:'Trạng thái',dataIndex:'state',render:badge},
          {title:'Thao tác',render:(_,row)=><Button onClick={()=>inspect(row)}>Kiểm tra SHA</Button>},
        ]}/>
      <Text type="secondary">Tổng {inventory?.total_items||0} thành phẩm local. Chỉ website và media mới có thể được chọn để backup riêng.</Text>
    </Card>
    {inspection&&<Card title={'Kiểm tra: '+inspection.kind+' / '+inspection.id}>
      <Descriptions bordered column={1} items={[
        {key:'1',label:'Số file',children:inspection.file_count},
        {key:'2',label:'Dung lượng',children:(inspection.total_bytes/1048576).toFixed(2)+' MiB'},
        {key:'3',label:'Tree SHA-256',children:<Text code className="digest">{inspection.tree_sha256}</Text>},
      ]}/>
      <Collapse style={{marginTop:14}} items={[{key:'files',label:'Danh sách file & SHA',
        children:<Table rowKey="path" size="small" dataSource={inspection.files||[]}
          pagination={{pageSize:8}} columns={[
            {title:'File',dataIndex:'path'},
            {title:'Bytes',dataIndex:'bytes'},
            {title:'SHA',dataIndex:'sha256',render:v=><Text code>{clip(v)}</Text>},
          ]}/>}]}/>
      <Button type="primary" style={{marginTop:18}} onClick={backup}>
        Tạo backup ZIP và kiểm chứng</Button>
    </Card>}
    <Card title="Backup & Quarantine receipts">
      {receipts.length===0?<Empty description="Chưa có snapshot local"/>:
        <Table rowKey="backup_id" dataSource={receipts} pagination={{pageSize:8}}
          columns={[
            {title:'Backup ID',dataIndex:'backup_id',render:v=><Text code>{clip(v)}</Text>},
            {title:'Sản phẩm',render:(_,r)=><Text>{r.kind} / {r.id}</Text>},
            {title:'Trạng thái',dataIndex:'status',render:badge},
            {title:'Đã xác minh phiên này',render:(_,r)=>
              verified[r.backup_id]===r.tree_sha256?
                <Tag color="success"><CheckCircleOutlined/> SHA hợp lệ</Tag>:<Tag>Chưa xác minh</Tag>},
            {title:'Thao tác',render:(_,row)=><Space wrap>
              <Button onClick={()=>verify(row)}>Xác minh ZIP</Button>
              {row.status==='BACKED_UP'&&<Button danger
                disabled={!paused||verified[row.backup_id]!==row.tree_sha256}
                onClick={()=>change(row,'quarantine')}>Cách ly</Button>}
              {row.status==='QUARANTINED'&&<Button type="primary"
                disabled={!paused||verified[row.backup_id]!==row.tree_sha256}
                onClick={()=>change(row,'restore')}>Phục hồi</Button>}
            </Space>},
          ]}/>}
      <Paragraph type="secondary">Cách ly chỉ chuyển thư mục sang workspace/.quarantine; không giải phóng dung lượng đĩa. ZIP và receipt nằm trong data/backups/agentforge, không được đưa lên Git.</Paragraph>
    </Card>
  </Space>;
}
