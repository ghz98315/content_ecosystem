create or replace function public.book_library(p_query text default null, p_status text default 'all', p_limit integer default 20, p_offset integer default 0)
returns table (book_key text, title text, author text, confirmed boolean, task_count bigint, done_count bigint, processing_count bigint, failed_count bigint, review_count bigint, final_count bigint, recent_updated_at timestamptz, latest_task_id uuid, total_count bigint)
language sql stable security invoker set search_path = public as $$
  with grouped as (
    select md5(lower(regexp_replace(btrim(coalesce(s.confirmed_title, s.detected_title)), '\\s+', '', 'g'))) book_key,
      coalesce(s.confirmed_title, s.detected_title) title, coalesce(s.confirmed_author, s.detected_author) author,
      (s.confirmed_title is not null) confirmed, count(distinct t.id)::bigint task_count,
      count(distinct t.id) filter (where t.status = 'done')::bigint done_count, count(distinct t.id) filter (where t.status = 'processing')::bigint processing_count,
      count(distinct t.id) filter (where t.status = 'failed')::bigint failed_count, count(distinct t.id) filter (where t.status = 'needs_review')::bigint review_count,
      count(distinct t.id) filter (where a.type = 'final')::bigint final_count, max(greatest(t.updated_at, coalesce(s.updated_at, t.updated_at))) recent_updated_at,
      (array_agg(t.id order by t.updated_at desc))[1] latest_task_id
    from public.task_book_signals s join public.tasks t on t.id = s.task_id and t.owner = auth.uid()
      left join public.artifacts a on a.task_id = t.id
    where nullif(btrim(coalesce(s.confirmed_title, s.detected_title)), '') is not null
      and (nullif(btrim(p_query), '') is null or coalesce(s.confirmed_title, s.detected_title) ilike '%' || btrim(p_query) || '%' or coalesce(s.confirmed_author, s.detected_author) ilike '%' || btrim(p_query) || '%')
    group by 1,2,3,4
  ), filtered as (select g.*, count(*) over()::bigint total_count from grouped g where p_status = 'all' or (p_status = 'confirmed' and g.confirmed) or (p_status = 'candidate' and not g.confirmed))
  select * from filtered order by recent_updated_at desc nulls last, title asc limit greatest(1, least(coalesce(p_limit, 20), 100)) offset greatest(0, coalesce(p_offset, 0));
$$;

create or replace function public.book_library_tasks(p_book_key text)
returns setof public.tasks language sql stable security invoker set search_path = public as $$
  select t.* from public.tasks t join public.task_book_signals s on s.task_id = t.id where t.owner = auth.uid()
    and md5(lower(regexp_replace(btrim(coalesce(s.confirmed_title, s.detected_title)), '\\s+', '', 'g'))) = p_book_key order by t.updated_at desc;
$$;

create or replace function public.confirm_book_library_candidate(p_book_key text, p_title text, p_author text default null)
returns bigint language plpgsql security invoker set search_path = public as $$
declare v_count bigint;
begin
  if nullif(btrim(p_title), '') is null then raise exception 'book title must not be empty'; end if;
  update public.task_book_signals s set confirmed_title = btrim(p_title), confirmed_author = nullif(btrim(p_author), ''), confirmed_by = auth.uid(), confirmed_at = now()
  where md5(lower(regexp_replace(btrim(coalesce(s.confirmed_title, s.detected_title)), '\\s+', '', 'g'))) = p_book_key
    and exists (select 1 from public.tasks t where t.id = s.task_id and t.owner = auth.uid());
  get diagnostics v_count = row_count;
  if v_count = 0 then raise exception 'book candidate not found or not owned by current user'; end if;
  return v_count;
end;
$$;
grant execute on function public.book_library(text, text, integer, integer) to authenticated;
grant execute on function public.book_library_tasks(text) to authenticated;
grant execute on function public.confirm_book_library_candidate(text, text, text) to authenticated;
