import {scriptBlocks} from './scriptPresentation.js';
import './script-content.css';

function emphasis(text){
  return text.split(/(\*\*[^*\n]+\*\*)/).map((part,index)=>index%2
    ?<strong key={index}>{part.slice(2,-2)}</strong>:part);
}

export function ScriptContent({text}){
  return <div className="script-content">
    {scriptBlocks(text).map((block,index)=>{
      const markdownHeading=block.match(/^#{1,6}\s+([^\n]+)(?:\n([\s\S]*))?$/);
      const labeled=block.match(/^\*\*([^*\n]+:[^*\n]*|(?:Cảnh|Scene)\s+\d+\b[^*\n]*)\*\*\s*([\s\S]*)$/iu);
      const plainLabel=block.match(/^((?:phong cách|nhân vật|bối cảnh|kịch bản|nội dung):)[ \t]*([\s\S]*)$/iu);
      if(markdownHeading||labeled||plainLabel){
        const [,heading,body]=markdownHeading??labeled??plainLabel;
        return <section key={index}><h4>{emphasis(heading)}</h4>{body&&<p>{emphasis(body)}</p>}</section>;
      }
      const lines=block.split('\n');
      if(lines.every(line=>/^\s*[-*+]\s+/.test(line))){
        return <ul key={index}>{lines.map((line,i)=><li key={i}>{emphasis(line.replace(/^\s*[-*+]\s+/,''))}</li>)}</ul>;
      }
      return <p key={index}>{emphasis(block)}</p>;
    })}
  </div>;
}
