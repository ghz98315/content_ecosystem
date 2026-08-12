-- Durable early book candidates shared by collection and the future book library.

create table if not exists public.task_book_signals (
  task_id uuid primary key references public.tasks(id) on delete cascade,
  detected_title text,
  detected_author text,
  confidence text not null default 'low' check (confidence in ('low', 'medium', 'high')),
  evidence text,
  source_stage public.stage_kind not null default 'transcribe',
  confirmed_title text,
  confirmed_author text,
  confirmed_by uuid references auth.users(id),
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.task_book_signals enable row level security;

drop policy if exists "owners read task book signals" on public.task_book_signals;
create policy "owners read task book signals" on public.task_book_signals
  for select using (exists (
    select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()
  ));

drop policy if exists "owners update task book signals" on public.task_book_signals;
create policy "owners update task book signals" on public.task_book_signals
  for update using (exists (
    select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()
  ));

drop trigger if exists trg_touch_task_book_signals on public.task_book_signals;
create trigger trg_touch_task_book_signals before update on public.task_book_signals
  for each row execute function public.touch_updated_at();

create or replace function public.confirm_task_book_signal(
  p_task_id uuid,
  p_title text,
  p_author text default null
)
returns public.task_book_signals
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_result public.task_book_signals;
begin
  if nullif(btrim(p_title), '') is null then
    raise exception 'book title must not be empty';
  end if;

  update public.task_book_signals s
     set confirmed_title = btrim(p_title),
         confirmed_author = nullif(btrim(p_author), ''),
         confirmed_by = auth.uid(),
         confirmed_at = now()
   where s.task_id = p_task_id
     and exists (select 1 from public.tasks t where t.id = s.task_id and t.owner = auth.uid())
   returning * into v_result;

  if v_result.task_id is null then
    raise exception 'book signal not found or not owned by current user';
  end if;
  return v_result;
end;
$$;

drop function if exists public.collection_tasks(text, text, bigint, bigint);
create or replace function public.collection_tasks(
  p_query text default null,
  p_status text default null,
  p_min_followers bigint default 0,
  p_min_comments bigint default 0,
  p_book_query text default null
)
returns setof public.tasks
language sql
stable
security invoker
set search_path = public
as $$
  select t.*
    from public.tasks t
    left join public.task_book_signals bs on bs.task_id = t.id
    left join lateral (
      select a.meta from public.artifacts a
       where a.task_id = t.id and a.stage_kind = 'ingest' and a.type = 'audio'
       order by a.created_at desc limit 1
    ) ingest on true
   where t.owner = auth.uid()
     and (nullif(p_status, '') is null or t.status = p_status)
     and (nullif(btrim(p_book_query), '') is null or coalesce(bs.confirmed_title, bs.detected_title, '') ilike '%' || btrim(p_book_query) || '%')
     and (nullif(btrim(p_query), '') is null
       or coalesce(t.title, '') ilike '%' || btrim(p_query) || '%'
       or coalesce(t.source_url, '') ilike '%' || btrim(p_query) || '%'
       or coalesce(t.author->>'name', '') ilike '%' || btrim(p_query) || '%'
       or coalesce(ingest.meta->>'desc', ingest.meta->>'description', '') ilike '%' || btrim(p_query) || '%')
     and (coalesce(p_min_followers, 0) <= 0 or case
       when coalesce(t.author->>'fans_count', t.author->>'follower_count', '') ~ '^\d+$'
       then coalesce(t.author->>'fans_count', t.author->>'follower_count')::bigint else 0 end >= p_min_followers)
     and (coalesce(p_min_comments, 0) <= 0 or case
       when coalesce(ingest.meta->>'comment_count', '') ~ '^\d+$'
       then (ingest.meta->>'comment_count')::bigint else 0 end >= p_min_comments)
   order by t.created_at desc;
$$;

grant execute on function public.confirm_task_book_signal(uuid, text, text) to authenticated;
grant execute on function public.collection_tasks(text, text, bigint, bigint, text) to authenticated;
