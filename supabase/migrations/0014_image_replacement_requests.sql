create table if not exists public.image_replacement_requests (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(id) on delete cascade,
  stage_id uuid not null references public.stages(id) on delete cascade,
  image_index integer not null check (image_index >= 0),
  note text,
  status text not null default 'pending' check (status in ('pending', 'processing', 'done', 'failed')),
  replacement_path text,
  error text,
  requested_by uuid not null references auth.users(id) on delete cascade,
  requested_at timestamptz not null default now(),
  completed_at timestamptz
);
create index if not exists idx_image_replacement_queue on public.image_replacement_requests(status, requested_at);
alter table public.image_replacement_requests enable row level security;
drop policy if exists "owners read image replacements" on public.image_replacement_requests;
create policy "owners read image replacements" on public.image_replacement_requests for select using (exists (select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()));

create or replace function public.request_image_replacement(p_stage_id uuid, p_image_index integer, p_note text default null)
returns public.image_replacement_requests language plpgsql security invoker set search_path = public as $$
declare v_task_id uuid; v_request public.image_replacement_requests;
begin
  if p_image_index < 0 then raise exception 'image index must be non-negative'; end if;
  select s.task_id into v_task_id from public.stages s join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id and s.kind = 'image' and s.status in ('done', 'needs_review') and t.owner = auth.uid();
  if v_task_id is null then raise exception 'image stage is not ready or not owned by current user'; end if;
  insert into public.image_replacement_requests(task_id, stage_id, image_index, note, requested_by)
    values (v_task_id, p_stage_id, p_image_index, nullif(btrim(p_note), ''), auth.uid()) returning * into v_request;
  return v_request;
end;
$$;
grant execute on function public.request_image_replacement(uuid, integer, text) to authenticated;
