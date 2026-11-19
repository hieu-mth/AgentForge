import {useState} from 'react';
import {App as AntApp, Alert, Button, Card, Grid, Input, Select, Space, Table, Typography} from 'antd';
import {PlayCircleOutlined,ReloadOutlined,VideoCameraOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsStatus} from '../components/settings.jsx';
import {StudioPreview} from './StudioPreview.jsx';
import {api} from '../api.js';
import {useResource, ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';

const {Text}=Typography;
const desktopColumns=['md'];
const statusLabels={
  PREPARED_NOT_RENDERED:'Đã chuẩn bị · chờ dựng',
  RENDER_RECEIPT_PRESENT_UNINSPECTED:'Cần Owner xem bản dựng',
  INVALID_NEEDS_OWNER_REVIEW:'Cần kiểm tra hồ sơ tập',
  COMPLETE_UNVERIFIED:'Chờ xác minh MP4',
  INTEGRITY_REVIEW_REQUIRED:'Cần kiểm tra lại clip',
  SUBMITTED:'Đã gửi ComfyUI',
  SUBMITTING:'Đang gửi ComfyUI',
  SUBMITTING_UNCERTAIN:'Cần đối chiếu lượt gửi',
  RUNNING:'Đang chạy',
  FAILED:'Có lỗi',
};

export function ProductionStatus({state,verified}){
  const warning=['RENDER_RECEIPT_PRESENT_UNINSPECTED','COMPLETE_UNVERIFIED','SUBMITTING_UNCERTAIN'].includes(state);
  const error=state==='FAILED'||state?.includes('REVIEW_REQUIRED')||state==='INVALID_NEEDS_OWNER_REVIEW';
  return <SettingsStatus tone={verified?'good':error?'bad':warning?'warn':'info'} title={state}>
    {verified?'MP4 đã qua kiểm tra kỹ thuật':statusLabels[state]||'Xem chi tiết trạng thái'}
  </SettingsStatus>;
}

export function MotionClips({mutate}){
  const {message,modal}=AntApp.useApp();
  const {md:desktop}=Grid.useBreakpoint();
  const motionResource=useResource('/api/film/motion');
  const {data:motion,loading:motionBusy,reload:reloadMotion}=motionResource;
  const [motionFilename,setMotionFilename]=useState({});
  useScreenRefresh(reloadMotion);

  const actionMotion=(job,action)=>{
    const filename=(motionFilename[job.job_id]||'').trim();
    if(action==='collect'&&(!filename.startsWith('af_motion_'+job.job_id+'_')
        || !filename.endsWith('.mp4'))){
      message.warning('Nhập tên MP4 đúng mã tác vụ trong thư mục đầu ra của ComfyUI');
      return;
    }
    modal.confirm({
      title:action==='collect'?'Kiểm tra và nhập MP4 local?':'Kiểm tra lịch sử ComfyUI?',
      content:<Space direction="vertical">
        <Text>Cảnh: {job.film_slug} / {job.shot_id}</Text>
        <Text code>SHA kế hoạch: {job.plan_sha}</Text>
        <Text code>SHA quy trình: {job.workflow_sha}</Text>
        {action==='collect'&&<Text code>Tệp: {filename}</Text>}
        <Alert type="warning" showIcon message="Cần Owner xem video trước khi chấp nhận"
          description="Lệnh kiểm tra lịch sử ComfyUI hoặc xác minh MP4 bằng ffprobe và FFmpeg trên máy."/>
      </Space>,okText:'Xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const inspected=await api('/api/film/motion/job/'+job.job_id);
        if(inspected.plan_sha!==job.plan_sha || inspected.workflow_sha!==job.workflow_sha)
          throw new Error('Tác vụ chuyển động đã thay đổi. Hãy tải lại rồi kiểm tra SHA.');
        const result=await mutate('/api/film/motion/'+(action==='collect'?'collect':'poll'),{
          ack:action==='collect'?'IMPORT_LOCAL_COMFY_MP4':'CHECK_LOCAL_COMFY_HISTORY',
          job_id:job.job_id,plan_sha:job.plan_sha,workflow_sha:job.workflow_sha,
          ...(action==='collect'?{filename}:{}),
        });
        if(result){message.success(action==='collect'?'MP4 đã kiểm tra kỹ thuật':'Đã đối chiếu lịch sử ComfyUI');await reloadMotion();}
      },
    });
  };

  const clipActions=row=><div className="studio-row-actions">
    <Button size="small" onClick={()=>actionMotion(row,'poll')}>Đối chiếu ComfyUI</Button>
    {row.mp4_technical_verified&&<Button size="small" onClick={()=>modal.info({
      title:'Clip '+row.shot_id, width:640, okText:'Đóng',
      content:<StudioPreview url={'/api/film/motion/job/'+encodeURIComponent(row.job_id)+'/preview'}
        filename={row.shot_id+'.mp4'} label="Phát clip"/>,
    })}>Xem clip</Button>}
    {!row.mp4_technical_verified&&row.state==='COMPLETE_UNVERIFIED'&&<>
      <Input size="small" aria-label={'Tên MP4 của cảnh '+row.shot_id}
        value={motionFilename[row.job_id]||''} placeholder="Tên file MP4 trong thư mục output"
        onChange={e=>setMotionFilename(old=>({...old,[row.job_id]:e.target.value}))}/>
      <Button size="small" onClick={()=>actionMotion(row,'collect')}>Xác minh & nhập MP4</Button>
    </>}
  </div>;

  return <Card className="env-panel" title={<SectionTitle icon={<PlayCircleOutlined/>}
    title="Danh sách clip chuyển động" description="Kiểm tra tác vụ đã gửi và xác minh MP4 local"/>}
    extra={<Button icon={<ReloadOutlined/>} onClick={reloadMotion} loading={motionBusy}>Làm mới</Button>}>
      <ResourceStatus resource={motionResource} label="clip chuyển động"/>
      {motion?.gpu&&<details className="studio-details">
        <summary>Thông tin GPU của lần kiểm tra</summary>
        <div>Tình trạng: {motion.gpu.status??'Chưa xác định'}</div>
        <div>Tổng VRAM: {motion.gpu.vram_gib??'—'} GiB · VRAM rảnh: {motion.gpu.vram_free_snapshot_gib??'—'} GiB</div>
      </details>}
      <Table className="hub-table studio-table" size="small" rowKey="job_id" dataSource={motion?.jobs||[]}
        loading={motionBusy} scroll={desktop?{x:620}:undefined}
        locale={{emptyText:motionResource.error?'Không tải được danh sách clip.':
          'Chưa có clip. Chuẩn bị checkpoint và gửi tác vụ bằng CLI để bắt đầu.'}}
        pagination={{pageSize:6,hideOnSinglePage:true}}
        columns={[
          {title:'Cảnh',width:'32%',render:(_,row)=><>
            <span className="env-runtime-name env-break">{row.film_slug} / {row.shot_id}</span>
            <details className="studio-details"><summary>Chi tiết</summary>
              <div>Tác vụ: {row.job_id}</div><div>Trạng thái: {row.status||row.state}</div>
              <div>SHA kế hoạch: {row.plan_sha}</div><div>SHA workflow: {row.workflow_sha}</div>
            </details>
            {!desktop&&clipActions(row)}
          </>},
          {title:'Trạng thái',render:(_,row)=><ProductionStatus
            state={row.status||row.state} verified={row.mp4_technical_verified}/>},
          {title:'Thao tác',width:'38%',responsive:desktopColumns,render:(_,row)=>clipActions(row)},
        ]}/>
      <details className="studio-details studio-panel-note"><summary>Điều kiện nhập MP4</summary>
        <div>Đặt <code>AGENTFORGE_COMFY_OUTPUT_DIR</code> và khởi động với <code>--allow-external-tools</code>.
          Tên file cần bắt đầu bằng <code>af_motion_&lt;mã tác vụ&gt;_</code> và có đuôi <code>.mp4</code>.</div>
      </details>
    </Card>;
}

