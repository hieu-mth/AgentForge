import { useEffect, useState } from 'react';
import { Alert, Button, Card, Collapse, Drawer, Input, Segmented, Space, Table, Typography } from 'antd';
import { badge, clip, needPreviewId } from '../components/shared.jsx';
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

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

export function ProposalDrawer({proposal, onClose, onRevise, onApply, busy}) {
  const [device,setDevice]=useState('desktop');
  const [feedback,setFeedback]=useState('');
  useEffect(()=>{setFeedback('');setDevice('desktop');},[proposal?.proposal_id]);
  if (!proposal) return null;
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
        <Title level={5}>Chưa ưng? Yêu cầu AI chỉnh sửa</Title>
        <Paragraph type="secondary">Góp ý sẽ dùng chính website đang xem làm bản gốc, tạo bản sửa mới để duyệt; không ghi đè bản cũ.</Paragraph>
        <Alert type="info" showIcon style={{marginBottom:12}}
          message="Có thể đổi nội dung, bảng màu và bố cục hero"
          description="Hiện chưa hỗ trợ tự thêm tính năng ứng dụng hoặc mã JavaScript tùy ý. Nếu AI không tạo thay đổi hiển thị, công việc sẽ báo lỗi thay vì trả bản y hệt."/>
        <TextArea rows={3} maxLength={3000} showCount value={feedback}
          onChange={e=>setFeedback(e.target.value)}
          placeholder="Ví dụ: Hero nhìn còn thô, thay bố cục cho sang trọng hơn, có hình ảnh nệm và CTA rõ ràng trên điện thoại..."/>
        <Space wrap style={{marginTop:20,justifyContent:'flex-end',width:'100%'}}>
          <Button loading={busy} disabled={feedback.trim().length<10}
            onClick={()=>onRevise(proposal,feedback)}>Yêu cầu chỉnh sửa</Button>
          <Button type="primary" loading={busy} onClick={()=>onApply(proposal)}>
            Duyệt & lưu website local</Button>
        </Space>
      </Card>
    </Space>
  </Drawer>;
}

