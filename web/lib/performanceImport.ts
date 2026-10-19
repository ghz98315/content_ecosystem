/** CSV/TSV parser for explicitly imported, already registered publication metrics. */
export const METRIC_FIELDS = ['views','likes','comments','shares','saves','follows'] as const;
export type MetricField = typeof METRIC_FIELDS[number];
export type ImportRow = { postId:string;recordedAt:string;notes:string } & Record<MetricField,number>;
const aliases:Record<string,string>={post_id:'postId',postid:'postId','作品ID':'postId','作品id':'postId','发布作品ID':'postId',post_url:'postUrl','作品链接':'postUrl','视频链接':'postUrl',recorded_at:'recordedAt','记录时间':'recordedAt','统计时间':'recordedAt','数据时间':'recordedAt',views:'views','播放量':'views','播放次数':'views','播放':'views',likes:'likes','点赞量':'likes','点赞数':'likes','点赞':'likes',comments:'comments','评论量':'comments','评论数':'comments','评论':'comments',shares:'shares','分享量':'shares','分享次数':'shares','转发':'shares',saves:'saves','收藏量':'saves','收藏数':'saves','收藏':'saves',follows:'follows','涨粉':'follows','新增粉丝':'follows',notes:'notes','备注':'notes'};
export function parseDelimited(text:string):string[][] {
 if(text.length>2_000_000)throw new Error('文件超过2MB，请拆分导入');
 text=text.replace(/^\uFEFF/,'');const first=text.split(/\r?\n/,1)[0]||'';
 const delimiter=first.includes('\t')?'\t':',';const rows:string[][]=[];let row:string[]=[],cell='',quoted=false,afterQuote=false;
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;afterQuote=true;}}else cell+=c;continue;}
  if(afterQuote&&c!==delimiter&&c!=='\r'&&c!=='\n'&&c!==' ')throw new Error('CSV引号后出现无效字符');
  if(c==='"'){if(cell||afterQuote)throw new Error('CSV字段中的引号需要成对转义');quoted=true;continue;}
  if(c===delimiter){row.push(cell);cell='';afterQuote=false;continue;}
  if(c==='\r'||c==='\n'){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v.trim()))rows.push(row);row=[];cell='';afterQuote=false;continue;}
  if(!afterQuote)cell+=c;
 }
 if(quoted)throw new Error('CSV存在未关闭的引号');row.push(cell);if(row.some(v=>v.trim()))rows.push(row);
 if(rows.length>201)throw new Error('每次最多导入200行，请拆分文件');
 return rows;
}
function count(value:string,label:string){
 const clean=value.trim().replace(/,/g,'');
 if(!/^\d+$/.test(clean))throw new Error(`${label}须为完整非负整数，不能使用“1.2万”或公式`);
 const number=Number(clean);if(!Number.isSafeInteger(number)||number>2147483647)throw new Error(`${label}超出可用整数范围`);return number;
}
function link(value:string){try{const url=new URL(value.trim());url.hash='';return url.toString().replace(/\/$/,'');}catch{return value.trim();}}
export function prepareImport(text:string,posts:Array<{id:string;post_url:string|null}>,defaultRecordedAt:string,defaultPostId=''):{rows:ImportRow[];errors:string[]} {
 const cells=parseDelimited(text);if(cells.length<2)throw new Error('文件需要表头和至少一行数据');
 const headers=cells[0].map(h=>aliases[h.trim()]||'');const known=headers.filter(Boolean);
 if(new Set(known).size!==known.length)throw new Error('多个表头对应同一字段，请保留一列');
 if(!headers.includes('views'))throw new Error('缺少播放量 / views 列');
 const ids=new Set(posts.map(p=>p.id));const rows:ImportRow[]=[];const errors:string[]=[];
 for(let index=1;index<cells.length;index++){
  try{
   if(cells[index].length!==headers.length)throw new Error('列数与表头不一致');
   const values=Object.create(null) as Record<string,string>;headers.forEach((h,i)=>{if(h)values[h]=cells[index][i].trim();});
   let postId=values.postId||'';
   if(postId&&values.postUrl&&!posts.some(p=>p.id===postId&&p.post_url&&link(p.post_url)===link(values.postUrl)))throw new Error('作品ID与作品链接不一致');
   if(!postId&&values.postUrl){const matches=posts.filter(p=>p.post_url&&link(p.post_url)===link(values.postUrl));if(matches.length!==1)throw new Error('作品链接未唯一匹配已登记作品，请先登记或填写作品ID');postId=matches[0].id;}
   if(!postId&&!values.postUrl)postId=defaultPostId;
   if(!ids.has(postId))throw new Error('作品ID不属于当前工作区已登记作品');
   const recordedAt=new Date(values.recordedAt||defaultRecordedAt);if(Number.isNaN(recordedAt.getTime())||recordedAt.getTime()>Date.now()+300000)throw new Error('数据时间无效或在未来');
   const missing=METRIC_FIELDS.filter(field=>!values[field]);
   const metrics=Object.fromEntries(METRIC_FIELDS.map(field=>[field,values[field]?count(values[field],field):0])) as Record<MetricField,number>;
   if(!values.views)throw new Error('播放量不能为空');
   const notes=[values.notes||'',missing.length?`导入缺失字段按0占位：${missing.join('、')}`:''].filter(Boolean).join('；');
   if(notes.length>500)throw new Error('备注超过500字');
   rows.push({postId,recordedAt:recordedAt.toISOString(),...metrics,notes});
  }catch(error){errors.push(`第${index+1}行：${error instanceof Error?error.message:'格式无效'}`);}
 }
 return {rows,errors};
}
export const IMPORT_TEMPLATE='\uFEFF作品ID,统计时间,播放量,点赞数,评论数,分享量,收藏数,涨粉,备注\r\n';
