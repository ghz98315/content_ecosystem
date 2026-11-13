import {createClient} from '@supabase/supabase-js';
import {NextResponse} from 'next/server';
import { assertStorageUploadSize } from '@/lib/uploadPolicyServer';
import { userMusicPresetMatch } from '@/lib/userMusicPresets';
import { isMusicCategory } from '@/lib/musicPresets';

async function session(request: Request) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new Error('服务配置缺失');
  const token = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '');
  if (!token) return null;
  const admin = createClient(url, key);
  const { data: auth } = await admin.auth.getUser(token);
  return auth.user ? { admin, owner: auth.user.id } : null;
}

export async function GET(request: Request) {
  try {
    const auth = await session(request);
    if (!auth) return NextResponse.json({error:'请先登录'},{status:401});
    const category = new URL(request.url).searchParams.get('category');
    if (!isMusicCategory(category)) throw new Error('无效音乐类别');
    const prefix = `user-music/${auth.owner}/${category}`;
    const presets = [];
    for (let offset = 0; ; offset += 100) {
      const { data, error } = await auth.admin.storage.from('artifacts').list(prefix, {
        limit: 100, offset, sortBy: { column: 'name', order: 'asc' },
      });
      if (error) throw new Error('个人预设读取失败');
      for (const file of data) {
        const path = `${prefix}/${file.name}`;
        const match = file.id && userMusicPresetMatch(path);
        if (match) presets.push({ path, label: Buffer.from(match[3], 'base64url').toString('utf8') });
      }
      if (data.length < 100) break;
    }
    return NextResponse.json({presets},{headers:{'Cache-Control':'no-store'}});
  } catch (err) {return NextResponse.json({error:err instanceof Error?err.message:'个人预设读取失败'},{status:400});}
}

export async function POST(request: Request) {
  try {
    const auth = await session(request);
    if (!auth) return NextResponse.json({error:'请先登录'},{status:401});
    const {admin,owner} = auth;
    const body=await request.json();
    const {data:task}=await admin.from('tasks').select('id').eq('id',String(body.taskId || '')).eq('owner',owner).maybeSingle();
    if(!task)return NextResponse.json({error:'无权设置该任务音乐'},{status:403});
    const extension=String(body.name || '').split('.').pop()?.toLowerCase();
    const size=Number(body.size);
    if(!['mp3','wav','m4a'].includes(extension || '') || !Number.isSafeInteger(size) || size<=0 || size>25*1024*1024)throw new Error('请选择25MB以内的MP3、WAV或M4A音乐');
    await assertStorageUploadSize(admin,size,25*1024*1024);
    const {data:render}=await admin.from('stages').select('status').eq('task_id',task.id).eq('kind','render').single();
    if(render?.status==='processing')throw new Error('视频正在合成，请稍后再上传');
    let path = `${task.id}/background-music/${crypto.randomUUID()}.${extension}`;
    if (body.preset === true) {
      const category = body.category;
      if (!isMusicCategory(category)) throw new Error('无效音乐类别');
      const label = Array.from(String(body.label || '').trim().replace(/[\u0000-\u001f\u007f]/g, '')).slice(0, 36).join('');
      if (!label) throw new Error('请填写预设音乐名称');
      path = `user-music/${owner}/${category}/${crypto.randomUUID()}--${Buffer.from(label).toString('base64url')}.${extension}`;
    }
    const {data,error}=await admin.storage.from('artifacts').createSignedUploadUrl(path);
    if(error || !data)throw new Error('准备音乐上传失败');
    return NextResponse.json({path,token:data.token},{headers:{'Cache-Control':'no-store'}});
  } catch(err) {return NextResponse.json({error:err instanceof Error?err.message:'音乐上传失败'},{status:400});}
}

export async function DELETE(request: Request) {
  try {
    const auth = await session(request);
    if (!auth) return NextResponse.json({error:'请先登录'},{status:401});
    const {path} = await request.json();
    if (typeof path !== 'string' || userMusicPresetMatch(path)?.[1] !== auth.owner) {
      return NextResponse.json({error:'只能删除本账号的个人预设'},{status:403});
    }
    const { data, error } = await auth.admin.from('tasks').select('id').eq('bgm_path', path).limit(1);
    if (error) throw new Error('无法检查预设是否正在使用');
    if (data.length) return NextResponse.json({error:'仍有任务使用这首音乐，请先在对应任务更换配乐并保存。'},{status:409});
    const { error: removeError } = await auth.admin.storage.from('artifacts').remove([path]);
    if (removeError) throw new Error('预设删除失败，请稍后重试');
    return NextResponse.json({deleted:true});
  } catch (err) {
    return NextResponse.json({error:err instanceof Error ? err.message : '预设删除失败'},{status:400});
  }
}
