const sectionLabel=/(\*\*(?:tên phim|tên video|phong cách|nhân vật|bối cảnh|kịch bản|nội dung|cảnh\s+\d+)(?=[:*])[^*\n]*\*\*)/giu;

export function scriptBlocks(text=''){
  return text.replace(/\r\n?/g,'\n')
    .replace(/(\*\*)[ \t]+(?=(?:phong cách|nhân vật|bối cảnh|kịch bản|nội dung):)/giu,'$1\n\n')
    .replace(sectionLabel,'\n\n$1')
    .trim().split(/\n\s*\n/).filter(Boolean);
}

export function draftTitle(job){
  const idea=job?.brief?.idea?.trim();
  const authored=Boolean(job?.duration_plan?.content_scene_count);
  const explicit=idea?.match(/^(?:#{1,6}\s+)?(?:\*\*)?(?:Tên phim|Tên video)\s*:\s*(?:\*\*)?([^\n*]+)/imu);
  if(job?.board?.title){
    if(!authored)return job.board.title;
    return explicit?.[1].trim()||job.board.title.replace(/\s+[·—–-]\s*(?:Cảnh|Scene)\s+\d+\b.*$/iu,'').trim();
  }
  if(!idea)return 'Đang chuẩn bị bản nháp';
  const first=explicit?.[1]??scriptBlocks(idea)[0]?.split('\n')[0]??'';
  const plain=first.replace(/^#{1,6}\s+/,'').replace(/\*\*/g,'').trim();
  const characters=Array.from(plain);
  if(characters.length<=84)return plain||'Video chưa đặt tên';
  const prefix=characters.slice(0,81).join('');
  return (prefix.replace(/\s+\S*$/u,'')||prefix)+'…';
}
