import {createClient} from '@supabase/supabase-js';
import {NextResponse} from 'next/server';
import {workerHealthStatus} from '@/lib/workerHealth';
export const dynamic='force-dynamic';
async function check(request:Request,taskId?:string){
  const token=request.headers.get('authorization')?.match(/^Bearer\s+(.+)$/i)?.[1];
  if(!token)return NextResponse.json({error:'请先登录'},{status:401});
  const admin=createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,process.env.SUPABASE_SERVICE_KEY!,{global:{fetch:(input,init)=>fetch(input,{...init,signal:AbortSignal.timeout(4000)})}});
  const {data:auth,error}=await admin.auth.getUser(token);
  if(error||!auth.user)return NextResponse.json({error:'登录会话已失效'},{status:401});
  if(taskId){
    const {data:task}=await admin.from('tasks').select('owner').eq('id',taskId).single();
    if(task?.owner!==auth.user.id)return NextResponse.json({error:'无权检查该任务'},{status:403});
  }
  const result=await admin.storage.from('artifacts').download('system/worker-health.json');
  const value=result.error||!result.data?null:await result.data.text().then(text=>JSON.parse(text));
  return NextResponse.json(workerHealthStatus(value),{headers:{'Cache-Control':'no-store'}});
}
export async function GET(request:Request){try{return await check(request);}catch{return NextResponse.json(workerHealthStatus(null),{headers:{'Cache-Control':'no-store'}});}}
export async function POST(request:Request){try{const body=await request.json();if(typeof body.taskId!=='string')return NextResponse.json({error:'缺少任务编号'},{status:400});return await check(request,body.taskId);}catch{return NextResponse.json(workerHealthStatus(null),{headers:{'Cache-Control':'no-store'}});}}
