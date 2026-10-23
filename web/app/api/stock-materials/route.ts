import {createClient} from '@supabase/supabase-js';
import {NextRequest,NextResponse} from 'next/server';
import {validateStockSelection, type StockPlan} from '@/lib/stockSelection';
export const dynamic='force-dynamic';
async function context(request:Request,id:string){
  const token=request.headers.get('authorization')?.match(/^Bearer\s+(.+)$/i)?.[1];
  if(!token)throw new Error('请先登录');
  const url=process.env.NEXT_PUBLIC_SUPABASE_URL!,key=process.env.SUPABASE_SERVICE_KEY!;
  if(!url||!key)throw new Error('服务配置缺失');
  const admin=createClient(url,key);const {data:auth,error}=await admin.auth.getUser(token);
  if(error||!auth.user)throw new Error('登录会话已失效');
  const {data:stage,error:readError}=await admin.from('stages').select('*').eq('id',id).eq('kind','image').single();
  if(readError||!stage||stage.params?.visual_mode!=='stock_video')throw new Error('视频素材阶段不存在');
  const {data:task}=await admin.from('tasks').select('owner,status').eq('id',stage.task_id).single();
  if(task?.owner!==auth.user.id||task.status==='cancelled')throw new Error('无权操作该任务');
  return {admin,stage};
}
export async function GET(request:NextRequest){
  try{const {stage}=await context(request,request.nextUrl.searchParams.get('stageId')||'');
    return NextResponse.json({stage},{headers:{'Cache-Control':'no-store'}});
  }catch(e){return NextResponse.json({error:e instanceof Error?e.message:'读取失败'},{status:400});}
}
export async function PATCH(request:Request){
  try{
    const body=await request.json();const {admin,stage}=await context(request,String(body.stageId||''));
    if(stage.status!=='needs_review')throw new Error('当前未等待素材确认，请刷新查看最新进度');
    const plan=stage.params.stock_plan as StockPlan;
    if(!plan?.revision||plan.revision!==body.revision)throw new Error('素材清单已更新，请重新读取');
    const params={...stage.params};
    if(body.action==='confirm'){
      params.stock_selection=validateStockSelection(plan,body.selections);
      params.stock_confirmed_revision=plan.revision;
    }else if(body.action==='search'){
      if(!Array.isArray(body.queries)||body.queries.length!==plan.entries.length)throw new Error('检索词不完整');
      params.stock_query_overrides=body.queries.map((q:unknown)=>String(q).trim().slice(0,100));
      params.stock_confirmed_revision=null;params.stock_refresh=true;
    }else throw new Error('无效操作');
    // CAS binds confirmation to the exact worker-authored plan, including all source URLs.
    const {data,error}=await admin.from('stages').update({status:'pending',error:null,params})
      .eq('id',stage.id).eq('status','needs_review').eq('updated_at',stage.updated_at).select('id');
    if(error||data?.length!==1)throw new Error(error?.message||'任务刚刚更新，请刷新重试');
    const {error:taskError}=await admin.from('tasks').update({status:'processing'}).eq('id',stage.task_id).neq('status','cancelled');
    if(taskError)throw new Error(taskError.message);
    return NextResponse.json({ok:true});
  }catch(e){return NextResponse.json({error:e instanceof Error?e.message:'保存失败'},{status:400});}
}
