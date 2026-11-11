import { useCallback, useEffect, useState } from 'react';
import { Alert, App as AntApp, Button, Card, Checkbox, Descriptions, Form,
  Input, InputNumber, Select, Space, Table, Tag, Typography } from 'antd';
import { api } from '../api.js';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {useReadSequence} from '../use_resource.jsx';

const { Text, Paragraph } = Typography;
const CLAIMS = [
  {label:'Private (Owner tự xác nhận)',value:'private'},
  {label:'Unlisted (Owner tự xác nhận)',value:'unlisted'},
  {label:'Public (Owner tự đăng trên YouTube Studio)',value:'public'},
  {label:'Scheduled (Owner tự đặt trong YouTube Studio)',value:'scheduled'},
];

export function Publishing({mutate,data}) {
  const {modal,message}=AntApp.useApp();
  const [episodes,setEpisodes]=useState([]);
  const [report,setReport]=useState(null);
  const [release,setRelease]=useState(null);
  const [handoff,setHandoff]=useState(null);
  const [selected,setSelected]=useState(null);
  const [busy,setBusy]=useState(false);
  const [prepareForm]=Form.useForm();
  const [attestForm]=Form.useForm();
  const [metricsForm]=Form.useForm();

  const beginRead=useReadSequence();
  const reload=useCallback(async()=>{
    const current=beginRead();
    setBusy(true);
    try{
      const [r,e]=await Promise.all([api('/api/publishing'),api('/api/film/productions')]);
      if(current()){setReport(r);setEpisodes(e.episodes||[]);}
    }catch(err){if(current())message.error(err.message||'Không đọc được sổ phát hành local');}
    finally{if(current())setBusy(false);}
  },[message,beginRead]);
  useEffect(()=>{reload();},[reload]);
  useScreenRefresh(reload);

  const inspectEpisode=async value=>{
    setSelected(null);
    if(!value)return;
    try{
      const [film,episode]=value.split(':');
      const detail=await api('/api/film/productions/'+film+'/'+episode);
      if(!detail.render){
        message.warning('Phim chưa có render-receipt SHA hợp lệ. Hoàn tất Đợt 9 trước.');
      } else{
        setSelected({...detail,film_slug:film,episode_id:episode});
      }
    }catch(err){message.error(err.message||'Phim chưa đạt QA kỹ thuật');}
  };

  const prepare=values=>{
    if(!selected?.render)return message.warning('Chọn phim đã render và inspect SHA trước');
    modal.confirm({
      title:'Chuẩn bị hồ sơ upload private?',
      content:<Space direction="vertical">
        <Paragraph>Đây chỉ là hồ sơ offline, không gửi lên YouTube và không lập lịch public.</Paragraph>
        <Text>Film: {selected.film_slug} / {selected.episode_id}</Text>
        <Text code>Episode: {selected.proposal.episode_sha256}</Text>
        <Text code>Render: {selected.render.receipt_sha256}</Text>
        <Alert type="warning" showIcon message="Owner phải tự xem phim, xác nhận bản quyền, nội dung tổng hợp và phân loại trẻ em."/>
      </Space>,
      okText:'Xác nhận lưu local',cancelText:'Hủy',
      onOk:async()=>{
        const result=await mutate('/api/publishing/prepare',{
          ack:'PREPARE_PRIVATE_RELEASE',film_slug:selected.film_slug,
          episode_id:selected.episode_id,
          episode_sha:selected.proposal.episode_sha256,
          render_sha:selected.render.receipt_sha256,
          metadata:{title:values.title,description:values.description||'',
            rights_attested:!!values.rights_attested,
            owner_watched:!!values.owner_watched,
            made_for_kids:!!values.made_for_kids,
            synthetic_media:!!values.synthetic_media,
            planned_utc:values.planned_utc?.trim()||null,
            campaign:values.campaign||null},
        });
        if(result){message.success('Đã tạo handoff local; chưa upload');prepareForm.resetFields();setSelected(null);reload();}
      },
    });
  };

  const inspect=async row=>{
    try{
      const detail=await api('/api/publishing/'+row.release_id);
      setRelease(detail);setHandoff(null);
      attestForm.resetFields();metricsForm.resetFields();
    }catch(err){message.error(err.message||'Release không hợp lệ hoặc file SHA thay đổi');}
  };

  const showHandoff=async()=>{
    try{setHandoff(await api('/api/publishing/'+release.release_id+'/handoff'));}
    catch(err){message.error(err.message||'Không mở được handoff');}
  };

  const attest=v=>{
    if(!release)return;
    modal.confirm({
      title:'Xác nhận thao tác do Owner đã thực hiện trên YouTube?',
      content:<Space direction="vertical">
        <Text>Video ID: {v.video_id} · {v.privacy}</Text>
        <Text code>Release SHA: {release.release_sha256}</Text>
        <Alert type="warning" showIcon message="AgentForge không xác minh nội dung/visibility bằng YouTube API trong bước này"
          description="Chỉ nhấn xác nhận nếu bạn đã tự kiểm tra trong YouTube Studio. Không có API public hay schedule tự động."/>
      </Space>,okText:'Tôi đã kiểm tra',cancelText:'Hủy',
      onOk:async()=>{
        const out=await mutate('/api/publishing/'+release.release_id+'/attest',{
          ack:'ATTEST_YOUTUBE_STUDIO_STATE',release_sha:release.release_sha256,
          video_id:v.video_id,privacy:v.privacy,owner_changed_on_youtube:true,
        });
        if(out){message.success('Đã ghi nhận lời xác nhận Owner, chưa phải API verification');await reload();await inspect(out);}
      },
    });
  };

  const observe=v=>{
    if(!release)return;
    modal.confirm({
      title:'Ghi thống kê do Owner quan sát?',
      content:'Số liệu được khai báo thủ công, không lấy trực tiếp từ YouTube API hoặc chứng minh doanh thu.',
      okText:'Ghi bản ghi local',cancelText:'Hủy',
      onOk:async()=>{
        const out=await mutate('/api/publishing/'+release.release_id+'/observe',{
          ack:'RECORD_OWNER_YOUTUBE_METRICS',release_sha:release.release_sha256,
          owner_observed:true,snapshot:{date:v.date,
            views:v.views,likes:v.likes,comments:v.comments,
            watch_minutes:v.watch_minutes},
        });
        if(out){message.success('Đã ghi metrics owner-reported');await reload();metricsForm.resetFields();}
      },
    });
  };

  return <Space orientation="vertical" size={18} style={{width:'100%'}}>
    <Alert type="warning" showIcon
      message="Wave 10 — không tự public, không tự chi tiền"
      description="Release metadata và lịch dự kiến chỉ lưu trên máy. YouTube private API upload là CLI opt-in với OAuth Desktop riêng; status/metrics trong Dashboard chủ yếu do Owner khai báo. Growth ledger quản lý VND, không có bank reconciliation hay doanh thu YouTube được xác minh."/>
    <Card title="Sổ phát hành Film Studio" loading={busy}
      extra={<Button onClick={reload}>Làm mới</Button>}>
      <Table rowKey="release_id" dataSource={report?.releases||[]}
        scroll={{x:960}} pagination={{pageSize:7}}
        columns={[
          {title:'Tập phim',width:210,render:(_,r)=><Space direction="vertical" size={0}>
            <Text strong>{r.film_slug} / {r.episode_id}</Text>
            <Text code>{r.release_id?.slice(0,12)}</Text>
          </Space>},
          {title:'Tên',dataIndex:'title',width:180,render:x=>x||'SHA chưa hợp lệ'},
          {title:'Trạng thái',dataIndex:'status',width:260,render:x=><Tag>{x}</Tag>},
          {title:'Lịch dự kiến (local)',dataIndex:'planned_utc',width:190,render:x=>x||'Chưa đặt'},
          {title:'Thống kê Owner',dataIndex:'latest_observation',width:170,
            render:x=>x?<Text>{x.views} views, {x.likes} likes</Text>:'Không có'},
          {title:'Xem release',width:140,
            render:(_,r)=><Button size="small" onClick={()=>inspect(r)}>Inspect SHA</Button>},
        ]}/>
    </Card>
    <Card title="Chuẩn bị hồ sơ upload từ phim đã qua FFmpeg QA">
      <Form form={prepareForm} layout="vertical" onFinish={prepare}
        initialValues={{rights_attested:false,owner_watched:false,
          synthetic_media:true,made_for_kids:false}}>
        <Form.Item label="Chọn phim đã assemble" name="episode" rules={[{required:true}]}>
          <Select showSearch placeholder="Chọn phim → kiểm tra SHA"
            options={episodes.filter(x=>x.render_receipt_present_uninspected)
              .map(x=>({label:x.film_slug+' / '+x.episode_id,
                value:x.film_slug+':'+x.episode_id}))}
            onChange={inspectEpisode}/>
        </Form.Item>
        {selected?.render&&<Alert type="info" showIcon style={{marginBottom:12}}
          message={'Nguồn hợp lệ: '+selected.film_slug+' / '+selected.episode_id}
          description={'MP4 SHA: '+selected.render.video_sha256}/>}
        <Form.Item label="YouTube title" name="title" rules={[{required:true,max:100,min:1}]}>
          <Input placeholder="Tên phim gốc của bạn"/>
        </Form.Item>
        <Form.Item label="Description" name="description">
          <Input.TextArea rows={3} maxLength={4500} showCount/>
        </Form.Item>
        <Form.Item label="Lịch dự kiến (ISO8601 với múi giờ, chỉ ghi chú local)" name="planned_utc">
          <Input placeholder="2026-12-10T19:00:00+07:00 (không tự đăng)"/>
        </Form.Item>
        <Form.Item label="Campaign Growth thật (không bắt buộc)" name="campaign">
          <Select allowClear options={(data?.growth||[]).filter(x=>!x.synthetic)
            .map(x=>({label:x.title,value:x.campaign}))}/>
        </Form.Item>
        <Form.Item name="owner_watched" valuePropName="checked">
          <Checkbox>Tôi đã xem MP4 và phụ đề trên máy</Checkbox>
        </Form.Item>
        <Form.Item name="rights_attested" valuePropName="checked">
          <Checkbox>Tôi xác nhận có quyền dùng toàn bộ hình, nhạc và giọng đọc</Checkbox>
        </Form.Item>
        <Form.Item name="synthetic_media" valuePropName="checked">
          <Checkbox>Khai báo nội dung tổng hợp / synthetic media</Checkbox>
        </Form.Item>
        <Form.Item name="made_for_kids" valuePropName="checked">
          <Checkbox>Nội dung dành cho trẻ em theo phân loại YouTube</Checkbox>
        </Form.Item>
        <Button type="primary" htmlType="submit" disabled={!selected?.render}>
          Chuẩn bị handoff local (Private)
        </Button>
      </Form>
    </Card>
    {release&&<Card title={'Release SHA · '+release.release_id}>
      <Descriptions bordered size="small" column={1} items={[
        {key:'status',label:'State',children:<Text strong>{release.status}</Text>},
        {key:'sha',label:'Release SHA',children:<Text copyable code>{release.release_sha256}</Text>},
        {key:'source',label:'Film video SHA',children:<Text copyable code>{release.video_sha256}</Text>},
        {key:'upload',label:'YouTube Video ID',children:release.youtube_video_id||'Chưa ghi nhận'},
        {key:'verified',label:'Platform verified',children:'Không — chỉ xác nhận Owner/API private response'},
      ]}/>
      <Space direction="vertical" style={{width:'100%',marginTop:14}}>
        <Button onClick={showHandoff}>Xem đường dẫn file & metadata cho YouTube Studio</Button>
        {handoff&&<Card size="small">
          <Paragraph>Video MP4: <Text code copyable>{handoff.video_file}</Text></Paragraph>
          <Paragraph>SRT: <Text code copyable>{handoff.srt_file}</Text></Paragraph>
          <Paragraph type="secondary">Chỉ upload từ YouTube Studio thủ công hoặc CLI private-only đã cấp OAuth. Không được gọi là public khi chưa kiểm tra trên platform.</Paragraph>
        </Card>}
        <Card size="small" title="Ghi nhận trạng thái đã thay đổi thủ công trên YouTube Studio">
          <Form form={attestForm} layout="vertical" onFinish={attest}>
            <Form.Item name="video_id" label="YouTube video ID (11 ký tự)"
              rules={[{required:true,pattern:/^[A-Za-z0-9_-]{11}$/}]}>
              <Input maxLength={11}/>
            </Form.Item>
            <Form.Item name="privacy" label="Trạng thái Owner tự kiểm tra" rules={[{required:true}]}>
              <Select options={CLAIMS}/>
            </Form.Item>
            <Button htmlType="submit">Ghi nhận xác nhận Owner (không gọi API)</Button>
          </Form>
        </Card>
        <Card size="small" title="Nhật ký thống kê do Owner nhập">
          <Form form={metricsForm} layout="vertical" onFinish={observe}>
            <Form.Item name="date" label="Ngày ghi số liệu UTC" rules={[
              {required:true,pattern:/^\d{4}-\d{2}-\d{2}$/}]}>
              <Input placeholder="2026-11-10"/>
            </Form.Item>
            {['views','likes','comments','watch_minutes'].map(k=>
              <Form.Item key={k} name={k} label={k} initialValue={0}
                rules={[{required:true,type:'number',min:0}]}>
                <InputNumber min={0} precision={0} style={{width:'100%'}}/>
              </Form.Item>)}
            <Button htmlType="submit" disabled={!release.youtube_video_id}>
              Ghi metrics owner-reported
            </Button>
          </Form>
        </Card>
      </Space>
    </Card>}
  </Space>;
}
