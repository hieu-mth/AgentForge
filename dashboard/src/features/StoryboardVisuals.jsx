import {useRef,useState} from 'react';
import {Alert, Button, Image, Modal, Select, Typography} from 'antd';
const {Text}=Typography;

export function StoryboardVisualModal({task,images,initialIds=[],onClose,onConfirm}) {
  const scenes=task.report?.scenes||[];
  const [ids,setIds]=useState(initialIds);
  const [motion,setMotion]=useState('static');
  const [submitting,setSubmitting]=useState(false);
  const [failed,setFailed]=useState(false);
  const pending=useRef(false);
  const available=new Set(images.map(image=>image.job_id));
  const selected=scenes.filter((_,index)=>available.has(ids[index])).length;
  const missing=Math.max(0,scenes.length-available.size);
  const complete=scenes.length>0&&selected===scenes.length&&
    new Set(ids.slice(0,scenes.length)).size===scenes.length;
  const submit=async()=>{
    if(!complete||pending.current)return;
    pending.current=true;
    setSubmitting(true);setFailed(false);
    try{
      const result=await onConfirm({mode:'studio',motion,image_job_ids:ids.slice(0,scenes.length)});
      if(!result)setFailed(true);
    }catch{setFailed(true);}
    finally{pending.current=false;setSubmitting(false);}
  };
  return <Modal open title="Chọn ảnh cho storyboard" className="storyboard-visual-modal"
    width={860} centered onCancel={onClose} maskClosable={!submitting} keyboard={!submitting}
    closable={!submitting} styles={{body:{padding:0}}}
    footer={<div className="visual-picker-footer">
      <Text type="secondary">{selected}/{scenes.length} cảnh đã chọn ảnh</Text>
      <div><Button onClick={onClose} disabled={submitting}>{missing?'Quay lại tạo ảnh':'Hủy'}</Button>
        <Button type="primary" onClick={submit} disabled={!complete} loading={submitting}>
          Tạo tư liệu từ ảnh đã duyệt
        </Button></div>
    </div>}>
    <div className="visual-picker-body">
      <p className="visual-picker-intro">Chọn một ảnh riêng cho mỗi cảnh. Bước này chỉ tạo tư liệu local, chưa render MP4 và không gọi AI/GPU.</p>
      {missing>0&&<Alert type="warning" showIcon
        message={`Cần thêm ${missing} ảnh để chuẩn bị ${scenes.length} cảnh`}
        description={`Hiện có ${available.size} ảnh nguồn. Quay lại phần tạo ảnh trong kết quả công việc, chuẩn bị đủ ảnh rồi mở lại panel này.`}/>}
      <section aria-label="Ảnh cho từng cảnh" className="visual-picker-section">
        <div className="visual-picker-section-title"><strong>Hình ảnh theo cảnh</strong>
          <Text type="secondary">{available.size} ảnh nguồn</Text></div>
        <div className="visual-picker-scenes">
          {scenes.map((scene,index)=><div className="visual-picker-scene" key={index}>
            <div className="visual-picker-thumbnail">
              {available.has(ids[index])?<Image preview={false}
                alt={'Ảnh đã chọn cho cảnh '+(index+1)} src={'/api/image/'+ids[index]+'/preview'}/>:
                <span aria-hidden="true">{String(index+1).padStart(2,'0')}</span>}
            </div>
            <div className="visual-picker-scene-content">
              <label htmlFor={'scene-image-'+index}>Cảnh {index+1} · {scene.headline}</label>
              <Select id={'scene-image-'+index} aria-label={'Chọn ảnh cảnh '+(index+1)}
                value={available.has(ids[index])?ids[index]:undefined} disabled={missing>0||submitting}
                placeholder={missing?'Chưa đủ ảnh nguồn':'Chọn ảnh đã kiểm tra'}
                onChange={value=>setIds(previous=>{const next=[...previous];next[index]=value;return next;})}
                options={images.map(image=>({value:image.job_id,
                  label:(image.source||'Ảnh AI')+' · '+image.job_id.slice(0,8),
                  disabled:ids.some((id,other)=>other!==index&&id===image.job_id)}))}/>
            </div>
          </div>)}
        </div>
      </section>
      <section className="visual-picker-motion" aria-label="Chuyển động camera">
        <div><label htmlFor="storyboard-camera"><strong>Chuyển động camera</strong></label>
          <p>Video dùng ảnh tĩnh. Zoom/Pan mô phỏng camera, không tạo chuyển động thật trong cảnh.</p></div>
        <Select id="storyboard-camera" aria-label="Chuyển động camera" value={motion}
          disabled={submitting} onChange={setMotion} options={[
            {value:'static',label:'Ảnh tĩnh'}, {value:'slow_zoom',label:'Zoom nhẹ'},
            {value:'slow_pan',label:'Lia chậm'},
          ]}/>
      </section>
      <details className="visual-picker-source"><summary>Thông tin nguồn & lưu ý</summary>
        <p>Chỉ dùng ảnh AI đã kiểm tra cho đúng sản phẩm. Muốn video chuyển động thực cần clip từ Film Studio hoặc video model. MP4 vẫn cần duyệt render riêng.</p>
        <Text type="secondary">SHA storyboard</Text><code>{task.storyboard_source_sha}</code>
      </details>
      {failed&&<p role="alert" className="visual-picker-error">Chưa tạo được tư liệu. Hãy kiểm tra thông báo lỗi; lựa chọn ảnh vẫn được giữ lại.</p>}
    </div>
  </Modal>;
}
