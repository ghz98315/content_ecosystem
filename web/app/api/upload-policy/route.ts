import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';
import { storageUploadLimit } from '@/lib/uploadPolicyServer';
export const dynamic='force-dynamic';
export async function GET(request:Request){
 try{
  const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.SUPABASE_SERVICE_KEY;
  const token=request.headers.get('authorization')?.replace(/^Bearer\s+/i,'');
  if(!url||!key)throw new Error('服务配置缺失');
  if(!token)return NextResponse.json({error:'请先登录'},{status:401});
  const admin=createClient(url,key);const {data,error}=await admin.auth.getUser(token);
  if(error||!data.user)return NextResponse.json({error:'登录会话已失效'},{status:401});
  return NextResponse.json({maxBytes:await storageUploadLimit(admin)},{headers:{'Cache-Control':'no-store'}});
 }catch(error){return NextResponse.json({error:error instanceof Error?error.message:'容量检查失败'},{status:503});}
}