export function FilmProduction({mutate,resource:productionResource,onInspect}){
  const {message,modal}=AntApp.useApp();
  const {md:desktop}=Grid.useBreakpoint();
  const {data,loading:productionBusy,reload:reloadProductions}=productionResource;
  const productions=data?.episodes||[];
  const [voiceEngine,setVoiceEngine]=useState('windows');
  const [voiceName,setVoiceName]=useState('');

  const filmProductionAction=(episode,action)=>{
    modal.confirm({
      title:action==='render'?'Kiểm tra và dựng MP4 local bằng FFmpeg?':'Tạo thoại offline bằng engine đã cài?',
      content:<Space direction="vertical" style={{width:'100%'}}>
        <Text strong>{episode.film_slug} / {episode.episode_id}</Text>
        <Text code>SHA tập phim: {episode.episode_sha256}</Text>
        <Text>{episode.shot_count} clip · khoảng {episode.runtime_seconds} giây</Text>
        {action==='voice'&&<Text>Công cụ: {voiceEngine} · Giọng đọc: {voiceName||'mặc định'}</Text>}
        <Alert showIcon type="warning"
          message="Cần Owner xác nhận trước khi thực thi"
          description="AgentForge kiểm tra lại SHA của từng clip gốc rồi dùng FFmpeg hoặc công cụ giọng đọc đã cài. Owner cần xem bản dựng để đánh giá chất lượng."/>
      </Space>,okText:'Kiểm tra SHA và xác nhận',cancelText:'Hủy',
      onOk:async()=>{
        const detail=await api('/api/film/productions/'+episode.film_slug+'/'+episode.episode_id);
        if(detail.proposal.episode_sha256!==episode.episode_sha256)
          throw new Error('SHA tập phim đã thay đổi. Hãy tải lại hồ sơ rồi thử lại.');
        const result=await mutate('/api/film/productions/'+action,{
          ack:action==='render'?'ASSEMBLE_LOCAL_FILM':'SYNTHESIZE_LOCAL_VOICE',
          film_slug:episode.film_slug,episode_id:episode.episode_id,
          episode_sha:episode.episode_sha256,
          ...(action==='voice'?{engine:voiceEngine,voice_name:voiceName.trim()||null}:{}),
        });
        if(result){message.success(action==='render'?'Đã dựng MP4. Owner cần xem lại bản phim.':'Đã tạo lời thoại. Owner cần nghe lại để kiểm tra.');await reloadProductions();}
      },
    });
  };
  const episodeActions=row=>row.episode_sha256&&<div className="studio-row-actions">
    <Button size="small" onClick={()=>onInspect(row)}>Xem hồ sơ cảnh</Button>
    {row.state==='PREPARED_NOT_RENDERED'&&<>
      <Button size="small" onClick={()=>filmProductionAction(row,'voice')}>Tạo thoại</Button>
      <Button size="small" type="primary" onClick={()=>filmProductionAction(row,'render')}>Dựng MP4</Button>
    </>}
  </div>;

  return <Card className="env-panel" title={<SectionTitle icon={<VideoCameraOutlined/>}
    title="Tập phim & bản dựng" description="Kiểm tra hồ sơ cảnh, tạo thoại và dựng MP4 local"/>}
    extra={<Button icon={<ReloadOutlined/>} loading={productionBusy} onClick={reloadProductions}>Làm mới</Button>}>
      <ResourceStatus resource={productionResource} label="tập phim"/>
      {productions.length>0&&<Space wrap className="studio-voice">
        <Text>Giọng đọc</Text>
        <Select aria-label="Công cụ giọng đọc" size="small" style={{minWidth:150}} value={voiceEngine}
          onChange={setVoiceEngine}
          options={[{label:'Windows SAPI local',value:'windows'},{label:'Piper offline',value:'piper'}]}/>
        <Input aria-label="Tên giọng đọc" size="small" placeholder="Tên giọng hoặc file .onnx (tùy chọn)"
          value={voiceName} onChange={e=>setVoiceName(e.target.value)}/>
      </Space>}
      <Table className="hub-table studio-table" size="small" rowKey={r=>r.film_slug+':'+r.episode_id}
        dataSource={productions} loading={productionBusy}
        scroll={desktop?{x:640}:undefined} pagination={{pageSize:8,hideOnSinglePage:true}}
        locale={{emptyText:productionResource.error?'Không tải được danh sách tập phim.':
          'Chưa có tập phim. Chuẩn bị hồ sơ tập từ các clip đã xác minh bằng CLI.'}}
        columns={[
          {title:'Tập phim',width:'32%',render:(_,row)=><>
            <span className="env-runtime-name env-break">{row.film_slug} / {row.episode_id}</span>
            <details className="studio-details"><summary>Chi tiết</summary>
              <div>{row.shot_count??'—'} cảnh · {row.runtime_seconds??'—'} giây</div>
              <div>Trạng thái: {row.state}</div>
              {row.episode_sha256&&<div>SHA tập phim: {row.episode_sha256}</div>}
            </details>
            {!desktop&&episodeActions(row)}
          </>},
          {title:'Trạng thái',dataIndex:'state',render:state=><ProductionStatus state={state}/>},
          {title:'Kiểm tra & dựng',width:'38%',responsive:desktopColumns,render:(_,row)=>episodeActions(row)},
        ]}/>
      <details className="studio-details studio-panel-note"><summary>Điều kiện dựng và vị trí file</summary>
        <div>Chỉ ghép clip đã xác minh SHA và MP4. Sau khi dựng, Owner cần xem bản phim để kiểm tra chất lượng.</div>
        <div>Bản dựng nằm trong <code>workspace/films/&lt;film&gt;/productions/&lt;episode&gt;/episode.mp4</code>.</div>
      </details>
    </Card>;
}
