export type VideoText = {title:string;subtitle:string;footnote:string};
export function healthVideoTextPreset(bookName:string,author:string):VideoText {
 const name=bookName.trim().replace(/^《|》$/g,'');
 const writer=author.trim();
 return {
  title:name?`《${name}》`:'',
  subtitle:writer?`${writer}（著）`:'',
  footnote:`${name?`本文根据《${name}》书籍和资料整理`:'本文根据书籍和资料整理'}\n仅作参考分享\n不提供任何健康建议或者行为指导`,
 };
}
export function resolveVideoText(params:Record<string,any>,rewrite:Record<string,any>={}):VideoText {
 const saved=params.video_text;
 if(saved&&typeof saved==='object')return {title:String(saved.title??''),subtitle:String(saved.subtitle??''),footnote:String(saved.footnote??'')};
 if(params.production_template==='health-v1'||(!params.production_template&&params.content_line==='health')){
  const preset=healthVideoTextPreset(String(rewrite.book_name??rewrite.book_title??''),String(rewrite.author??''));
  return {title:String(params.main_title??preset.title),subtitle:String(params.subtitle??preset.subtitle),footnote:String(params.footnote??preset.footnote)};
 }
 return {title:String(params.main_title??rewrite.cover_title??''),subtitle:String(params.subtitle??rewrite.cover_subtitle??''),footnote:String(params.footnote??(params.production_template==='scene-v1'?'图片由AI生成':'读书分享'))};
}
export function validateVideoText(value:VideoText,requireHistoryCover=false,healthFootnote=false):VideoText {
 const text={title:value.title.trim(),subtitle:value.subtitle.trim(),footnote:value.footnote.replace(/\r\n?/g,'\n').trim()};
 for(const [key,label,max] of [['title','画面主标题',32],['subtitle','画面副标题',48],['footnote','右下脚注',60]] as const){
  if(key==='footnote'&&healthFootnote){if(text[key].length>80||text[key].split('\n').length>4)throw new Error('健康类脚注最多4行，总计不超过80字');continue;}
  if(text[key].length>max||/[\r\n]/.test(text[key]))throw new Error(`${label}请填写不超过${max}字的单行文字`);
 }
 if(requireHistoryCover){
  if(!text.title||!text.subtitle)throw new Error('历史类请在上方“成片画面文字”填写主标题和副标题，再确认改写稿');
  if(text.title.length>24||text.subtitle.length>36)throw new Error('历史类主标题不得超过24字，副标题不得超过36字');
 }
 return text;
}
