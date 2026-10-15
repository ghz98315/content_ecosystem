-- External narration is an alternate implementation of the existing TTS stage.
alter table public.tasks add column if not exists tts_source text not null default 'automatic'
  check (tts_source in ('automatic', 'external'));

create table if not exists public.external_narrations (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(id) on delete cascade,
  stage_id uuid not null references public.stages(id) on delete cascade,
  state text not null default 'uploading' check (state in ('uploading','queued','review','approved','failed')),
  original_path text not null,
  original_name text not null,
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 209715200),
  script_text text not null,
  subtitle_text text not null,
  audio_path text,
  subtitle_path text,
  review jsonb not null default '{}',
  created_at timestamptz not null default now()
);
alter table public.external_narrations enable row level security;
create policy external_narration_read on public.external_narrations for select to authenticated
  using (exists(select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()));
grant select on public.external_narrations to authenticated;
grant all on public.external_narrations to service_role;

create or replace function public.seed_narration_source() returns trigger
language plpgsql set search_path = public as $$
begin
  if new.kind = 'tts' then
    new.params := new.params || jsonb_build_object('audio_source',
      (select tts_source from public.tasks where id = new.task_id));
  end if;
  return new;
end $$;
create trigger seed_narration_source before insert on public.stages
for each row execute function public.seed_narration_source();

-- Owner-facing mutations share one task lock. Disallow changes while any
-- downstream handler owns a lease, preventing stale paid/render work publishing.
create or replace function public.narration_action(
  p_stage_id uuid, p_action text, p_data jsonb default '{}'
) returns jsonb language plpgsql security definer set search_path = public as $$
declare
  s public.stages; t public.tasks; n public.external_narrations;
  v_id uuid; v_text text; v_ext text; v_source text; v_changed boolean;
