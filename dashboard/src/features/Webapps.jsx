import { useEffect, useState } from 'react';
import { AcceptanceStatus } from '../components/AcceptanceStatus.jsx';
import { Alert, Button, Card, Collapse, Descriptions, Drawer, Input, Space, Tag, Typography } from 'antd';

const { Text, Title, Paragraph } = Typography;
const LABELS = {
  brand:'Thương hiệu',headline:'Tiêu đề',tagline:'Giới thiệu',
  accent:'Màu chủ đạo',categories:'Danh mục',products:'Sản phẩm',
};
const COLOR = /^#[0-9a-fA-F]{6}$/;

export function WebappProposalDrawer({proposal,onClose,onRevise,onApply,onVerify,onDecide,onValidate,onRollback,onBrowserQA,busy}) {
  const [feedback,setFeedback]=useState('');
  const isCode=proposal?.ai_code_experimental===true;
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
  const versions=comparison.versions||[];
  const diffs=comparison.diffs||[];
  const fileItems=(proposal.files||[]).map(file=>({
    key:file.path,label:file.path+(changed.includes(file.path)?' · đã thay đổi':''),
    children:<pre className="source-text">{file.content}</pre>,
  }));
  return <Drawer title="Duyệt mã nguồn ứng dụng React" open={!!proposal} onClose={onClose}
    size="min(1080px,96vw)" destroyOnHidden>
    <Space orientation="vertical" size={18} style={{width:'100%'}}>
      <Card size="small">
        <Title level={4} style={{margin:'0 0 8px'}}>{proposal.project_slug}</Title>
        <AcceptanceStatus acceptance={proposal.artifact_acceptance} busy={busy}
          onDecide={onDecide?decision=>onDecide(proposal,decision):null}/>
        <Alert type="warning" showIcon
          message="Đây là mã nguồn nháp, không phải ứng dụng đang chạy"
          description={isCode
            ? 'AI tự viết JSX/CSS và có thể sửa từng file bằng feedback/phiên bản mới. Diff/cú pháp không chứng minh ứng dụng chạy đúng. Không chạy source trên host; cần QA cách ly riêng.'
            : 'AI chỉ tạo dữ liệu demo và cấu hình đã kiểm tra; React/Vite dùng mã nguồn được review. Không tự chạy npm, không thanh toán hoặc xuất bản.'}/>
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
        {diffs.length>0&&<Collapse size="small" items={diffs.map(d=>({
          key:d.path,label:'Diff: '+d.path+(d.truncated?' (rút gọn)':''),
          children:<pre className="source-text">{d.diff}</pre>,
        }))}/>}
        <Text type="secondary">Phiên bản cũ được giữ nguyên; bản mới sử dụng thư mục riêng, không ghi đè.</Text>
      </Card>}
      {isCode&&versions.length>1&&<Card size="small" title="Lịch sử phiên bản & khôi phục">
        <Alert type="info" showIcon style={{marginBottom:12}}
          message="Khôi phục source thành proposal mới"
          description="Chỉ được chọn tổ tiên đã xác minh SHA. Trước khi duyệt bạn sẽ xem mã nguồn phiên bản đích. Không gọi model, không ghi đè project cũ, không tự chạy hoặc deploy."/>
        <Space orientation="vertical" style={{width:'100%'}}>
          {versions.slice(1).map(version=><Space key={version.proposal_id} wrap>
            <Text code>{version.project_slug} · {version.sha256.slice(0,12)}</Text>
            <Button size="small" disabled={busy} onClick={()=>onRollback?.(proposal,version)}>
              Xem source & tạo bản khôi phục</Button>
          </Space>)}
        </Space>
      </Card>}
      <Collapse items={fileItems} style={{width:'100%'}}/>
      <Card size="small" title={isCode?'Duyệt mã nguồn AI thử nghiệm':'Yêu cầu AI chỉnh sửa ứng dụng'}>
        <Paragraph type="secondary">{isCode
          ? 'AI sẽ đọc source từ đúng proposal và SHA, chỉ đề xuất những file cần sửa. File cũ giữ nguyên; kết quả có diff và cần Owner phê duyệt Goal riêng. Chưa build/browser QA tự động.'
          : 'AI sẽ nhận dữ liệu phiên bản này và góp ý của bạn. Kết quả là proposal mới cần phê duyệt Goal và SHA. Phần logic React vẫn cố định trong mốc V4.1.'}</Paragraph>
        <Input.TextArea rows={4} maxLength={3000} showCount value={feedback}
          onChange={e=>setFeedback(e.target.value)}
          placeholder="Ví dụ: Đổi màu sang xanh navy, sửa giao diện giỏ hàng, giữ nguyên sản phẩm và các tương tác khác..."/>
        <Space wrap style={{display:'flex',justifyContent:'flex-end',marginTop:22}}>
          <Button loading={busy} onClick={()=>onValidate?.(proposal)}>Kiểm tra cú pháp</Button>
          <Button disabled={feedback.trim().length<10} loading={busy}
            onClick={()=>onRevise(proposal,feedback)}>Tạo kế hoạch chỉnh sửa</Button>
          <Button loading={busy} onClick={()=>onVerify(proposal)}>
            QA build Docker
          </Button>
          <Button loading={busy} onClick={()=>onBrowserQA?.(proposal)}>
            QA Chromium offline
          </Button>
          <Button href={'/api/webapps/'+proposal.proposal_id+'/export'}
            target="_self" download loading={busy}>
            Tải ZIP source + SHA
          </Button>
          <Button type="primary" loading={busy} onClick={()=>onApply(proposal)}>
            Duyệt SHA & lưu mã nguồn local
          </Button>
        </Space>
        <Paragraph type="secondary" style={{marginTop:15,marginBottom:0}}>
          {isCode
            ? 'Lưu mã nguồn không làm mã AI trở nên đáng tin cậy. Không chạy npm trực tiếp trên Windows với dự án AI thử nghiệm; trước tiên sử dụng QA Docker được duyệt riêng.'
            : 'Lưu mã nguồn không tự chạy npm hay cài dependencies. Sau khi duyệt, mở workspace/webapps trong PowerShell để tự kiểm thử ứng dụng.'}
        </Paragraph>
      </Card>
    </Space>
  </Drawer>;
}
