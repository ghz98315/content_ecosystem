export const DEFAULT_FILE_LIMIT = 50_000_000;
export const MAX_PREPROCESS_INPUT = 200 * 1024 * 1024;
export function safeUploadLimit(bucketLimit:unknown,projectLimit=DEFAULT_FILE_LIMIT){
 const bucket=Number(bucketLimit);const cap=Number.isSafeInteger(bucket)&&bucket>0?Math.min(bucket,projectLimit):projectLimit;
 return Math.max(1,Math.floor(cap*.96));
}
export function uploadTarget(limit:number){return Math.max(1,Math.floor(limit*.9));}
export function audioBitrate(duration:number,target:number){
 if(!Number.isFinite(duration)||duration<=0)throw new Error('无法读取音频时长，未上传文件');
 const budget=Math.floor(target*8/duration/1000);
 const rate=[48,64,80,96,112,128,160,192].filter(rate=>rate<=budget).pop();
 if(!rate)throw new Error('音频过长，无法在当前容量下保留清晰度，请分段上传');
 return rate;
}