begin
  select * into t from public.tasks where id = (select task_id from public.stages where id = p_stage_id)
    and owner = auth.uid() for update;
  if t.id is null then raise exception '无权操作该任务'; end if;
  perform 1 from public.stages where task_id = t.id order by seq for update;
  select * into s from public.stages where id = p_stage_id and kind = 'tts';
  if s.id is null or t.status = 'cancelled' then raise exception '任务不可操作'; end if;
  if exists(select 1 from public.stages where task_id = t.id and seq >= 5 and status = 'processing') then
    raise exception '下游正在处理，请结束后重试';
  end if;
  if exists(select 1 from public.image_replacement_requests where task_id=t.id and status='processing' and invalidated_at is null) then
    raise exception '图片正在替换，请结束后重试'; end if;
  if p_action = 'source' then
    v_source := p_data->>'source';
    if v_source not in ('external','automatic') or v_source is null then raise exception '无效配音方式'; end if;
    if coalesce(s.params->>'audio_source', 'automatic') = v_source then return to_jsonb(s); end if;
    update public.tasks set tts_source = v_source, status = 'processing' where id = t.id;
    update public.stages set params = (params - 'external_id' - 'external_job' - 'subtitle_path') ||
      jsonb_build_object('audio_source',v_source), status = 'pending', output_ref = null, error = null where id = s.id;
    if v_source='automatic' then
      update public.stages set status='pending',output_ref=null,error=null,
        params=params - 'external_visual_text' - 'image_provider_jobs'
        where task_id=t.id and kind='image' and params ? 'external_visual_text';
    end if;
    update public.stages set status = 'pending', output_ref = null, error = null where task_id = t.id and kind = 'render';
    return jsonb_build_object('source',v_source);
  end if;
  if not exists(select 1 from public.stages where task_id = t.id and kind = 'rewrite' and status = 'done') then
    raise exception '请先确认并完成改写文案';
  end if;
  if s.params->>'audio_source' is distinct from 'external' then raise exception '请先选择外部配音'; end if;
  if exists(select 1 from public.stages where task_id=t.id and kind='rewrite' and status='processing') then
    raise exception '文案正在更新，请稍后重试';
  end if;
  if p_action = 'prepare' then
    select params->>'final_text' into v_text from public.stages where task_id = t.id and kind = 'rewrite';
    if nullif(btrim(v_text),'') is null then raise exception '确认稿缺失，请重新确认改写稿'; end if;
    v_ext := lower(p_data->>'extension');
    if v_ext not in ('wav','mp3') or v_ext is null then raise exception '仅支持 WAV 或 MP3'; end if;
    v_id := gen_random_uuid();
    insert into public.external_narrations(id,task_id,stage_id,original_path,original_name,size_bytes,script_text,subtitle_text)
    values(v_id,t.id,s.id,t.id::text||'/external/'||v_id::text||'/original.'||v_ext,
      left(p_data->>'name',240),(p_data->>'size')::bigint,v_text,v_text) returning * into n;
    return to_jsonb(n);
  end if;
  select * into n from public.external_narrations where id = (p_data->>'id')::uuid and stage_id = s.id for update;
  if n.id is null then raise exception '配音版本不存在'; end if;
  select params->>'final_text' into v_text from public.stages where task_id=t.id and kind='rewrite';
  if n.script_text is distinct from v_text then raise exception '确认稿已变化，请按新稿上传配音'; end if;
  if p_action = 'submit' then
    if s.params->>'external_id' = n.id::text and n.state <> 'uploading' then return to_jsonb(n); end if;
    if n.state <> 'uploading' then raise exception '此版本已提交，请刷新'; end if;
    if exists(select 1 from public.external_narrations where stage_id=s.id and state<>'uploading' and created_at>n.created_at) then
      raise exception '已有较新的配音版本，请刷新'; end if;
    if not exists(select 1 from storage.objects where bucket_id='artifacts' and name=n.original_path
      and (metadata->>'size')::bigint=n.size_bytes) then raise exception '上传尚未完成或文件大小不符'; end if;
    update public.external_narrations set state='queued' where id=n.id;
    update public.stages set status='pending',output_ref=null,error=null,
      params=(params - 'external_job' - 'subtitle_path') || jsonb_build_object('external_id',n.id) where id=s.id;
  else
    if s.params->>'external_id' is distinct from n.id::text then raise exception '配音版本已变化，请刷新'; end if;
    if p_action = 'realign' then
      v_text := btrim(p_data->>'text');
      if v_text is null or length(v_text) not between 1 and 20000 then raise exception '字幕稿须为 1–20000 字'; end if;
      if n.state not in ('review','failed','approved') then raise exception '配音尚未完成识别'; end if;
      update public.external_narrations set state='queued',subtitle_text=v_text,
        review=(review - 'requested_cues') || case when p_data ? 'cues'
          then jsonb_build_object('requested_cues',p_data->'cues') else '{}'::jsonb end where id=n.id;
      update public.stages set status='pending',output_ref=null,error=null,
        params=params - 'external_job' - 'subtitle_path' where id=s.id;
    elsif p_action = 'approve' then
      if n.state='approved' and s.status='done' then return to_jsonb(n); end if;
      if n.state<>'review' or s.status<>'needs_review' or n.audio_path is null or n.subtitle_path is null then
        raise exception '请先完成配音识别与字幕对齐'; end if;
      if p_data->>'subtitle_path' is distinct from n.subtitle_path then raise exception '字幕版本已变化，请重新核对'; end if;
      -- Edited times were validated by the worker; approval always publishes
      -- exactly the reviewed file, never unvalidated browser JSON.
      if coalesce((n.review->>'alignment_ready')::boolean,false) is not true then
        raise exception '存在无法定位的字幕，请先修正字幕稿并重新对齐'; end if;
      select params->>'external_visual_text' into v_text from public.stages where task_id=t.id and kind='image';
      if v_text is null then
        select params->>'final_text' into v_text from public.stages where task_id=t.id and kind='rewrite';
      end if;
      v_changed := v_text is distinct from n.subtitle_text;
      update public.external_narrations set state='approved' where id=n.id;
      insert into public.artifacts(task_id,stage_kind,type,storage_path,meta) values
        (t.id,'tts','audio',n.audio_path,jsonb_build_object('provider','external','external_id',n.id,'subtitle_path',n.subtitle_path,'duration',n.review->'duration')),
        (t.id,'tts','subtitle',n.subtitle_path,jsonb_build_object('external_id',n.id,'input_format','timeline_v3'));
      update public.stages set status='done',output_ref=n.audio_path,error=null,
        params=params||jsonb_build_object('subtitle_path',n.subtitle_path) where id=s.id;
      update public.stages set params=params||jsonb_build_object('external_visual_text',n.subtitle_text)
        where task_id=t.id and kind='image';
      if v_changed then
        update public.stages set status='pending',output_ref=null,error=null,
          params=(params - 'image_provider_jobs')||jsonb_build_object('external_visual_text',n.subtitle_text)
          where task_id=t.id and kind='image';
        update public.image_replacement_requests set invalidated_at=now() where task_id=t.id and invalidated_at is null;
      end if;
    else raise exception '未知操作'; end if;
  end if;
  update public.stages set status='pending',output_ref=null,error=null where task_id=t.id and kind='render';
  update public.tasks set status='processing' where id=t.id;
  return jsonb_build_object('id',n.id,'ok',true);
