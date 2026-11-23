const sectionLabel=/(\*\*(?:tên phim|tên video|phong cách|nhân vật|bối cảnh|kịch bản|nội dung|cảnh\s+\d+)(?=[:*])[^*\n]*\*\*)/giu;

export function scriptBlocks(text=''){
  return text.replace(/\r\n?/g,'\n')
    .replace(/(\*\*)[ \t]+(?=(?:phong cách|nhân vật|bối cảnh|kịch bản|nội dung):)/giu,'$1\n\n')
    .replace(sectionLabel,'\n\n$1')
    .trim().split(/\n\s*\n/).filter(Boolean);
}

export function draftTitle(job){
  if(job?.board?.title)return job.board.title;
  const idea=job?.brief?.idea?.trim();
  if(!idea)return 'Đang chuẩn bị bản nháp';
  const explicit=idea.match(/^(?:#{1,6}\s+)?(?:\*\*)?(?:Tên phim|Tên video)\s*:\s*(?:\*\*)?([^\n*]+)/iu);
  const first=explicit?.[1]??scriptBlocks(idea)[0]?.split('\n')[0]??'';
  const plain=first.replace(/^#{1,6}\s+/,'').replace(/\*\*/g,'').trim();
  const characters=Array.from(plain);
  if(characters.length<=84)return plain||'Video chưa đặt tên';
  const prefix=characters.slice(0,81).join('');
  return (prefix.replace(/\s+\S*$/u,'')||prefix)+'…';
}
