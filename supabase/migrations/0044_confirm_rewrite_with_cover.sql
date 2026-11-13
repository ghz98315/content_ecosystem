-- Publish review settings and queue the approved script in a single transaction.
create or replace function public.confirm_rewrite_with_cover(
  p_stage_id uuid,
  p_chosen_index int,
  p_final_text text,
  p_expected_rewrite_ref text,
  p_video_text jsonb,
  p_cover_path text,
  p_expected_video_text jsonb,
  p_expected_cover_path text
) returns public.stages
language plpgsql security invoker set search_path = public
as $$
declare
  v_task_id uuid;
  v_category text;
  v_render public.stages;
  v_title text := btrim(coalesce(p_video_text->>'title', ''));
  v_subtitle text := btrim(coalesce(p_video_text->>'subtitle', ''));
  v_path text := nullif(p_cover_path, '');
begin
  select s.task_id, t.content_category::text into v_task_id, v_category
    from public.stages s join public.tasks t on t.id = s.task_id
    where s.id = p_stage_id and s.kind = 'rewrite' and s.status = 'needs_review'
      and s.output_ref is not distinct from p_expected_rewrite_ref
      and t.owner = auth.uid() for update of s;
  if not found then raise exception '改写稿已不在待确认状态，请刷新'; end if;

  select * into v_render from public.stages
    where task_id = v_task_id and kind = 'render' for update;
  if not found or v_render.status = 'processing' then
    raise exception '当前无法修改成片设置，请刷新后重试';
  end if;
  if nullif(v_render.params->'video_text', 'null'::jsonb) is distinct from nullif(p_expected_video_text, 'null'::jsonb)
     or coalesce(v_render.params->>'video_cover_path', '') <> coalesce(p_expected_cover_path, '') then
    raise exception '封面或画面文字已在其他页面更新，请刷新后再确认';
  end if;
  if p_video_text is not null and (jsonb_typeof(p_video_text) is distinct from 'object'
     or char_length(v_title) > 32 or v_title ~ '[\r\n]'
     or char_length(v_subtitle) > 48
     or char_length(coalesce(p_video_text->>'footnote', '')) > 80
     or char_length(coalesce(p_video_text->>'account_name', '')) > 25) then
    raise exception '画面文字格式无效';
  end if;
  if v_category = 'social_science' and
     (array_length(string_to_array(v_subtitle, chr(10)), 1) is distinct from 2
      or btrim(split_part(v_subtitle, chr(10), 1)) = '' or btrim(split_part(v_subtitle, chr(10), 2)) = '') then
    raise exception '历史社科副标题请分两行填写：人物介绍、文案关键总结';
  end if;
  if v_path is not null and v_path !~ ('^' || v_task_id::text || '/video-cover/[0-9a-f-]{36}\.(jpg|jpeg|png|webp)$') then
    raise exception '封面路径不属于当前任务';
  end if;
  if v_path is distinct from nullif(v_render.params->>'video_cover_path', '') and exists (
    select 1 from public.stages where task_id = v_task_id and kind = 'image' and status = 'processing'
  ) then raise exception '画面正在生成，请稍后再修改封面'; end if;

  update public.stages set params = params || jsonb_build_object('video_cover_path', v_path)
    || case when p_video_text is null then '{}'::jsonb else jsonb_build_object('video_text', p_video_text) end
    where id = v_render.id;
  return public.confirm_rewrite(p_stage_id, p_chosen_index, p_final_text, v_title, v_subtitle);
end;
$$;

revoke execute on function public.confirm_rewrite_with_cover(uuid, int, text, text, jsonb, text, jsonb, text) from public;
grant execute on function public.confirm_rewrite_with_cover(uuid, int, text, text, jsonb, text, jsonb, text) to authenticated;