end $$;
revoke all on function public.narration_action(uuid,text,jsonb) from public, anon;
grant execute on function public.narration_action(uuid,text,jsonb) to authenticated;

create or replace function public.claim_media_stage(p_stage_id uuid) returns setof public.stages
language plpgsql security definer set search_path=public as $$
declare s public.stages; a public.stages; v_task uuid;
begin
  select id into v_task from public.tasks where id=(select task_id from public.stages where id=p_stage_id)
    and status in ('pending','processing') for update;
  if v_task is null then return; end if;
  perform 1 from public.stages where task_id=v_task order by seq for update;
  select * into s from public.stages where id=p_stage_id;
  select * into a from public.stages where task_id=v_task and kind='tts';
  if s.status<>'pending' or s.kind not in ('tts','image','render') then return; end if;
  if exists(select 1 from public.image_replacement_requests where task_id=v_task
    and status='processing' and invalidated_at is null) then return; end if;
  if exists(select 1 from public.stages where task_id=v_task
    and seq <= (case when s.kind='tts' then 4 else s.seq-1 end) and status<>'done') then return; end if;
  if s.kind in ('image','render') and a.params->>'audio_source'='external' and a.status<>'done' then return; end if;
  return query update public.stages set status='processing',error=null,
    params=case when kind='tts' and params->>'audio_source'='external'
      then params||jsonb_build_object('external_job',gen_random_uuid()) else params end
    where id=p_stage_id returning *;
end $$;
revoke all on function public.claim_media_stage(uuid) from public,anon,authenticated;
grant execute on function public.claim_media_stage(uuid) to service_role;

-- Replacement claims share the task lock with narration review and reruns.
create or replace function public.claim_image_replacement(p_request_id uuid)
returns setof public.image_replacement_requests
language plpgsql security definer set search_path=public as $$
declare v_task uuid;
begin
  select id into v_task from public.tasks
    where id=(select task_id from public.image_replacement_requests where id=p_request_id)
      and status<>'cancelled' for update;
  if v_task is null then return; end if;
  perform 1 from public.stages where task_id=v_task order by seq for update;
  if exists(select 1 from public.stages where task_id=v_task and status='processing') then return; end if;
  if not exists(select 1 from public.stages where task_id=v_task and kind='image' and status in ('done','needs_review')) then return; end if;
  if exists(select 1 from public.stages where task_id=v_task and kind='tts'
    and params->>'audio_source'='external' and status<>'done') then return; end if;
  return query update public.image_replacement_requests set status='processing',error=null
    where id=p_request_id and status='pending' and invalidated_at is null returning *;
end $$;
revoke all on function public.claim_image_replacement(uuid) from public,anon,authenticated;
grant execute on function public.claim_image_replacement(uuid) to service_role;

create or replace function public.finish_external_narration(
  p_stage_id uuid,p_job text,p_state text,p_review jsonb default '{}',p_audio text default null,p_subtitle text default null
) returns boolean language plpgsql security definer set search_path=public as $$
declare s public.stages;
begin
  select * into s from public.stages where id=p_stage_id and kind='tts' and params->>'audio_source'='external' for update;
  if s.id is null or s.status<>'processing' or s.params->>'external_job' is distinct from p_job then return false; end if;
  if exists(select 1 from public.tasks where id=s.task_id and status='cancelled') then return false; end if;
  if p_state not in ('review','failed','waiting') then raise exception 'invalid completion state'; end if;
  if p_state<>'waiting' then
    update public.external_narrations set state=p_state,review=p_review,audio_path=p_audio,subtitle_path=p_subtitle
      where id=(s.params->>'external_id')::uuid and stage_id=s.id;
  end if;
  update public.stages set status=(case when p_state='failed' then 'failed' else 'needs_review' end)::stage_status,
    output_ref=p_audio,error=case when p_state='waiting' then '等待上传外部配音'
      when p_state='failed' then p_review->>'error' else '请核对朗读差异与字幕时间，再确认继续生图' end
    where id=s.id;
  return true;
