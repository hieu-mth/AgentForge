import { Alert, Button, Space } from 'antd';
import { acceptanceLabel, canAccept } from '../acceptance.js';

export function AcceptanceStatus({acceptance, onDecide, busy}) {
  if (!acceptance) return null;
  const status = acceptance.status;
  const final = ['ACCEPTED', 'REJECTED'].includes(status);
  return <Space orientation="vertical" size={8} style={{width:'100%', margin:'12px 0'}}>
    <Alert showIcon type={status==='ACCEPTED'?'success':status==='NEEDS_REVISION'?'error':'info'}
      message={acceptanceLabel(status)}
      description="Trạng thái nghiệm thu sản phẩm tách biệt với việc task đã thực thi xong. Lưu mã nguồn không phải nghiệm thu hoặc xuất bản."/>
    {onDecide&&!final&&<Space>
      <Button disabled={!canAccept(acceptance)} loading={busy} onClick={()=>onDecide('ACCEPTED')}>
        Owner chấp nhận sản phẩm
      </Button>
      <Button danger loading={busy} onClick={()=>onDecide('REJECTED')}>Từ chối sản phẩm</Button>
    </Space>}
  </Space>;
}
