import { createClient } from '@supabase/supabase-js';
import { NextResponse } from 'next/server';
import { assertStorageUploadSize } from '@/lib/uploadPolicyServer';

export async function POST(request: Request) {
  try {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_KEY;
    if (!url || !key) throw new Error('服务配置缺失');
    const token = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '');
    const admin = createClient(url, key);
    const user = token ? (await admin.auth.getUser(token)).data.user : null;
    if (!user) return NextResponse.json({error:'请先登录'},{status:401});
    const { taskId, name, size } = await request.json();
    const {data:task} = await admin.from('tasks').select('id,content_category,narration_mode').eq('id', String(taskId || '')).eq('owner',user.id).maybeSingle();
    if (!task) return NextResponse.json({error:'无权设置该任务封面'},{status:403});
    const { data: render } = await admin.from('stages').select('params,status').eq('task_id',task.id).eq('kind','render').single();
    const stock = render?.params?.visual_mode === 'stock_video';
    const history = !stock && task.narration_mode !== 'dual_dialogue'
      && (render?.params?.content_line || task.content_category) === 'social_science';
    if (!render || render.status === 'processing') {
      throw new Error('请在成片开始前或结束后设置封面');
    }
    if (history) {
      const {data: image, error} = await admin.from('stages').select('status').eq('task_id',task.id).eq('kind','image').single();
      if (error || !image || image.status === 'processing') throw new Error('请在生图前或本批图片生成后设置封面');
    }
    const extension = String(name || '').split('.').pop()?.toLowerCase();
    const limit = 5 * 1024 * 1024;
    if (!['png','jpg','jpeg','webp'].includes(extension || '') || !Number.isSafeInteger(size) || size <= 0 || size > limit) {
      throw new Error('请选择 5 MB 以内的 PNG、JPG 或 WebP 封面');
    }
    await assertStorageUploadSize(admin, size, limit);
    const path = `${task.id}/video-cover/${crypto.randomUUID()}.${extension}`;
    const {data,error} = await admin.storage.from('artifacts').createSignedUploadUrl(path);
    if (error || !data) throw new Error('准备封面上传失败');
    return NextResponse.json({path,token:data.token});
  } catch (err) {return NextResponse.json({error:err instanceof Error?err.message:'封面上传失败'},{status:400});}
}
