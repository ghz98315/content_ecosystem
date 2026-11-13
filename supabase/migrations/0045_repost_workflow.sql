create or replace function public.create_repost_task(p_source_task_id uuid)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  src public.tasks%rowtype;
  child_id uuid;
  src_stage public.stages%rowtype;
  inherited jsonb;
  keys text[];
begin
  select * into src from public.tasks
  where id = p_source_task_id and owner = auth.uid() and rewrite_mode = 'initial_dedup'
  for update;
  if not found then raise exception '首发任务不存在或无权访问'; end if;
  if not exists (select 1 from public.stages where task_id = src.id and kind = 'render' and status = 'done')
     or not exists (select 1 from public.stages where task_id = src.id and kind = 'rewrite' and status = 'done') then
    raise exception '首发稿件和成片须完成后才能创建二次发布版本';
  end if;

  select id into child_id from public.tasks
  where owner = src.owner and source_task_id = src.id and rewrite_mode = 'repost_dedup'
    and status not in ('cancelled', 'failed')
  order by created_at desc limit 1;
  if child_id is not null then return child_id; end if;

  insert into public.tasks (
    owner, source_url, title, source_tags, play_count, author, status,
    content_category, narration_mode, rewrite_mode, source_task_id, version_no
  ) values (
    src.owner, src.source_url, src.title, src.source_tags, src.play_count, src.author, 'pending',
    src.content_category, src.narration_mode, 'repost_dedup', src.id, src.version_no + 1
  ) returning id into child_id;

  update public.stages set status = 'done', error = null,
    params = params || jsonb_build_object('skipped', true, 'reason', '二次发布沿用首发确认稿')
    where task_id = child_id and kind in ('ingest','transcribe','clean');

  for src_stage in select * from public.stages where task_id = src.id and kind in ('rewrite','image','render') loop
    keys := case src_stage.kind
      when 'rewrite' then array['content_line','rewrite_domain']
      when 'image' then array['content_line','production_template','template_version','visual_mode','visual_style','visual_preset_id','image_aspect_ratio','image_provider','image_model','grid_resolution','stock_source','stock_visual_policy']
      else array['content_line','production_template','template_version','visual_mode','frame_mode','title_font','title_color','stock_source','footnote','cover_duration'] end;
    select coalesce(jsonb_object_agg(key, value), '{}'::jsonb) into inherited
      from jsonb_each(src_stage.params) where key = any(keys);
    update public.stages set params = params || inherited
      where task_id = child_id and kind = src_stage.kind;
  end loop;
  return child_id;
end;
$$;

revoke execute on function public.create_repost_task(uuid) from public;

-- Restore legacy queued V2 tasks without reopening user-cancelled or failed tasks.
update public.stages s set status = 'done', error = null,
  params = s.params || jsonb_build_object('skipped', true, 'reason', '二次发布沿用首发确认稿')
from public.tasks t
where s.task_id = t.id and t.rewrite_mode = 'repost_dedup'
  and t.status in ('pending','processing','needs_review')
  and s.kind in ('ingest','transcribe','clean') and s.status = 'cancelled';

-- Complete template snapshots for old V2 tasks before they can resume.
update public.stages target set params = inherited.params || target.params
from public.tasks task
join public.stages source on source.task_id = task.source_task_id
cross join lateral (
  select coalesce(jsonb_object_agg(key, value), '{}'::jsonb) as params
  from jsonb_each(source.params)
  where key = any(case source.kind
    when 'rewrite' then array['content_line','rewrite_domain']
    when 'image' then array['content_line','production_template','template_version','visual_mode','visual_style','visual_preset_id','image_aspect_ratio','image_provider','image_model','grid_resolution','stock_source','stock_visual_policy']
    else array['content_line','production_template','template_version','visual_mode','frame_mode','title_font','title_color','stock_source','footnote','cover_duration'] end)
) inherited
where target.task_id = task.id and target.kind = source.kind
  and target.kind in ('rewrite','image','render')
  and task.rewrite_mode = 'repost_dedup' and task.status in ('pending','processing','needs_review')
  and target.status in ('pending','needs_review')
  and inherited.params <> '{}'::jsonb
  and target.params is distinct from inherited.params || target.params;

grant execute on function public.create_repost_task(uuid) to authenticated;
