import { useEffect, useState } from 'react';
import { Alert, Button, Card, Collapse, Descriptions, Drawer, Input, Space, Tag, Typography } from 'antd';

const { Text, Title, Paragraph } = Typography;
const LABELS = {
  brand:'Thương hiệu',headline:'Tiêu đề',tagline:'Giới thiệu',
  accent:'Màu chủ đạo',categories:'Danh mục',products:'Sản phẩm',
};
const COLOR = /^#[0-9a-fA-F]{6}$/;

export function WebappProposalDrawer({proposal,onClose,onRevise,onApply,busy}) {
  const [feedback,setFeedback]=useState('');
  useEffect(()=>setFeedback(''),[proposal?.proposal_id]);
  if(!proposal)return null;
  const specFile=(proposal.files||[]).find(f=>f.path==='app.json');
  let spec=null;
  try{
    const parsed=JSON.parse(specFile?.content||'null');
    if(parsed?.format==='agentforge.webapp.marketplace.v1')spec=parsed.spec;
  }catch{ /* Invalid files remain visible for review; backend rejects them. */ }
  const comparison=proposal.comparison||{};
  const hasVersion=Boolean(comparison.revision);
  const fields=(comparison.changed_fields||[]).map(f=>LABELS[f]||f);
  const changed=(comparison.changed_files||[]);
  const fileItems=(proposal.files||[]).map(file=>({
    key:file.path,label:file.path+(changed.includes(file.path)?' · đã thay đổi':''),
    children:<pre className="source-text">{file.content}</pre>,
  }));
  return <Drawer title="Duyệt mã nguồn ứng dụng React" open={!!proposal} onClose={onClose}
    size="min(1080px,96vw)" destroyOnHidden>
    <Space orientation="vertical" size={18} style={{width:'100%'}}>
      <Card size="small">
        <Title level={4} style={{margin:'0 0 8px'}}>{proposal.project_slug}</Title>
        <Alert type="warning" showIcon
          message="Đây là mã nguồn nháp, không phải ứng dụng đang chạy"
          description="AI chỉ tạo dữ liệu demo và cấu hình đã kiểm tra; React/Vite dùng mã nguồn được review. Không tự chạy npm, không thanh toán hoặc xuất bản."/>
        <Descriptions size="small" column={1} style={{marginTop:15}} items={[
          {key:'id',label:'Proposal',children:<Text code>{proposal.proposal_id}</Text>},
          {key:'sha',label:'SHA-256',children:<Text code copyable>{proposal.sha256}</Text>},
          {key:'status',label:'Trạng thái',children:proposal.status},
          {key:'files',label:'Số file mã nguồn',children:proposal.files?.length||0},
        ]}/>
      </Card>
      {spec&&<Card size="small" title="Thông tin ứng dụng do AI đề xuất">
        <Space orientation="vertical" size={8}>
          <Text strong>{spec.brand}</Text>
          <Text>{spec.headline}</Text>
          <Text type="secondary">{spec.tagline}</Text>
          <Space wrap><Tag>{spec.categories?.length||0} danh mục</Tag>
            <Tag>{spec.products?.length||0} sản phẩm demo</Tag>
            {COLOR.test(spec.accent||'')&&<Tag color={spec.accent}>Màu chủ đạo {spec.accent}</Tag>}</Space>
        </Space>
      </Card>}
      {hasVersion&&<Card size="small" title="So sánh với phiên bản gốc">
        <Paragraph>Proposal gốc: <Text code copyable>{comparison.source_proposal_id}</Text></Paragraph>
        <Paragraph>SHA gốc: <Text code>{comparison.source_sha256}</Text></Paragraph>
        {fields.length?<><Text strong>Thay đổi hiển thị:</Text>
          <Space wrap style={{margin:'8px 0'}}>{fields.map(f=><Tag key={f}>{f}</Tag>)}</Space></>:
          <Alert type="error" message="Không có thay đổi hiển thị được xác minh"/>}
        <Paragraph type="secondary">File thay đổi: {changed.join(', ')||'Không có'}</Paragraph>
        <Text type="secondary">Phiên bản cũ được giữ nguyên; bản mới sử dụng thư mục riêng, không ghi đè.</Text>
      </Card>}
      <Collapse items={fileItems} style={{width:'100%'}}/>
      <Card size="small" title="Yêu cầu AI chỉnh sửa ứng dụng">
        <Paragraph type="secondary">AI sẽ nhận dữ liệu phiên bản này và góp ý của bạn. Kết quả là proposal mới cần phê duyệt Goal và SHA. Phần logic React vẫn cố định trong mốc V4.1.</Paragraph>
        <Input.TextArea rows={4} maxLength={3000} showCount value={feedback}
          onChange={e=>setFeedback(e.target.value)}
          placeholder="Ví dụ: Đổi màu sang xanh navy, đổi tên gian hàng, bổ sung sản phẩm nhà cửa và giữ nguyên danh mục điện tử..."/>
        <Space wrap style={{display:'flex',justifyContent:'flex-end',marginTop:22}}>
          <Button disabled={feedback.trim().length<10} loading={busy}
            onClick={()=>onRevise(proposal,feedback)}>Tạo kế hoạch chỉnh sửa</Button>
          <Button type="primary" loading={busy} onClick={()=>onApply(proposal)}>
            Duyệt SHA & lưu mã nguồn local
          </Button>
        </Space>
        <Paragraph type="secondary" style={{marginTop:15,marginBottom:0}}>
          Lưu mã nguồn không tự chạy npm hay cài dependencies. Sau khi duyệt, mở workspace/webapps trong PowerShell để tự kiểm thử ứng dụng.
        </Paragraph>
      </Card>
    </Space>
  </Drawer>;
}
