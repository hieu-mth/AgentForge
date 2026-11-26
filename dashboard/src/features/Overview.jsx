import {useState} from 'react';
import {Button,Card,Empty,Modal,Table} from 'antd';
import {CheckSquareOutlined,ClockCircleOutlined,PlayCircleOutlined,VideoCameraOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus,Stat} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';
import {StudioPreview} from './StudioPreview.jsx';
import {draftTitle} from './scriptPresentation.js';
import {productionUsage} from './productionUsage.js';

const prepared='PREPARED_NOT_RENDERED';
const needsReview='RENDER_RECEIPT_PRESENT_UNINSPECTED';
const episodeStates={
  [prepared]:{label:'Đã chuẩn bị · chờ dựng',tone:'info'},
  [needsReview]:{label:'Cần Owner xem bản dựng',tone:'warn'},
  INVALID_NEEDS_OWNER_REVIEW:{label:'Cần kiểm tra hồ sơ tập',tone:'bad'},
};

const columns=[
  {title:'Dự án',dataIndex:'film_slug',width:'30%',
    render:name=><span className="env-runtime-name env-break">{name}</span>},
  {title:'Tập phim',dataIndex:'episode_id',width:'25%',
    render:name=><span className="env-break">{name}</span>},
  {title:'Trạng thái',dataIndex:'state',render:state=>{
    const {label,tone}=episodeStates[state]??{label:'Chưa rõ',tone:'neutral'};
    return <SettingsStatus tone={tone} title={state}>{label}</SettingsStatus>;
  }},
];

export function Overview({onNavigate}){
  const resource=useResource('/api/video-studio/projects');
  const draftsResource=useResource('/api/film/drafts');
  const [preview,setPreview]=useState(null);
  useScreenRefresh(resource.reload);
  useScreenRefresh(draftsResource.reload);
  const episodes=resource.data?.projects?.filter(row=>row.source!=='studio_draft');
  const drafts=draftsResource.data?.drafts;
  const videos=drafts?.filter(row=>row.video_sha);
  const usage=drafts?productionUsage(drafts):null;
  const empty=episodes?.length===0&&videos?.length===0;
  const openStudio=()=>onNavigate('media-studio');
  const studioButton=<Button type="primary" icon={<PlayCircleOutlined/>} onClick={openStudio}>
    Mở Video Studio
  </Button>;

  return <div className="environment-page overview-page">
    <SettingsHeading title="Tổng quan Video Studio" eyebrow="SẢN XUẤT VIDEO"
      description="Theo dõi video đã dựng từ bản nháp và các tập phim trong workspace."
      actions={empty?null:studioButton}/>
    <ResourceStatus resource={draftsResource} label="video từ bản nháp"/>
    <ResourceStatus resource={resource} label="tập phim"/>
    {(videos||episodes)&&
      <div className="env-stat-grid overview-stats" aria-label="Tiến độ Video Studio">
        <Stat icon={<VideoCameraOutlined/>} label="Bản nháp đã dựng" value={videos?.length??'—'}/>
        <Stat icon={<ClockCircleOutlined/>} label="Đã chuẩn bị · chờ dựng"
          value={episodes?.filter(row=>row.state===prepared).length??'—'}/>
        <Stat icon={<CheckSquareOutlined/>} label="Bản dựng cần Owner xem"
          value={videos&&episodes? videos.filter(row=>row.status==='REVIEW').length+
            episodes.filter(row=>row.state===needsReview).length:'—'}/>
      </div>}
    {usage&&usage.count>0&&<Card className="env-panel" title="Số liệu vận hành Studio">
      <div className="env-stat-grid overview-stats">
        <Stat label="Production đã duyệt" value={usage.approved+'/'+usage.count}/>
        <Stat label="Lượt cloud đã giữ ngân sách" value={usage.cloudCalls}/>
        <Stat label="Giây video cloud đã giữ ngân sách" value={usage.cloudSeconds}/>
        <Stat label="Thời gian attempt gần nhất (trung vị)" value={usage.medianAttemptSeconds===null?'—':usage.medianAttemptSeconds+' giây'}/>
      </div>
      <p className="env-muted">Tối đa 30 bản nháp gần nhất. Lượt/giây đặt chỗ gồm cả lỗi; không phải hóa đơn. Thời gian chỉ tính attempt đã kết thúc, không phải tổng thời gian sản xuất.</p>
    </Card>}
    {empty&&<Card className="env-panel">
      <Empty description="Chưa có video đã dựng hoặc tập phim trong workspace">{studioButton}</Empty>
    </Card>}
    {videos?.length>0&&<Card className="env-panel" title="Video từ bản nháp">
      <Table className="overview-table env-table" size="middle" rowKey="id" dataSource={videos}
        pagination={{pageSize:6,hideOnSinglePage:true}} columns={[
          {title:'Video',render:(_,row)=><span className="env-break">
            {draftTitle(row)}
          </span>},
          {title:'Trạng thái',dataIndex:'status',render:status=><SettingsStatus
            tone={status==='APPROVED'?'good':status==='REVIEW'?'warn':'neutral'}>
            {{APPROVED:'Đã duyệt',REVIEW:'Chờ duyệt',REJECTED:'Đã từ chối'}[status]??'Đã dựng'}
          </SettingsStatus>},
          {title:'',render:(_,row)=><Button size="small" onClick={()=>setPreview(row)}>Xem MP4</Button>},
        ]}/>
    </Card>}
    {episodes?.length>0&&
      <Card className="env-panel" title={<SectionTitle icon={<VideoCameraOutlined/>}
        title="Dự án & tập phim"
        description="Trạng thái dựa trên hồ sơ Film Studio trong workspace"/>}
        extra={episodes.length>0&&<Button onClick={()=>onNavigate('projects')}>Xem dự án</Button>}>
        <Table className="overview-table env-table" columns={columns}
          size="middle" rowKey="project_id" dataSource={episodes}
          pagination={{pageSize:6,hideOnSinglePage:true}}/>
      </Card>}
    {preview&&<Modal open title={draftTitle(preview)} footer={null}
      onCancel={()=>setPreview(null)}>
      <StudioPreview url={'/api/film/drafts/'+preview.id+'/preview?v='+preview.video_sha}
        filename="draft.mp4" label="Xem MP4" initiallyOpen/>
    </Modal>}
  </div>;
}
