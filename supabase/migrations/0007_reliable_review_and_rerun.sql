-- Make review confirmation and dependency-aware reruns atomic.
-- This supersedes 0006 and is safe to apply whether 0006 ran or not.

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
     and t.owner = auth.uid()
   for update of s;

  if v_task_id is null then
    raise exception 'stage not found or not owned by current user';
  end if;

  update public.stages
     set status = 'pending',
         error = null,
         output_ref = null,
         params = params
           - 'chosen_index'
           - 'final_text'
           - 'manual_book_name'
           - 'book_confirmed'
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

create or replace function public.confirm_rewrite(
  p_stage_id uuid,
  p_chosen_index int,
  p_final_text text
)
returns public.stages
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_task_id uuid;
  v_stage public.stages;
begin
  if p_chosen_index < 0 then
    raise exception 'chosen index must be non-negative';
  end if;
  if nullif(btrim(p_final_text), '') is null then
    raise exception 'final text must not be empty';
  end if;

  select s.task_id
    into v_task_id
    from public.stages s
    join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id
     and s.kind = 'rewrite'
     and s.status = 'needs_review'
     and t.owner = auth.uid()
   for update of s;

  if v_task_id is null then
    raise exception 'rewrite stage is no longer awaiting review';
  end if;

  update public.stages
     set status = 'pending',
         error = null,
         params = params || jsonb_build_object(
           'chosen_index', p_chosen_index,
           'final_text', btrim(p_final_text)
         )
   where id = p_stage_id
   returning * into v_stage;

  update public.tasks
     set status = 'processing'
   where id = v_task_id;

  return v_stage;
end;
$$;

grant execute on function public.rerun_stage(uuid) to authenticated;
grant execute on function public.confirm_rewrite(uuid, integer, text) to authenticated;
