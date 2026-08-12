-- Bounded collection workbench query with owner checks and artifact-backed filters.

create or replace function public.collection_tasks(
  p_query text default null,
  p_status text default null,
  p_min_followers bigint default 0,
  p_min_comments bigint default 0
)
returns setof public.tasks
language sql
stable
security invoker
set search_path = public
as $$
  select t.*
    from public.tasks t
    left join lateral (
      select a.meta
        from public.artifacts a
       where a.task_id = t.id
         and a.stage_kind = 'ingest'
         and a.type = 'audio'
       order by a.created_at desc
       limit 1
    ) ingest on true
   where t.owner = auth.uid()
     and (nullif(p_status, '') is null or t.status = p_status)
     and (
       nullif(btrim(p_query), '') is null
       or coalesce(t.title, '') ilike '%' || btrim(p_query) || '%'
       or coalesce(t.source_url, '') ilike '%' || btrim(p_query) || '%'
       or coalesce(t.author->>'name', '') ilike '%' || btrim(p_query) || '%'
       or coalesce(ingest.meta->>'desc', ingest.meta->>'description', '') ilike '%' || btrim(p_query) || '%'
     )
     and (
       coalesce(p_min_followers, 0) <= 0
       or case
         when coalesce(t.author->>'fans_count', t.author->>'follower_count', '') ~ '^\d+$'
         then coalesce(t.author->>'fans_count', t.author->>'follower_count')::bigint
         else 0
       end >= p_min_followers
     )
     and (
       coalesce(p_min_comments, 0) <= 0
       or case
         when coalesce(ingest.meta->>'comment_count', '') ~ '^\d+$'
         then (ingest.meta->>'comment_count')::bigint
         else 0
       end >= p_min_comments
     )
   order by t.created_at desc;
$$;

grant execute on function public.collection_tasks(text, text, bigint, bigint) to authenticated;
