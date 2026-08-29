-- Prevent narration paragraphs from being stored as history cover copy.
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
  if v_category = 'social_science' and char_length(v_title) > 24 then
    raise exception 'history cover title must not exceed 24 characters';
  end if;
  if v_category = 'social_science' and char_length(v_subtitle) > 36 then
    raise exception 'history cover subtitle must not exceed 36 characters';
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

grant execute on function public.confirm_rewrite(uuid, integer, text, text, text) to authenticated;
