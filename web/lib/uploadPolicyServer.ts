import { DEFAULT_FILE_LIMIT, safeUploadLimit } from './uploadPolicy';
export async function storageUploadLimit(admin:any){
 const {data,error}=await admin.storage.getBucket('artifacts');
 if(error)throw new Error('读取存储容量限制失败，请稍后重试');
 const configured=Number(process.env.STORAGE_FILE_LIMIT_BYTES||DEFAULT_FILE_LIMIT);
 return safeUploadLimit(data?.file_size_limit,Number.isSafeInteger(configured)&&configured>0?configured:DEFAULT_FILE_LIMIT);
}
export async function assertStorageUploadSize(admin:any,size:number,featureLimit=Infinity){
 const limit=Math.min(await storageUploadLimit(admin),featureLimit);
 if(!Number.isSafeInteger(size)||size<=0||size>limit)throw new Error(`文件需要先处理到 ${(limit/1_000_000).toFixed(1)} MB以内再上传，请刷新后重新选择文件`);
 return limit;
}
