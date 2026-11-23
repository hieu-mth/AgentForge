export function groupDraftScenes(job) {
  const groups=new Map();
  const source=Array.from(job?.brief?.idea??'');
  for(const [index,scene] of (job?.board?.scenes??[]).entries()){
    const key=scene.content_scene??index+1;
    if(!groups.has(key)){
      const original=scene.content_scene&&scene.script_range?source.slice(...scene.script_range).join('').trim():'';
      const heading=original.split('\n')[0].replace(/^#{1,6}\s+/,'').replace(/\*\*/g,'');
      const title=heading.match(/^(?:Cảnh|Scene)\s+\d+\s*[:—–-]\s*(.+?)(?:\s*\([^)]*\))?$/iu)?.[1];
      groups.set(key,{key,label:'Cảnh '+String(key).padStart(2,'0'),title,original,shots:[]});
    }
    groups.get(key).shots.push({scene,index});
  }
  return [...groups.values()];
}
