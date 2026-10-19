import {createClient} from '@supabase/supabase-js';
import {NextResponse} from 'next/server';
import { assertStorageUploadSize } from '@/lib/uploadPolicyServer';

export async function POST(request: Request) {
  try {
    const url=process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key=process.env.SUPABASE_SERVICE_KEY;
    if(!url || !key)throw new Error('服务配置缺失');
    const token=request.headers.get('authorization')?.replace(/^Bearer\s+/i,'');
    if(!token)return NextResponse.json({error:'请先登录'},{status:401});
    const admin=createClient(url,key);
    const {data:auth}=await admin.auth.getUser(token);
    if(!auth.user)return NextResponse.json({error:'登录会话已失效'},{status:401});
    const body=await request.json();
    const {data:task}=await admin.from('tasks').select('id').eq('id',String(body.taskId || '')).eq('owner',auth.user.id).maybeSingle();
    if(!task)return NextResponse.json({error:'无权设置该任务音乐'},{status:403});
    const extension=String(body.name || '').split('.').pop()?.toLowerCase();
    const size=Number(body.size);
    if(!['mp3','wav','m4a'].includes(extension || '') || !Number.isSafeInteger(size) || size<=0 || size>25*1024*1024)throw new Error('请选择25MB以内的MP3、WAV或M4A音乐');
    await assertStorageUploadSize(admin,size,25*1024*1024);
    const {data:render}=await admin.from('stages').select('status').eq('task_id',task.id).eq('kind','render').single();
    if(render?.status==='processing')throw new Error('视频正在合成，请稍后再上传');
    const path=`${task.id}/background-music/${crypto.randomUUID()}.${extension}`;
    const {data,error}=await admin.storage.from('artifacts').createSignedUploadUrl(path);
    if(error || !data)throw new Error('准备音乐上传失败');
    return NextResponse.json({path,token:data.token},{headers:{'Cache-Control':'no-store'}});
  } catch(err) {return NextResponse.json({error:err instanceof Error?err.message:'音乐上传失败'},{status:400});}
}
