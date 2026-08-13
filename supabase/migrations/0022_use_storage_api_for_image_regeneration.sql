-- Supabase Storage objects must be deleted through the Storage API, not SQL.
-- The web server performs that authorized object deletion before calling this RPC.

create or replace function public.regenerate_image_stage(p_stage_id uuid)
returns setof public.stages
language plpgsql
security definer
set search_path = public
as $$
declare
  v_task_id uuid;
  v_image_seq int;
begin
  select s.task_id, s.seq
    into v_task_id, v_image_seq
    from public.stages s
    join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id
     and s.kind = 'image'
     and t.owner = auth.uid()
   for update of s;

  if v_task_id is null then
    raise exception 'image stage not found or not owned by current user';
  end if;

  delete from public.artifacts
   where task_id = v_task_id
     and stage_kind in ('image', 'render');

  update public.image_replacement_requests
     set invalidated_at = now()
   where task_id = v_task_id
     and invalidated_at is null;

  update public.stages
     set status = 'pending',
         error = null,
         output_ref = null,
         params = case
           when seq = v_image_seq then params - 'image_provider_jobs'
           else params
         end
   where task_id = v_task_id
     and seq >= v_image_seq
     and status <> 'cancelled';

  update public.tasks set status = 'processing' where id = v_task_id;

  return query
    select * from public.stages where task_id = v_task_id order by seq;
end;
$$;
