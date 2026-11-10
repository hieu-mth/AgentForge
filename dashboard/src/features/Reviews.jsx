import { useEffect, useState } from 'react';
import { App as AntApp, Alert, Button, Card, Checkbox, Descriptions, Drawer, Empty,
  Space, Table, Tag, Typography } from 'antd';
import { api } from '../api.js';
import { badge, clip } from '../components/shared.jsx';
const { Paragraph, Text, Title } = Typography;

export function Reviews({data, mutate, onReload}) {
  const {message,modal}=AntApp.useApp();
  const [draft,setDraft]=useState(null);
  const [video,setVideo]=useState(null);
  const [watched,setWatched]=useState(false);
  const drafts=data?.autopilot_reviews?.items||[];
  const videos=data?.local_video?.items||[];
  useEffect(()=>setWatched(false),[video?.production_id]);
  const inspectDraft=async job=>{
    try{setDraft(await api('/api/drafts/'+job.job_id));}
    catch(e){message.error(e.message);}
  };
  const inspectVideo=async record=>{
    try{setVideo(await api('/api/videos/'+record.production_id));}
    catch(e){message.error(e.message);}
  };
  const decideDraft=decision=>{
    if(!draft)return;
    modal.confirm({title:decision==='APPROVE'?'Duyệt bản nháp AI?':'Từ chối bản nháp?',
      content:<div><Paragraph>Quyết định dựa trên nội dung đã xem và SHA:</Paragraph>
        <Text code>{draft.output_sha}</Text><Paragraph>Không tự đăng hoặc phát hành.</Paragraph></div>,
      okText:decision==='APPROVE'?'Duyệt':'Từ chối',okButtonProps:{danger:decision==='REJECT'},
      onOk:async()=>{
        const out=await mutate('/api/drafts/'+draft.job_id+'/decide',{
          ack:'REVIEW_'+decision,decision,output_sha:draft.output_sha});
        if(out){message.success('Đã ghi quyết định');setDraft(null);onReload();}
      }});
  };
  const decideVideo=decision=>{
    if(!video||!watched){message.warning('Hãy phát và tự kiểm tra video rồi xác nhận trước.');return;}
    modal.confirm({title:'Quyết định video local?',
      content:<div><Paragraph>Owner xác nhận đã xem video MP4 từ nguồn local có SHA sau:</Paragraph>
        <Text code>{video.video_sha}</Text><Paragraph>Không tự đăng lên mạng.</Paragraph></div>,
      okText:decision==='APPROVE'?'Duyệt video':'Từ chối',okButtonProps:{danger:decision==='REJECT'},
      onOk:async()=>{
        const out=await mutate('/api/videos/'+video.production_id+'/decide',{
          ack:'VIDEO_'+decision,decision,video_sha:video.video_sha,watched_local_file:true});
        if(out){message.success('Đã ghi quyết định video');setVideo(null);onReload();}
      }});
  };
  return <Space orientation="vertical" size={18} style={{width:'100%'}}>
    <Alert showIcon type="info" message="Owner Review Queue"
      description="Phê duyệt chỉ ghi lại quyết định, không đăng bài, phát hành video hoặc quảng cáo."/>
    <Card title={'AI Drafts ('+(data?.autopilot_reviews?.pending_count||0)+' chờ xử lý)'}>
      <Table rowKey="job_id" dataSource={drafts} pagination={{pageSize:8}}
        columns={[
          {title:'Job',render:(_,r)=><code>{clip(r.job_id)}</code>},
          {title:'Skill',dataIndex:'skill_id'},
          {title:'Quality',dataIndex:'quality',render:badge},
          {title:'Quyết định',dataIndex:'decision',render:badge},
          {title:'Xem',render:(_,r)=><Button onClick={()=>inspectDraft(r)}>Xem nội dung</Button>},
        ]}/>
    </Card>
    <Card title={'Video local ('+(data?.local_video?.pending_count||0)+' cần owner)'}>
      <Table rowKey="production_id" dataSource={videos} pagination={{pageSize:8}}
        columns={[
          {title:'Production',render:(_,r)=><code>{clip(r.production_id)}</code>},
          {title:'Status',dataIndex:'status',render:badge},
          {title:'QA',dataIndex:'quality',render:badge},
          {title:'Xem',render:(_,r)=><Button onClick={()=>inspectVideo(r)}
            disabled={!['VIDEO_READY','APPROVED','REJECTED'].includes(r.status)}>Xem video</Button>},
        ]}/>
    </Card>
    <Drawer title="Review storyboard AI" open={!!draft} onClose={()=>setDraft(null)}
      size="min(720px, 96vw)" destroyOnHidden>
      {draft&&<Space orientation="vertical" size="middle" style={{width:'100%'}}>
        <Alert type="warning" message="PASS_HEURISTIC không phải xác minh fact"
          description="Đọc toàn bộ nội dung và tự kiểm tra claim, sản phẩm, giá và chính sách trước khi duyệt."/>
        <Text>SHA: <Text code>{draft.output_sha}</Text></Text>
        <Title level={4}>{draft.storyboard?.title||'Storyboard draft'}</Title>
        {(draft.storyboard?.scenes||[]).map((sc,i)=><Card key={i} size="small"
          title={(i+1)+'. '+(sc.headline||'Cảnh')}>
          <Paragraph>{sc.caption}</Paragraph>
          <Text type="secondary">{sc.duration_seconds||0} giây</Text>
        </Card>)}
        <Space>
          <Button danger onClick={()=>decideDraft('REJECT')}>Từ chối</Button>
          <Button type="primary" onClick={()=>decideDraft('APPROVE')}>Duyệt draft</Button>
        </Space>
      </Space>}
    </Drawer>
    <Drawer title="Review MP4 local" open={!!video} onClose={()=>setVideo(null)}
      size="min(680px, 96vw)" destroyOnHidden>
      {video&&<Space orientation="vertical" size="middle" style={{width:'100%'}}>
        <Alert type="info" message="Phát video trực tiếp từ AgentForge local"
          description="Dữ liệu MP4 được phát qua backend đã đăng nhập, không upload lên cloud. Hãy xem hình ảnh và nghe âm thanh trước khi nghiệm thu."/>
        <video key={video.production_id} controls playsInline preload="metadata"
          src={video.stream_url}
          style={{width:'100%',maxHeight:460,background:'#10131b',borderRadius:10}}
          aria-label="Phát video sản phẩm local">
          Trình duyệt không hỗ trợ phát MP4 này.
        </video>
        <Descriptions bordered column={1} items={[
          {key:'1',label:'File trên máy',children:<Text code>{video.relative_path}</Text>},
          {key:'2',label:'QA',children:badge(video.quality)},
          {key:'3',label:'SHA-256',children:<Text code>{video.video_sha}</Text>},
        ]}/>
        <Checkbox checked={watched} onChange={e=>setWatched(e.target.checked)}>
          Tôi đã xem video và nghe âm thanh, đối chiếu nội dung với yêu cầu trước khi duyệt.
        </Checkbox>
        <Space><Button danger disabled={!watched||video.status==='APPROVED'||video.status==='REJECTED'}
          onClick={()=>decideVideo('REJECT')}>Từ chối</Button>
          <Button type="primary" disabled={!watched||video.status==='APPROVED'||video.status==='REJECTED'}
            onClick={()=>decideVideo('APPROVE')}>Duyệt video local</Button></Space>
      </Space>}
    </Drawer>
  </Space>;
}