end $$;
revoke all on function public.finish_external_narration(uuid,text,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.finish_external_narration(uuid,text,text,jsonb,text,text) to service_role;

-- A new rewrite confirmation/rerun makes an old recording approval stale.
-- This does not change rewrite content, candidate selection or confirmation.
create or replace function public.invalidate_external_on_rewrite() returns trigger
language plpgsql set search_path=public as $$
begin
  if new.kind='rewrite' and new.status='pending' and old.status is distinct from new.status then
    update public.stages set status='pending',output_ref=null,error=null,
      params=params - 'external_id' - 'external_job' - 'subtitle_path'
      where task_id=new.task_id and kind='tts' and params->>'audio_source'='external';
  end if;
  return new;
end $$;
create trigger invalidate_external_on_rewrite after update of status on public.stages
for each row execute function public.invalidate_external_on_rewrite();

-- Keep external audio when rerunning images. Reprocessing external audio only
-- invalidates rendering; a new manuscript explicitly invalidates its approval.
create or replace function public.rerun_stage(p_stage_id uuid) returns setof public.stages
language plpgsql security invoker set search_path=public as $$
declare s public.stages; v_external boolean;
begin
  perform 1 from public.tasks where id=(select task_id from public.stages where id=p_stage_id)
    and owner=auth.uid() for update;
  if not found then raise exception '无权操作该任务'; end if;
  select * into s from public.stages where id=p_stage_id;
  perform 1 from public.stages where task_id=s.task_id order by seq for update;
  if exists(select 1 from public.stages where task_id=s.task_id and status='processing') then
    raise exception '任务正在处理，请稍后重跑'; end if;
  if exists(select 1 from public.image_replacement_requests where task_id=s.task_id
    and status='processing' and invalidated_at is null) then raise exception '图片正在替换，请稍后重试'; end if;
  select params->>'audio_source'='external' into v_external from public.stages where task_id=s.task_id and kind='tts';
  update public.stages set status='pending',output_ref=null,error=null,
    params=(case when kind='image' then params - 'image_provider_jobs' else params end)
      - 'chosen_index' - 'final_text' - 'manual_book_name' - 'book_confirmed'
      - 'cover_title' - 'cover_subtitle' - 'cover_confirmed'
    where task_id=s.task_id and status<>'cancelled' and (
      (coalesce(v_external,false) and s.kind='tts' and kind in ('tts','render')) or
      (coalesce(v_external,false) and s.kind='image' and kind in ('image','render')) or
      ((not coalesce(v_external,false) or s.kind not in ('tts','image')) and seq>=s.seq)
    );
  update public.tasks set status='processing' where id=s.task_id;
  return query select * from public.stages where task_id=s.task_id order by seq;
end $$;
grant execute on function public.rerun_stage(uuid) to authenticated;

create or replace function public.regenerate_image_stage(p_stage_id uuid) returns setof public.stages
language plpgsql security definer set search_path=public as $$
declare s public.stages; v_external boolean;
begin
  perform 1 from public.tasks where id=(select task_id from public.stages where id=p_stage_id)
    and owner=auth.uid() for update;
  if not found then raise exception '无权操作该任务'; end if;
  perform 1 from public.stages where task_id=(select task_id from public.stages where id=p_stage_id) order by seq for update;
  select * into s from public.stages where id=p_stage_id and kind='image';
  if s.id is null then raise exception '图片阶段不存在'; end if;
  if exists(select 1 from public.stages where task_id=s.task_id and status='processing') then
    raise exception '任务正在处理，请稍后重试'; end if;
  if exists(select 1 from public.image_replacement_requests where task_id=s.task_id
    and status='processing' and invalidated_at is null) then raise exception '图片正在替换，请稍后重试'; end if;
  select params->>'audio_source'='external' into v_external from public.stages where task_id=s.task_id and kind='tts';
  delete from public.artifacts where task_id=s.task_id and stage_kind in ('image','render');
  update public.image_replacement_requests set invalidated_at=now() where task_id=s.task_id and invalidated_at is null;
  update public.stages set status='pending',error=null,output_ref=null,
    params=case when kind='image' then (params - 'image_provider_jobs') || jsonb_build_object('generation_id',gen_random_uuid()) else params end
    where task_id=s.task_id and status<>'cancelled'
      and ((coalesce(v_external,false) and kind in ('image','render')) or (not coalesce(v_external,false) and seq>=s.seq));
  update public.tasks set status='processing' where id=s.task_id;
  return query select * from public.stages where task_id=s.task_id order by seq;
end $$;
revoke all on function public.regenerate_image_stage(uuid) from public,anon;
grant execute on function public.regenerate_image_stage(uuid) to authenticated;
