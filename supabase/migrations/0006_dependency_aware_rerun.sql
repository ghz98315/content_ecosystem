-- 依赖感知的阶段重跑：当前阶段及所有下游一起失效，避免旧产物继续被下载。
create or replace function public.rerun_stage(p_stage_id uuid)
returns setof public.stages
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_task_id uuid;
  v_seq int;
begin
  select s.task_id, s.seq
    into v_task_id, v_seq
    from public.stages s
    join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id
     and t.owner = auth.uid();

  if v_task_id is null then
    raise exception 'stage not found or not owned by current user';
  end if;

  update public.stages
     set status = 'pending',
         error = null,
         output_ref = null,
         params = case when seq = v_seq then
           params - 'chosen_index' - 'final_text' - 'manual_book_name' - 'book_confirmed'
           else params end
   where task_id = v_task_id
     and seq >= v_seq
     and status <> 'cancelled';

  update public.tasks
     set status = 'processing'
   where id = v_task_id;

  return query
    select * from public.stages
     where task_id = v_task_id
     order by seq;
end;
$$;

grant execute on function public.rerun_stage(uuid) to authenticated;
