export type VideoText = {title:string;subtitle:string;footnote:string};
export function resolveVideoText(params:Record<string,any>,rewrite:Record<string,any>={}):VideoText {
 const saved=params.video_text;
 if(saved&&typeof saved==='object')return {title:String(saved.title??''),subtitle:String(saved.subtitle??''),footnote:String(saved.footnote??'')};
 return {title:String(params.main_title??rewrite.cover_title??''),subtitle:String(params.subtitle??rewrite.cover_subtitle??''),footnote:String(params.footnote??'读书分享')};
}
export function validateVideoText(value:VideoText,requireHistoryCover=false):VideoText {
 const text={title:value.title.trim(),subtitle:value.subtitle.trim(),footnote:value.footnote.trim()};
 for(const [key,label,max] of [['title','画面主标题',32],['subtitle','画面副标题',48],['footnote','右下脚注',60]] as const){
  if(text[key].length>max||/[\r\n]/.test(text[key]))throw new Error(`${label}请填写不超过${max}字的单行文字`);
 }
 if(requireHistoryCover){
  if(!text.title||!text.subtitle)throw new Error('历史类请在上方“成片画面文字”填写主标题和副标题，再确认改写稿');
  if(text.title.length>24||text.subtitle.length>36)throw new Error('历史类主标题不得超过24字，副标题不得超过36字');
 }
 return text;
}
