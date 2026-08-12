alter table public.tasks
  add column if not exists source_platform text not null default 'douyin',
  add column if not exists narration_mode text not null default 'single',
  add column if not exists tts_secondary_voice_profile_id uuid references public.voice_profiles(id) on delete set null,
  add column if not exists tts_secondary_provider text,
  add column if not exists tts_secondary_model text,
  add column if not exists tts_secondary_voice text,
  add column if not exists tts_secondary_voice_label text;

alter table public.tasks drop constraint if exists tasks_source_platform_check;
alter table public.tasks add constraint tasks_source_platform_check check (source_platform in ('douyin', 'wechat_channels', 'manual'));
alter table public.tasks drop constraint if exists tasks_narration_mode_check;
alter table public.tasks add constraint tasks_narration_mode_check check (narration_mode in ('single', 'dual_dialogue'));

create or replace function public.seed_stages()
returns trigger language plpgsql as $$
declare kinds stage_kind[] := array['ingest','transcribe','clean','rewrite','image','book','tts','render']::stage_kind[]; k stage_kind; i int := 1; initial_status stage_status; stage_params jsonb;
begin
  foreach k in array kinds loop
    initial_status := 'pending'; stage_params := '{}'::jsonb;
    if new.rewrite_mode = 'repost_dedup' and k in ('ingest', 'transcribe', 'clean') then initial_status := 'cancelled'; end if;
    if k = 'rewrite' then stage_params := jsonb_build_object('rewrite_mode', new.rewrite_mode, 'source_task_id', new.source_task_id, 'narration_mode', new.narration_mode);
    elsif k = 'tts' then stage_params := jsonb_strip_nulls(jsonb_build_object('provider', new.tts_provider, 'model', new.tts_model, 'voice', new.tts_voice, 'voice_profile_id', new.tts_voice_profile_id, 'voice_label', new.tts_voice_label, 'secondary_provider', new.tts_secondary_provider, 'secondary_model', new.tts_secondary_model, 'secondary_voice', new.tts_secondary_voice, 'secondary_voice_profile_id', new.tts_secondary_voice_profile_id, 'secondary_voice_label', new.tts_secondary_voice_label, 'narration_mode', new.narration_mode));
    end if;
    insert into public.stages (task_id, kind, seq, status, params) values (new.id, k, i, initial_status, stage_params); i := i + 1;
  end loop; return new;
end $$;
