import { useEffect, useState } from 'react';
import { AcceptanceStatus } from '../components/AcceptanceStatus.jsx';
import { Alert, Button, Card, Collapse, Drawer, Input, Segmented, Space, Table, Typography } from 'antd';
import { badge, clip, needPreviewId } from '../components/shared.jsx';
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const FONT_LABELS={modern:'Hiện đại',editorial:'Thanh lịch',rounded:'Mềm mại',technical:'Công nghệ'};
const HERO_LABELS={split:'Chia đôi',centered:'Căn giữa',stacked:'Xếp dọc',editorial:'Phong cách tạp chí'};


export function Websites({data, showProposal}) {
  const proposals=(data?.tasks||[]).filter(x=>x.web_proposal);
  return <Card className="panel" title="Landing page AI" extra={<Text type="secondary">Chỉ duyệt sau khi xem bản preview</Text>}>
    <Table rowKey={x=>x.task_id} scroll={{x:"max-content"}} pagination={{pageSize:8,hideOnSinglePage:true}} dataSource={proposals}
      locale={{emptyText:'Chưa có bản nháp website.'}} columns={[
        {title:'Project',render:(_,t)=><b>{t.web_proposal.slug}</b>},
        {title:'Proposal',render:(_,t)=><code>{clip(t.web_proposal.proposal_id)}</code>},
        {title:'Trạng thái',render:()=>badge('PROPOSED_NOT_APPLIED')},
        {title:'Hành động',render:(_,t)=><Button type="primary" ghost
          onClick={()=>showProposal(t.web_proposal.proposal_id)}>Xem website</Button>},
      ]}/>
  </Card>;
}

export function ProposalDrawer({proposal, onClose, onRevise, onApply, onDecide, onValidate, busy}) {
  const [device,setDevice]=useState('desktop');
  const [feedback,setFeedback]=useState('');
  useEffect(()=>{setFeedback('');setDevice('desktop');},[proposal?.proposal_id]);
  if (!proposal) return null;
  const designFile=(proposal.files||[]).find(file=>file.path==='site.json');
  let design=null;
  try{if(designFile?.content){const record=JSON.parse(designFile.content);design=record?.format==='agentforge.design.v1'?record.design:null;}}catch{design=null;}
  const id=proposal.proposal_id, allowed=needPreviewId(id);
  return <Drawer title="Xem trước & phê duyệt website" open={!!proposal} onClose={onClose}
    size="min(1120px, 96vw)" destroyOnHidden extra={badge(proposal.status)}>
    <Space orientation="vertical" style={{width:'100%'}} size={18}>
      <div className="preview-toolbar">
        <div><Title level={4} style={{marginBottom:0}}>{proposal.project_slug}</Title>
          <Text type="secondary">Bản nháp được cách ly, không chạy script hoặc tải tài nguyên ngoài</Text></div>
        <Segmented options={[{label:'Desktop',value:'desktop'},{label:'Mobile',value:'mobile'}]}
          value={device} onChange={setDevice}/>
      </div>
      {design?.style && Array.isArray(design.sections) && <Card size="small"
        title="Thiết kế riêng do AI lựa chọn">
        <Space wrap>
          <Text>Kiểu chữ: <strong>{FONT_LABELS[design.style.font]||'Theo AI'}</strong></Text>
          <Text>Bố cục mở đầu: <strong>{HERO_LABELS[design.style.hero_layout]||'Theo AI'}</strong></Text>
          <Text>Bảng màu: <Text code>{[design.style.background,design.style.surface,design.style.accent].join(' · ')}</Text></Text>
          <Text>Mục nội dung: <strong>{design.sections.length}</strong></Text>
        </Space>
        <Paragraph type="secondary" style={{margin:'8px 0 0'}}>
          {design.sections.map(item=>item.title).join(' → ')}
        </Paragraph>
      </Card>}
      <div className="preview-stage">
        {allowed ? <iframe className={'preview-iframe '+(device==='mobile'?'mobile':'desktop')}
          title={'Xem trước website '+proposal.project_slug} sandbox=""
          referrerPolicy="no-referrer" src={'/api/proposals/'+id+'/preview'}/> :
          <Alert type="error" message="Proposal ID không hợp lệ"/>}
      </div>
      <Collapse items={[{key:'source',label:'Mã nguồn và SHA (nâng cao)',
        children:<>
          <Text code className="digest">{proposal.sha256}</Text>
          {(proposal.files||[]).map(f=><div key={f.path}><Text strong>{f.path}</Text>
            <pre className="source-text">{f.content}</pre></div>)}
        </>} ]}/>
      <Card size="small" className="feedback-card">
        <AcceptanceStatus acceptance={proposal.artifact_acceptance} busy={busy}
          onDecide={onDecide?decision=>onDecide(proposal,decision):null}/>
        <Title level={5}>Chưa ưng? Yêu cầu AI chỉnh sửa</Title>
        <Paragraph type="secondary">Góp ý sẽ dùng chính website đang xem làm bản gốc, tạo bản sửa mới để duyệt; không ghi đè bản cũ.</Paragraph>
        <Alert type="info" showIcon style={{marginBottom:12}}
          message="AI có thể thiết kế lại toàn trang"
          description="Có thể đổi thứ tự/số lượng section, màu HEX, font, hero, kiểu thẻ và nội dung. Không tự viết JavaScript hoặc gọi Internet. Nếu không có thay đổi hiển thị, hệ thống sẽ báo lỗi thay vì trả lại bản y hệt."/>
        <TextArea rows={3} maxLength={3000} showCount value={feedback}
          onChange={e=>setFeedback(e.target.value)}
          placeholder="Ví dụ: Thay hero sang phong cách tạp chí, đổi bảng màu sang kem và nâu, thêm mục câu hỏi thường gặp, giữ nút tư vấn rõ trên điện thoại..."/>
        <Space wrap style={{marginTop:20,justifyContent:'flex-end',width:'100%'}}>
          <Button loading={busy} onClick={()=>onValidate?.(proposal)}>Kiểm tra bản nháp</Button>
          <Button loading={busy} disabled={feedback.trim().length<10}
            onClick={()=>onRevise(proposal,feedback)}>Yêu cầu chỉnh sửa</Button>
          <Button type="primary" loading={busy} onClick={()=>onApply(proposal)}>
            Duyệt & lưu website local</Button>
        </Space>
      </Card>
    </Space>
  </Drawer>;
}

