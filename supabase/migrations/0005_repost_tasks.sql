-- Independent second-publication video variants.
-- Keep this migration safe to run when 0003 was not applied manually yet.
alter table public.tasks
  add column if not exists content_category text not null default 'health';

alter table public.tasks
  drop constraint if exists tasks_content_category_check;

alter table public.tasks
  add constraint tasks_content_category_check
  check (content_category in ('health', 'social_science', 'education'));

alter table public.tasks
  add column if not exists rewrite_mode text not null default 'initial_dedup',
  add column if not exists source_task_id uuid references public.tasks(id) on delete set null,
  add column if not exists version_no int not null default 1;

alter table public.tasks
  drop constraint if exists tasks_rewrite_mode_check;

alter table public.tasks
  add constraint tasks_rewrite_mode_check
  check (rewrite_mode in ('initial_dedup', 'repost_dedup'));

alter table public.tasks
  drop constraint if exists tasks_version_no_check;

alter table public.tasks
  add constraint tasks_version_no_check
  check (version_no >= 1);

create index if not exists idx_tasks_source_task on public.tasks(source_task_id);

create or replace function public.seed_stages()
returns trigger
language plpgsql
as $$
declare
  kinds stage_kind[] := array[
    'ingest','transcribe','clean','rewrite','image','book','tts','render'
  ]::stage_kind[];
  k stage_kind;
  i int := 1;
  initial_status stage_status;
  stage_params jsonb;
begin
  foreach k in array kinds loop
    initial_status := 'pending';
    stage_params := '{}'::jsonb;
    if new.rewrite_mode = 'repost_dedup' and k in ('ingest', 'transcribe', 'clean') then
      initial_status := 'cancelled';
    end if;
    if k = 'rewrite' then
      stage_params := jsonb_build_object(
        'rewrite_mode', new.rewrite_mode,
        'source_task_id', new.source_task_id
      );
    end if;
    insert into public.stages (task_id, kind, seq, status, params)
      values (new.id, k, i, initial_status, stage_params);
    i := i + 1;
  end loop;
  return new;
end $$;

create or replace function public.create_repost_task(p_source_task_id uuid)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  source_task public.tasks%rowtype;
  existing_task uuid;
  new_task uuid;
begin
  select * into source_task
  from public.tasks
  where id = p_source_task_id and owner = auth.uid();
  if not found then
    raise exception '源任务不存在或无权访问';
  end if;

  if not exists (
    select 1 from public.stages
    where task_id = p_source_task_id and kind = 'render' and status = 'done'
  ) then
    raise exception '源任务成片尚未完成，不能创建二次发布版本';
  end if;

  select id into existing_task
  from public.tasks
  where source_task_id = p_source_task_id
    and rewrite_mode = 'repost_dedup'
    and status not in ('cancelled', 'failed')
  order by created_at desc
  limit 1;
  if existing_task is not null then
    return existing_task;
  end if;

  insert into public.tasks (
    owner, source_url, title, play_count, author, status,
    content_category, rewrite_mode, source_task_id, version_no
  ) values (
    source_task.owner,
    source_task.source_url,
    coalesce(source_task.title, '图书视频') || ' · 二次发布 V2',
    source_task.play_count,
    source_task.author,
    'pending',
    source_task.content_category,
    'repost_dedup',
    source_task.id,
    source_task.version_no + 1
  ) returning id into new_task;

  return new_task;
end $$;

grant execute on function public.create_repost_task(uuid) to authenticated;