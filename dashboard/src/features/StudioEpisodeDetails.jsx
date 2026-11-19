import {Button,Drawer,Typography} from 'antd';
import {useResource,ResourceStatus} from '../use_resource.jsx';
import {ProductionStatus} from './FilmProduction.jsx';

const {Text}=Typography;

export function StudioEpisodeDetails({episode,onClose,onAssembly}){
  const {film_slug:film,episode_id:id,state}=episode;
  const resource=useResource('/api/film/productions/'+encodeURIComponent(film)+'/'+encodeURIComponent(id));
  const {proposal,render}=resource.data??{};
  const shots=proposal?.shots??[];

  return <Drawer open width="min(640px, 100vw)" className="studio-episode-drawer" onClose={onClose}
    title={<><span className="studio-episode-project">{film}</span><div>{id}</div></>}>
    <div className="studio-drawer-content">
      <ProductionStatus state={state}/>
      <ResourceStatus resource={resource} label="hồ sơ tập phim"/>
      {proposal&&<>
        <section>
          <h3>Cảnh và tư liệu tham chiếu</h3>
          <p className="env-muted">{proposal.shot_count} cảnh · thời lượng dự kiến {proposal.runtime_seconds} giây.
            Thông tin nhân vật và bối cảnh lấy từ hồ sơ đã chuẩn bị.</p>
          <ul className="studio-shot-list">
            {shots.map(shot=><li key={shot.shot_id}>
              <strong>Cảnh {shot.shot_id}</strong>
              {shot.action_camera&&<div>{shot.action_camera}</div>}
              {shot.caption&&<div className="env-muted">Phụ đề: {shot.caption}</div>}
              {shot.character_ids?.length>0&&<div className="env-muted">Nhân vật: {shot.character_ids.join(', ')}</div>}
            </li>)}
          </ul>
        </section>
        <section>
          <h3>Âm thanh và bản dựng</h3>
          {render?<>
            <p>Đã xác minh hồ sơ và tính toàn vẹn của file. Owner cần xem và nghe bản dựng để đánh giá chất lượng.</p>
            {Number.isFinite(render.technical?.duration_seconds)&&
              <p>Thời lượng bản dựng: {render.technical.duration_seconds.toLocaleString('vi-VN')} giây.</p>}
            <Text code className="env-break">workspace/films/{film}/productions/{id}/episode.mp4</Text>
          </>:<p>Chưa có bản dựng. Bạn có thể tạo thoại hoặc dựng MP4 bằng công cụ local.</p>}
          {state==='PREPARED_NOT_RENDERED'&&<Button onClick={onAssembly}>Mở công cụ dựng</Button>}
        </section>
        <details className="studio-details"><summary>Thông tin kỹ thuật và mã SHA</summary>
          <div>SHA tập phim: {proposal.episode_sha256}</div>
          {render&&<div>SHA bản dựng: {render.video_sha256}</div>}
          <pre className="source-text">{JSON.stringify(shots,null,2)}</pre>
        </details>
      </>}
    </div>
  </Drawer>;
}
