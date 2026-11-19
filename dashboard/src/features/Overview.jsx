import {Button,Card,Empty,Table} from 'antd';
import {CheckSquareOutlined,ClockCircleOutlined,PlayCircleOutlined,VideoCameraOutlined} from '@ant-design/icons';
import {SectionTitle,SettingsHeading,SettingsStatus,Stat} from '../components/settings.jsx';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {useScreenRefresh} from '../refresh_scope.jsx';

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
  useScreenRefresh(resource.reload);
  const episodes=resource.data?.projects;
  const openStudio=()=>onNavigate('media-studio');
  const studioButton=<Button type="primary" icon={<PlayCircleOutlined/>} onClick={openStudio}>
    Mở Video Studio
  </Button>;

  return <div className="environment-page overview-page">
    <SettingsHeading title="Tổng quan Video Studio" eyebrow="SẢN XUẤT VIDEO"
      description="Xem các tập phim trong workspace và xác định việc cần làm tiếp theo."
      actions={episodes?.length===0?null:studioButton}/>
    <ResourceStatus resource={resource} label="tập phim"/>
    {episodes&&<>
      <div className="env-stat-grid overview-stats" aria-label="Tiến độ trong danh sách tập phim hiện tại">
        <Stat icon={<VideoCameraOutlined/>} label="Tập phim được tìm thấy" value={episodes.length}
          sub="Trong danh sách hiện tại"/>
        <Stat icon={<ClockCircleOutlined/>} label="Đã chuẩn bị · chờ dựng"
          value={episodes.filter(row=>row.state===prepared).length}/>
        <Stat icon={<CheckSquareOutlined/>} label="Bản dựng cần Owner xem"
          value={episodes.filter(row=>row.state===needsReview).length}/>
      </div>
      <Card className="env-panel" title={<SectionTitle icon={<VideoCameraOutlined/>}
        title="Dự án & tập phim"
        description="Trạng thái dựa trên hồ sơ Film Studio trong workspace"/>}
        extra={episodes.length>0&&<Button onClick={()=>onNavigate('projects')}>Xem dự án</Button>}>
        {episodes.length>0?<Table className="overview-table env-table" columns={columns}
          size="middle" rowKey="project_id" dataSource={episodes}
          pagination={{pageSize:6,hideOnSinglePage:true}}/>:
          <Empty description="Chưa tìm thấy tập phim trong workspace">
            {studioButton}
          </Empty>}
      </Card>
    </>}
  </div>;
}
