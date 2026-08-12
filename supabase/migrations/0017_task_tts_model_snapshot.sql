alter table public.tasks
  add column if not exists tts_model text;

create or replace function public.seed_stages()
returns trigger
language plpgsql
as $$
declare
  kinds stage_kind[] := array['ingest','transcribe','clean','rewrite','image','book','tts','render']::stage_kind[];
  k stage_kind;
  i int := 1;
  initial_status stage_status;
  stage_params jsonb;
begin
  foreach k in array kinds loop
    initial_status := 'pending';
    stage_params := '{}'::jsonb;
    if new.rewrite_mode = 'repost_dedup' and k in ('ingest', 'transcribe', 'clean') then initial_status := 'cancelled'; end if;
    if k = 'rewrite' then
      stage_params := jsonb_build_object('rewrite_mode', new.rewrite_mode, 'source_task_id', new.source_task_id);
    elsif k = 'tts' then
      stage_params := jsonb_strip_nulls(jsonb_build_object('provider', new.tts_provider, 'model', new.tts_model, 'voice', new.tts_voice, 'voice_profile_id', new.tts_voice_profile_id, 'voice_label', new.tts_voice_label));
    end if;
    insert into public.stages (task_id, kind, seq, status, params) values (new.id, k, i, initial_status, stage_params);
    i := i + 1;
  end loop;
  return new;
end $$;
