-- Auto-complete validated external narration in the existing fenced transaction.
-- Keeps the existing service_role-only RPC access; no new client permissions.
create or replace function public.finish_external_narration(
  p_stage_id uuid,p_job text,p_state text,p_review jsonb default '{}',p_audio text default null,p_subtitle text default null
) returns boolean language plpgsql security definer set search_path=public as $$
declare s public.stages; n public.external_narrations; v_task uuid; v_text text; v_changed boolean;
begin
  select task_id into v_task from public.stages where id=p_stage_id;
  perform 1 from public.tasks where id=v_task for update;
  if exists(select 1 from public.tasks where id=v_task and status='cancelled') then return false; end if;
  perform 1 from public.stages where task_id=v_task order by seq for update;
  select * into s from public.stages where id=p_stage_id and kind='tts' and params->>'audio_source'='external';
  if s.id is null or s.status<>'processing' or s.params->>'external_job' is distinct from p_job then return false; end if;
  if p_state not in ('approved','review','failed','waiting') then raise exception 'invalid completion state'; end if;
  select * into n from public.external_narrations where id=(s.params->>'external_id')::uuid and stage_id=s.id for update;
  if p_state='approved' then
    if n.id is null or p_audio is null or p_subtitle is null
      or coalesce((p_review->>'alignment_ready')::boolean,false) is not true
      or coalesce((p_review->>'auto_processed')::boolean,false) is not true
      or p_review->>'subtitle_text' is distinct from n.subtitle_text then
      raise exception 'auto alignment validation incomplete';
    end if;
    select params->>'external_visual_text' into v_text from public.stages where task_id=v_task and kind='image';
    if v_text is null then select params->>'final_text' into v_text from public.stages where task_id=v_task and kind='rewrite'; end if;
    v_changed := v_text is distinct from n.subtitle_text;
    update public.external_narrations set state='approved',review=p_review,audio_path=p_audio,subtitle_path=p_subtitle where id=n.id;
    insert into public.artifacts(task_id,stage_kind,type,storage_path,meta) values
      (v_task,'tts','audio',p_audio,jsonb_build_object('provider','external','external_id',n.id,'subtitle_path',p_subtitle,'duration',p_review->'duration','auto_processed',true)),
      (v_task,'tts','subtitle',p_subtitle,jsonb_build_object('external_id',n.id,'input_format','timeline_v3','auto_processed',true));
    update public.stages set status='done',output_ref=p_audio,error=null,
      params=params||jsonb_build_object('subtitle_path',p_subtitle) where id=s.id;
    update public.stages set params=params||jsonb_build_object('external_visual_text',n.subtitle_text) where task_id=v_task and kind='image';
    if v_changed then
      update public.stages set status='pending',output_ref=null,error=null,
        params=(params - 'image_provider_jobs')||jsonb_build_object('external_visual_text',n.subtitle_text) where task_id=v_task and kind='image';
      update public.image_replacement_requests set invalidated_at=now() where task_id=v_task and invalidated_at is null;
    end if;
    update public.stages set status='pending',output_ref=null,error=null where task_id=v_task and kind='render';
    update public.tasks set status='processing' where id=v_task;
    return true;
  end if;
  if p_state<>'waiting' then
    update public.external_narrations set state=p_state,review=p_review,audio_path=p_audio,subtitle_path=p_subtitle where id=n.id;
  end if;
  update public.stages set status=(case when p_state='failed' then 'failed' else 'needs_review' end)::stage_status,
    output_ref=p_audio,error=case when p_state='waiting' then '等待上传外部配音'
      when p_state='failed' then p_review->>'error' else '配音已对齐，可重新对齐后自动继续' end where id=s.id;
  return true;
end $$;
