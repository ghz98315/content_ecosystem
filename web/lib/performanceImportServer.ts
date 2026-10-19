import { createHash } from 'node:crypto';
import { ImportRow, METRIC_FIELDS } from './performanceImport';
const UUID=/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
export function validateImportRows(value:unknown):ImportRow[]{
 if(!Array.isArray(value)||!value.length||value.length>200)throw new Error('每批需要1至200条数据');
 return value.map((item,index)=>{
  if(!item||typeof item!=='object'||!UUID.test(item.postId||''))throw new Error(`第${index+1}行作品ID无效`);
  if(typeof item.recordedAt!=='string'||!/(?:Z|[+-]\d{2}:\d{2})$/.test(item.recordedAt))throw new Error(`第${index+1}行时间须包含时区`);
  const date=new Date(item.recordedAt);if(!Number.isFinite(date.getTime())||date.getTime()>Date.now()+300000)throw new Error(`第${index+1}行时间无效`);
  const metrics:Record<string,number>={};for(const key of METRIC_FIELDS){if(typeof item[key]!=='number'||!Number.isSafeInteger(item[key])||item[key]<0||item[key]>2147483647)throw new Error(`第${index+1}行${key}无效`);metrics[key]=item[key];}
  if(typeof item.notes!=='string'||item.notes.length>500)throw new Error(`第${index+1}行备注无效`);
  return {postId:item.postId,recordedAt:date.toISOString(),...metrics,notes:item.notes} as ImportRow;
 });
}
function fingerprint(owner:string,row:ImportRow){
 const hex=createHash('sha256').update(`metric-import-v1:${owner}:${row.postId}:${row.recordedAt}`).digest('hex').slice(0,32).split('');hex[12]='5';hex[16]='8';const s=hex.join('');
 return `${s.slice(0,8)}-${s.slice(8,12)}-${s.slice(12,16)}-${s.slice(16,20)}-${s.slice(20)}`;
}
export async function importSnapshots(db:any,owner:string,input:unknown){
 const rows=validateImportRows(input);const ids=[...new Set(rows.map(row=>row.postId))];
 const {data:posts,error:postError}=await db.from('published_posts').select('id').eq('owner',owner).in('id',ids);
 if(postError)throw new Error('校验作品归属失败');if(posts?.length!==ids.length)throw new Error('包含不属于当前工作区的作品，整批未导入');
 const unique=new Map<string,ImportRow>();let duplicates=0;
 for(const row of rows){const key=`${row.postId}|${row.recordedAt}`;const old=unique.get(key);if(old){if(METRIC_FIELDS.some(k=>old[k]!==row[k])||old.notes!==row.notes)throw new Error('文件中同一作品同一时刻存在不同数据，整批未导入');duplicates++;}else unique.set(key,row);}
 const times=[...new Set(rows.map(row=>row.recordedAt))];
 const {data:existing,error}=await db.from('published_post_metrics').select('post_id,recorded_at,views,likes,comments,shares,saves,follows,notes').in('post_id',ids).in('recorded_at',times).limit(1001);
 if(error||existing?.length>1000)throw new Error('历史重复检查未完成，请拆小批次重试');
 const oldRows=new Map<string,any>((existing||[]).map((row:any)=>[`${row.post_id}|${new Date(row.recorded_at).toISOString()}`,row]));
 const payload:Array<{id:string;post_id:string;recorded_at:string;notes:string}&Record<typeof METRIC_FIELDS[number],number>>=[];
 for(const [key,row] of unique){const old=oldRows.get(key);if(old){if(METRIC_FIELDS.some(k=>old[k]!==row[k])||old.notes!==row.notes)throw new Error('同一作品同一时刻已有不同快照，整批未导入；请核对时间，不覆盖历史');duplicates++;continue;}payload.push({id:fingerprint(owner,row),post_id:row.postId,recorded_at:row.recordedAt,views:row.views,likes:row.likes,comments:row.comments,shares:row.shares,saves:row.saves,follows:row.follows,notes:row.notes});}
 if(!payload.length)return {inserted:0,duplicates};
 const {data:inserted,error:writeError}=await db.from('published_post_metrics').upsert(payload,{onConflict:'id',ignoreDuplicates:true}).select('id');
 if(writeError)throw new Error('批量保存失败，请重试；不会覆盖已有历史');
 const insertedIds=new Set((inserted||[]).map((row:any)=>row.id));
 const skipped=payload.filter(row=>!insertedIds.has(row.id));
 if(skipped.length){
  const {data:concurrent,error:checkError}=await db.from('published_post_metrics').select('id,views,likes,comments,shares,saves,follows,notes').in('id',skipped.map(row=>row.id));
  if(checkError||concurrent?.length!==skipped.length)throw new Error('部分数据可能已保存，但并发重复核对失败；请重试相同文件核验，不会覆盖历史');
  if(skipped.some(row=>{const old=concurrent.find((item:any)=>item.id===row.id);return !old||METRIC_FIELDS.some(k=>old[k]!==row[k])||old.notes!==row.notes;}))throw new Error('并发导入出现不同数据；已保留先写入的记录，本批其他数据可能已保存，请刷新核对后重试');
 }
 return {inserted:inserted?.length||0,duplicates:duplicates+payload.length-(inserted?.length||0)};
}
