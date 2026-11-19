import {useState} from 'react';
import {App as AntApp, Alert, Button, Card, Input, Select, Space, Table, Tag, Typography} from 'antd';
import {api} from '../api.js';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';

const {Text}=Typography;

export function FilmProduction({mutate}){
  const {message,modal}=AntApp.useApp();
  const motionResource=useResource('/api/film/motion');
  const productionResource=useResource('/api/film/productions');
  const motion=motionResource.data;
  const motionBusy=motionResource.loading;
  const [motionFilename,setMotionFilename]=useState({});
  const productions=productionResource.data?.episodes||[];
  const productionBusy=productionResource.loading;
  const [voiceEngine,setVoiceEngine]=useState('windows');
  const [voiceName,setVoiceName]=useState('');
  const reloadMotion=motionResource.reload;
  const reloadProductions=productionResource.reload;
  useScreenRefresh(()=>Promise.all([reloadMotion(),reloadProductions()]));

  const filmProductionAction=(episode,action)=>{
    modal.confirm({
      title:action==='render'?'Kiểm tra và dựng MP4 local bằng FFmpeg?':'Tạo thoại offline bằng engine đã cài?',
      content:<Space direction="vertical" style={{width:'100%'}}>
        <Text strong>{episode.film_slug} / {episode.episode_id}</Text>
        <Text code>Episode SHA: {episode.episode_sha256}</Text>
        <Text>{episode.shot_count} clips · ~{episode.runtime_seconds} giây</Text>
        {action==='voice'&&<Text>Engine: {voiceEngine} · voice: {voiceName||'mặc định'}</Text>}
        <Alert showIcon type="warning"
          message="Thực thi local, cần quyền Owner và xem đầy đủ source manifest"
          description="Backend sẽ đọc lại SHA của từng clip gốc và chỉ chạy FFmpeg/TTS đã cài. Không gọi model hoặc GPU. Dựng kỹ thuật thành công KHÔNG chứng minh nhân vật đồng nhất hay phim đạt chất lượng."/>
      </Space>,okText:'Kiểm tra SHA và xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const detail=await api('/api/film/productions/'+episode.film_slug+'/'+episode.episode_id);
        if(detail.proposal.episode_sha256!==episode.episode_sha256)
          throw new Error('Episode SHA đã thay đổi; không thực thi');
        const result=await mutate('/api/film/productions/'+action,{
          ack:action==='render'?'ASSEMBLE_LOCAL_FILM':'SYNTHESIZE_LOCAL_VOICE',
          film_slug:episode.film_slug,episode_id:episode.episode_id,
          episode_sha:episode.episode_sha256,
          ...(action==='voice'?{engine:voiceEngine,voice_name:voiceName.trim()||null}:{}),
        });
        if(result){message.success(action==='render'?'Đã dựng MP4; Owner vẫn cần xem phim':'Tạo audio offline; chưa QA ngôn ngữ');await reloadProductions();}
      },
    });
  };
  const actionMotion=(job,action)=>{
    const filename=(motionFilename[job.job_id]||'').trim();
    if(action==='collect'&&(!filename.startsWith('af_motion_'+job.job_id+'_')
        || !filename.endsWith('.mp4'))){
      message.warning('Nhập tên MP4 đúng job trong thư mục ComfyUI output');
      return;
    }
    modal.confirm({
      title:action==='collect'?'Kiểm tra và nhập MP4 local?':'Kiểm tra lịch sử ComfyUI?',
      content:<Space direction="vertical">
        <Text>Shot: {job.film_slug} / {job.shot_id}</Text>
        <Text code>Plan SHA: {job.plan_sha}</Text>
        <Text code>Workflow SHA: {job.workflow_sha}</Text>
        {action==='collect'&&<Text code>File: {filename}</Text>}
        <Alert type="warning" showIcon message="Cần Owner xem video trước khi chấp nhận"
          description="Lệnh chỉ xác minh history hoặc chạy ffprobe/FFmpeg local; không gọi model, không xuất bản và không tự duyệt chất lượng."/>
      </Space>,okText:'Xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const inspected=await api('/api/film/motion/job/'+job.job_id);
        if(inspected.plan_sha!==job.plan_sha || inspected.workflow_sha!==job.workflow_sha)
          throw new Error('Motion job đã thay đổi; tải lại và kiểm tra SHA');
        const result=await mutate('/api/film/motion/'+(action==='collect'?'collect':'poll'),{
          ack:action==='collect'?'IMPORT_LOCAL_COMFY_MP4':'CHECK_LOCAL_COMFY_HISTORY',
          job_id:job.job_id,plan_sha:job.plan_sha,workflow_sha:job.workflow_sha,
          ...(action==='collect'?{filename}:{}),
        });
        if(result){message.success(action==='collect'?'MP4 đã kiểm tra kỹ thuật':'Đã đối chiếu lịch sử ComfyUI');await reloadMotion();}
      },
    });
  };

  return <>
    <Card title="Film Studio · Motion pilot 4 giây" extra={
      <Button onClick={reloadMotion} loading={motionBusy}>Làm mới GPU / Jobs</Button>}>
      <ResourceStatus resource={motionResource} label="motion jobs"/>
      <Alert type="warning" showIcon style={{marginBottom:12}}
        message="Wan 2.2 5B chạy bằng CLI do Owner kiểm soát"
        description="Model Hub video vẫn CONFIG_ONLY; phải tự cài ComfyUI/checkpoint và duyệt workflow SHA, không có auto-download/gọi GPU. QA kỹ thuật không phải duyệt chất lượng phim."/>
      <Space wrap style={{marginBottom:12}}>
        <Tag>{motion?.gpu?.status||'CHƯA KIỂM TRA GPU'}</Tag>
        <Text>Tổng VRAM: {motion?.gpu?.vram_gib??'—'} GiB</Text>
        <Text>VRAM rảnh (snapshot): {motion?.gpu?.vram_free_snapshot_gib??'—'} GiB</Text>
      </Space>
      <Table size="small" rowKey="job_id" dataSource={motion?.jobs||[]}
        loading={motionBusy} scroll={{x:980}}
        pagination={{pageSize:6,hideOnSinglePage:true}}
        columns={[
          {title:'Shot',width:180,render:(_,r)=><Space direction="vertical" size={0}>
            <Text strong>{r.film_slug} / {r.shot_id}</Text>
            <Text code>{r.job_id.slice(0,12)}</Text></Space>},
          {title:'State',dataIndex:'status',width:260,render:v=><Tag>{v}</Tag>},
          {title:'Decode MP4',dataIndex:'mp4_technical_verified',width:145,
            render:v=>v?<Tag color="green">PASS kỹ thuật</Tag>:<Tag>Chưa đạt</Tag>},
          {title:'History',width:125,render:(_,r)=>
            <Button size="small" onClick={()=>actionMotion(r,'poll')}>Đối chiếu</Button>},
          {title:'Import MP4',width:270,render:(_,r)=><Space direction="vertical" style={{width:'100%'}}>
            <Input size="small" value={motionFilename[r.job_id]||''}
              placeholder={'af_motion_'+r.job_id+'_00001.mp4'}
              onChange={e=>setMotionFilename(old=>({...old,[r.job_id]:e.target.value}))}/>
            <Button size="small" disabled={r.mp4_technical_verified||r.state!=='COMPLETE_UNVERIFIED'}
              onClick={()=>actionMotion(r,'collect')}>Xác minh & nhập file</Button>
          </Space>},
        ]}/>
      <Text type="secondary">Để nhập file trên Dashboard, đặt AGENTFORGE_COMFY_OUTPUT_DIR trước khi khởi động với --allow-external-tools. Muốn đo peak VRAM thật hãy theo dõi nvidia-smi và khai báo thủ công qua CLI. Chưa có benchmark GPU 12 GB thực.</Text>
    </Card>
    <Card title="Film Studio · Continuity & Dựng phim"
      extra={<Button loading={productionBusy} onClick={reloadProductions}>Làm mới Episodes</Button>}>
      <ResourceStatus resource={productionResource} label="episodes"/>
      <Alert type="warning" showIcon style={{marginBottom:14}}
        message="Chỉ ghép clip đã xác minh SHA và MP4 kỹ thuật"
        description="Tạo episode-plan bằng CLI từ receipt clip thật; mỗi cảnh cần ghi identity/reference/costume/location/action/camera/caption. Không tự render GPU. 3–5 shot xem continuity (~12–20s), 15–22 shot làm pilot 60–90s. Các kiểm tra metadata KHÔNG thay thế quan sát nhân vật bằng mắt."/>
      <Space wrap style={{marginBottom:14}}>
        <Text>Giọng đọc:</Text>
        <Select size="small" style={{minWidth:150}} value={voiceEngine}
          onChange={setVoiceEngine}
          options={[{label:'Windows SAPI local',value:'windows'},{label:'Piper offline',value:'piper'}]}/>
        <Input size="small" style={{minWidth:210}} placeholder="Tên voice hoặc file .onnx (tùy chọn)"
          value={voiceName} onChange={e=>setVoiceName(e.target.value)}/>
      </Space>
      <Table rowKey={r=>r.film_slug+':'+r.episode_id}
        dataSource={productions} loading={productionBusy}
        scroll={{x:960}} pagination={{pageSize:8,hideOnSinglePage:true}}
        columns={[
          {title:'Episode',width:190,render:(_,r)=><Space direction="vertical" size={0}>
            <Text strong>{r.film_slug} / {r.episode_id}</Text>
            {r.episode_sha256&&<Text code>{r.episode_sha256.slice(0,14)}</Text>}
          </Space>},
          {title:'Phạm vi',width:150,render:(_,r)=><Text>
            {r.shot_count??'—'} shot · {r.runtime_seconds??'—'} giây
          </Text>},
          {title:'Trạng thái',dataIndex:'state',width:295,render:v=><Tag>{v}</Tag>},
          {title:'Kiểm tra & dựng',width:300,render:(_,r)=><Space wrap>
            <Button size="small" disabled={!r.episode_sha256} onClick={async()=>{
              try{
                const detail=await api('/api/film/productions/'+r.film_slug+'/'+r.episode_id);
                modal.info({title:'Episode continuity & shot SHA',
                  width:720,content:<Space direction="vertical" style={{width:'100%'}}>
                    <Text code>{detail.proposal.episode_sha256}</Text>
                    <Text>Reference/costume/location là metadata Owner nhập, chưa được thị giác máy xác nhận.</Text>
                    <pre className="source-text">{JSON.stringify(detail.proposal.shots,null,2)}</pre>
                    {detail.render&&<Text>Render SHA: {detail.render.video_sha256}</Text>}
                  </Space>});
              }catch(e){message.error(e.message||'Không đọc được episode');}
            }}>Xem shot SHA</Button>
            <Button size="small" disabled={!r.episode_sha256||r.state!=='PREPARED_NOT_RENDERED'}
              onClick={()=>filmProductionAction(r,'voice')}>TTS local</Button>
            <Button size="small" type="primary"
              disabled={!r.episode_sha256||r.state!=='PREPARED_NOT_RENDERED'}
              onClick={()=>filmProductionAction(r,'render')}>Dựng FFmpeg</Button>
          </Space>},
        ]}/>
      <Text type="secondary">Bản dựng nằm trong workspace/films/&lt;film&gt;/productions/&lt;episode&gt;/episode.mp4 cùng captions.srt và render-receipt.json. Không tự publish hoặc đánh dấu QA hình ảnh PASS.</Text>
    </Card>
  </>;
}
