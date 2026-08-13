-- Full image regeneration intentionally differs from normal reruns:
-- it removes only the image/render outputs for an owned task, while preserving
-- upstream manuscript/audio artifacts and image review history.

alter table public.image_replacement_requests
  add column if not exists invalidated_at timestamptz;

create or replace function public.regenerate_image_stage(p_stage_id uuid)
returns setof public.stages
language plpgsql
security definer
set search_path = public, storage
as $$
declare
  v_task_id uuid;
  v_image_seq int;
  v_paths text[];
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

  select coalesce(array_agg(a.storage_path), array[]::text[])
    into v_paths
    from public.artifacts a
   where a.task_id = v_task_id
     and a.stage_kind in ('image', 'render');

  -- Deleting storage.objects removes the corresponding private bucket objects.
  if cardinality(v_paths) > 0 then
    delete from storage.objects
     where bucket_id = 'artifacts'
       and name = any(v_paths);
  end if;

  delete from public.artifacts
   where task_id = v_task_id
     and stage_kind in ('image', 'render');

  -- Keep the review audit, but never let an old replacement affect new frames.
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

  update public.tasks
     set status = 'processing'
   where id = v_task_id;

  return query
    select * from public.stages
     where task_id = v_task_id
     order by seq;
end;
$$;

grant execute on function public.regenerate_image_stage(uuid) to authenticated;
