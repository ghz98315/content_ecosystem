-- Make history cover confirmation atomic with rewrite confirmation.
create or replace function public.confirm_rewrite(
  p_stage_id uuid,
  p_chosen_index int,
  p_final_text text,
  p_cover_title text default null,
  p_cover_subtitle text default null
)
returns public.stages
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_task_id uuid;
  v_category text;
  v_stage public.stages;
  v_title text := nullif(btrim(p_cover_title), '');
  v_subtitle text := nullif(btrim(p_cover_subtitle), '');
begin
  if p_chosen_index < 0 then raise exception 'chosen index must be non-negative'; end if;
  if nullif(btrim(p_final_text), '') is null then raise exception 'final text must not be empty'; end if;
  select s.task_id, t.content_category into v_task_id, v_category
    from public.stages s join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id and s.kind = 'rewrite' and s.status = 'needs_review'
     and t.owner = auth.uid() for update of s;
  if v_task_id is null then raise exception 'rewrite stage is no longer awaiting review'; end if;
  if v_category = 'social_science' and (v_title is null or v_subtitle is null) then
    raise exception 'history cover title and subtitle must be confirmed with rewrite';
  end if;
  update public.stages set status = 'pending', error = null,
    params = params || jsonb_strip_nulls(jsonb_build_object(
      'chosen_index', p_chosen_index, 'final_text', btrim(p_final_text),
      'cover_title', v_title, 'cover_subtitle', v_subtitle,
      'cover_confirmed', (v_category = 'social_science')))
   where id = p_stage_id returning * into v_stage;
  update public.tasks set status = 'processing' where id = v_task_id;
  return v_stage;
end;
$$;

create or replace function public.rerun_stage(p_stage_id uuid)
returns setof public.stages
language plpgsql security invoker set search_path = public
as $$
declare v_task_id uuid; v_seq int;
begin
  select s.task_id, s.seq into v_task_id, v_seq from public.stages s
    join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id and t.owner = auth.uid() for update of s;
  if v_task_id is null then raise exception 'stage not found or not owned by current user'; end if;
  update public.stages set status='pending', error=null, output_ref=null,
    params = params - 'chosen_index' - 'final_text' - 'manual_book_name' - 'book_confirmed'
      - 'cover_title' - 'cover_subtitle' - 'cover_confirmed'
   where task_id=v_task_id and seq >= v_seq and status <> 'cancelled';
  update public.tasks set status='processing' where id=v_task_id;
  return query select * from public.stages where task_id=v_task_id order by seq;
end;
$$;

grant execute on function public.confirm_rewrite(uuid, integer, text, text, text) to authenticated;
