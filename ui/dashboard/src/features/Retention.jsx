import { useCallback, useEffect, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Descriptions, Empty,
  Modal, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { api } from '../api.js';
import { badge, clip } from '../components/shared.jsx';
const { Paragraph, Text, Title } = Typography;

export function Retention({data,mutate}) {
  const {message,modal}=AntApp.useApp();
  const [inventory,setInventory]=useState(null);
  const [backups,setBackups]=useState(null);
  const [inspected,setInspected]=useState({});
  const [verified,setVerified]=useState({});
  const [busy,setBusy]=useState(false);
  const paused=data?.operations?.mode==='PAUSED';

  const refresh=useCallback(async()=>{
    setBusy(true);
    try {
      const [items,snapshots]=await Promise.all([
        api('/api/retention/inventory'),api('/api/retention/backups')]);
      setInventory(items);setBackups(snapshots);
    } catch(err) {message.error(err.message);}
    finally {setBusy(false);}
  },[message]);
  useEffect(()=>{refresh();},[refresh]);
  const key=(item)=>item.kind+':'+item.id;

  const inspect=async item=>{
    setBusy(true);
    try{
      const result=await api('/api/retention/inspect/'+encodeURIComponent(item.kind)+'/'+encodeURIComponent(item.id));
      setInspected(old=>({...old,[key(item)]:result}));
      message.success('Đã kiểm tra SHA của thành phẩm');
    }catch(err){message.error(err.message);}
    finally{setBusy(false);}
  };
  const verify=async row=>{
    setBusy(true);
    try{
      const result=await api('/api/retention/verify/'+encodeURIComponent(row.backup_id));
      setVerified(old=>({...old,[row.backup_id]:result}));
      message.success('ZIP, manifest và từng SHA file đều hợp lệ');
    }catch(err){
      setVerified(old=>({...old,[row.backup_id]:null}));
      message.error(err.message);
    }finally{setBusy(false);}
  };
  const backup=item=>{
    const review=inspected[key(item)];
    if(!review?.tree_sha256){message.warning('Kiểm tra artifact trước khi tạo backup.');return;}
    modal.confirm({
      title:'Tạo bản backup local cho thành phẩm này?',
      width:600,okText:'Tạo backup ZIP',cancelText:'Hủy',
      content:<Space orientation="vertical">
        <Paragraph>Tên: <Text code>{item.kind}/{item.id}</Text>. Nguồn vẫn được giữ nguyên; bản sao nằm ở data/backups/agentforge.</Paragraph>
        <Text>File: {review.file_count} · {(review.total_bytes/1024/1024).toFixed(2)} MiB</Text>
        <Text>Tree SHA-256: <Text code style={{overflowWrap:'anywhere'}}>{review.tree_sha256}</Text></Text>
      </Space>,
      onOk:async()=>{
        const result=await mutate('/api/retention/backup',{
          ack:'BACKUP_ARTIFACT',kind:item.kind,id:item.id,tree_sha:review.tree_sha256});
        if(result){message.success('Đã tạo ZIP và xác minh SHA. Thành phẩm gốc không thay đổi.');await refresh();}
      },
    });
  };
  const move=(row,action)=>{
    const review=verified[row.backup_id];
    if(!review||review.tree_sha256!==row.tree_sha256){
      message.warning('Hãy xác minh chính xác backup trong phiên này trước.');
      return;
    }
    if(!paused){message.warning('Phải PAUSE Operations trước khi quarantine/restore.');return;}
    const isRestore=action==='restore';
    modal.confirm({
      title:isRestore?'Khôi phục thành phẩm từ quarantine?':'Chuyển thành phẩm vào quarantine?',
      width:620,okText:isRestore?'Khôi phục — không ghi đè':'Chuyển vào quarantine',
      okButtonProps:{danger:!isRestore},
      content:<div>
        <Alert type="warning" showIcon style={{marginBottom:14}}
          message={isRestore?'Không ghi đè thư mục thành phẩm đang tồn tại.':'Không xóa vĩnh viễn; chỉ di chuyển thư mục local khỏi danh sách active.'}/>
        <Paragraph>Chỉ thực hiện khi Operations đang PAUSED. Bản ZIP vẫn được giữ nguyên.</Paragraph>
        <Text>Backup ID: <Text code>{row.backup_id}</Text></Text>
        <br/><Text>Tree SHA: <Text code style={{overflowWrap:'anywhere'}}>{review.tree_sha256}</Text></Text>
      </div>,
      onOk:async()=>{
        const result=await mutate('/api/retention/'+action,{
          ack:isRestore?'RESTORE_ARTIFACT':'QUARANTINE_ARTIFACT',
          backup_id:row.backup_id,tree_sha:review.tree_sha256});
        if(result){
          setVerified(old=>({...old,[row.backup_id]:null}));
          setInspected({});
          message.success(isRestore?'Đã khôi phục thành phẩm local':'Đã chuyển vào quarantine (có thể khôi phục)');
          await refresh();
        }
      },
    });
  };

  return <Space orientation="vertical" size={20} style={{width:'100%'}}>
    <Alert type="info" showIcon message="Retention & Cleanup — an toàn theo SHA"
      description="Chỉ sao lưu và di chuyển thành phẩm đã chọn. Không tự xóa sản phẩm, SQLite, task history hoặc dữ liệu khách hàng. Quarantine không giải phóng dung lượng ổ đĩa."/>
    <Alert type={paused?'success':'warning'} showIcon
      message={'Operations: '+(paused?'PAUSED — có thể quarantine/restore sau xác nhận':'ACTIVE — khóa các thao tác thay đổi vị trí thành phẩm')}
      description="Dùng tab Operations để tạm dừng vận hành trước khi chuyển thành phẩm; không có nút thay đổi trạng thái ẩn ở đây."/>
    <Card title="Thành phẩm local (chưa xóa)" extra={<Button icon={<ReloadOutlined/>} loading={busy} onClick={refresh}>Làm mới</Button>}>
      <Table rowKey={key} size="middle" pagination={{pageSize:10}}
        dataSource={inventory?.items||[]} locale={{emptyText:'Chưa có website hoặc media run hợp lệ'}}
        columns={[
          {title:'Nhóm',dataIndex:'kind',render:x=><Tag>{x}</Tag>},
          {title:'Artifact ID',dataIndex:'id',render:x=><Text code>{x}</Text>},
          {title:'Trạng thái',dataIndex:'state',render:badge},
          {title:'Kiểm tra',render:(_,item)=>{
            const receipt=inspected[key(item)];
            return <Space orientation="vertical">
              <Button onClick={()=>inspect(item)} size="small" loading={busy}>Kiểm tra SHA</Button>
              {receipt&&<>
                <Text type="secondary">{receipt.file_count} file / {(receipt.total_bytes/1024/1024).toFixed(2)} MiB</Text>
                <Text code style={{overflowWrap:'anywhere'}}>{receipt.tree_sha256}</Text>
                <Button type="primary" size="small" onClick={()=>backup(item)}>Tạo backup</Button>
              </>}
            </Space>;
          }},
        ]}/>
      <Text type="secondary">Hiển thị {inventory?.items?.length||0}/{inventory?.total_items||0} mục. Không quét hoặc xóa thư mục bất kỳ ngoài workspace/products và workspace/media.</Text>
    </Card>
    <Card title="Bản backup đã ghi nhận">
      <Table rowKey="backup_id" dataSource={backups?.items||[]} pagination={{pageSize:8}}
        locale={{emptyText:'Chưa có bản snapshot đã ghi nhận'}}
        columns={[
          {title:'Backup',render:(_,row)=><Text code>{clip(row.backup_id)}</Text>},
          {title:'Thành phẩm',render:(_,row)=><div><Tag>{row.kind}</Tag><Text code>{row.id}</Text></div>},
          {title:'Trạng thái',dataIndex:'status',render:badge},
          {title:'Bảo vệ',render:(_,row)=>{
            const match=verified[row.backup_id]?.tree_sha256===row.tree_sha256;
            return <Space orientation="vertical" size={8}>
              <Button size="small" onClick={()=>verify(row)} loading={busy}>Verify ZIP & SHA</Button>
              {match&&<Tag color="success" icon={<SafetyCertificateOutlined/>}>Đã verify phiên này</Tag>}
              {row.status==='BACKED_UP'&&
                <Button size="small" danger disabled={!paused||!match}
                  onClick={()=>move(row,'quarantine')}>Quarantine</Button>}
              {row.status==='QUARANTINED'&&
                <Button size="small" type="primary" disabled={!paused||!match}
                  onClick={()=>move(row,'restore')}>Restore</Button>}
            </Space>;
          }},
        ]}/>
      <Alert type="warning" showIcon message="Backup local không thay thế disaster recovery"
        description="Các snapshot riêng lẻ không bao gồm toàn bộ database. Sử dụng ops_backup cho sao lưu nhất quán SQLite. Không gửi ZIP lên cloud."/>
    </Card>
  </Space>;
}
