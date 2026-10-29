import {createClient} from '@supabase/supabase-js';
import {NextResponse} from 'next/server';
import {productionTemplate} from '@/lib/productionTemplates';
export const dynamic='force-dynamic';

export async function PATCH(request:Request){
  const token=request.headers.get('authorization')?.match(/^Bearer\s+(.+)$/i)?.[1];
  if(!token)return NextResponse.json({error:'请先登录'},{status:401});
  const admin=createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,process.env.SUPABASE_SERVICE_KEY!);
  const {data:auth,error:authError}=await admin.auth.getUser(token);
  if(authError||!auth.user)return NextResponse.json({error:'登录会话已失效'},{status:401});
  let taskId='',locked=false,previousStatus='';
  const originals:Record<string,{id:string;params:Record<string,unknown>}>= {};
  try{
    const body=await request.json();taskId=String(body.taskId||'');
    const template=productionTemplate(String(body.templateId||''));
    if(!['guoxue-v1','health-v1'].includes(template.id))throw new Error('当前只支持国学类与健康类相互调整');
    const {data:task}=await admin.from('tasks').select('id,owner,status').eq('id',taskId).single();
    if(!task||task.owner!==auth.user.id)throw new Error('任务不存在或无权修改');
    if(!['pending','needs_review'].includes(task.status))throw new Error('当前任务正在处理或已完成，请等阶段结束后再调整');
    previousStatus=task.status;
    const {data:held}=await admin.from('tasks').update({status:'configuring'}).eq('id',taskId).eq('status',previousStatus).select('id');
    if(held?.length!==1)throw new Error('任务状态已变化，请刷新后重试');locked=true;
    const {data:stages,error:readError}=await admin.from('stages').select('id,kind,status,params').eq('task_id',taskId);
    if(readError||!stages)throw new Error('阶段读取失败');
    const by=Object.fromEntries(stages.map(s=>[s.kind,s]));
    if(stages.some(s=>s.status==='processing')||by.image?.status!=='pending'||by.render?.status!=='pending')throw new Error('已有图片或成片开始生成，不能直接切换类别');
    if(!(by.rewrite?.status==='pending'||(by.rewrite?.status==='done'&&by.rewrite?.params?.input_mode==='ready_script')))throw new Error('改写已完成；请先处理稿件，再调整类别');
    for(const kind of ['rewrite','image','render'])originals[kind]={id:by[kind].id,params:by[kind].params||{}};
    const line=template.category,version=line==='guoxue'?3:2;
    const rewrite={...originals.rewrite.params,content_line:line,rewrite_domain:line};
    const image:Record<string,unknown>={...originals.image.params,content_line:line,production_template:template.id,template_version:version,visual_style:template.style,visual_preset_id:template.preset,image_aspect_ratio:template.aspect,grid_cells:template.gridCells};
    if(template.gridResolution)image.grid_resolution=template.gridResolution;else delete image.grid_resolution;
    const render={...originals.render.params,content_line:line,production_template:template.id,template_version:version,title_font:template.font,title_color:template.color,frame_mode:template.frameMode};
    for(const [kind,params] of Object.entries({rewrite,image,render})){
      const {data,error}=await admin.from('stages').update({params}).eq('id',originals[kind].id).eq('status',by[kind].status).select('id');
      if(error||data?.length!==1)throw new Error(error?.message||'阶段状态已变化，请刷新重试');
    }
    const {data:released,error:releaseError}=await admin.from('tasks').update({status:previousStatus,content_category:line}).eq('id',taskId).eq('status','configuring').select('id');
    if(releaseError||released?.length!==1)throw new Error(releaseError?.message||'类别保存失败');locked=false;
    return NextResponse.json({ok:true,category:line});
  }catch(error){
    if(locked){
      for(const original of Object.values(originals))await admin.from('stages').update({params:original.params}).eq('id',original.id);
      await admin.from('tasks').update({status:previousStatus}).eq('id',taskId).eq('status','configuring');
    }
    return NextResponse.json({error:error instanceof Error?error.message:'类别调整失败'},{status:400});
  }
}
