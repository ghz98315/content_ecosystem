alter table public.tasks
  add column if not exists tts_voice_profile_id uuid references public.voice_profiles(id) on delete set null,
  add column if not exists tts_provider text,
  add column if not exists tts_voice text,
  add column if not exists tts_voice_label text;

alter table public.tasks
  drop constraint if exists tasks_tts_provider_check;

alter table public.tasks
  add constraint tasks_tts_provider_check
  check (tts_provider is null or tts_provider in ('edge', 'cosyvoice2'));

create index if not exists idx_tasks_tts_voice_profile on public.tasks(tts_voice_profile_id);

create or replace function public.seed_stages()
returns trigger
language plpgsql
as $$
declare
  kinds stage_kind[] := array[
    'ingest','transcribe','clean','rewrite','image','book','tts','render'
  ]::stage_kind[];
  k stage_kind;
  i int := 1;
  initial_status stage_status;
  stage_params jsonb;
begin
  foreach k in array kinds loop
    initial_status := 'pending';
    stage_params := '{}'::jsonb;
    if new.rewrite_mode = 'repost_dedup' and k in ('ingest', 'transcribe', 'clean') then
      initial_status := 'cancelled';
    end if;
    if k = 'rewrite' then
      stage_params := jsonb_build_object(
        'rewrite_mode', new.rewrite_mode,
        'source_task_id', new.source_task_id
      );
    elsif k = 'tts' then
      stage_params := jsonb_strip_nulls(jsonb_build_object(
        'provider', new.tts_provider,
        'voice', new.tts_voice,
        'voice_profile_id', new.tts_voice_profile_id,
        'voice_label', new.tts_voice_label
      ));
    end if;
    insert into public.stages (task_id, kind, seq, status, params)
      values (new.id, k, i, initial_status, stage_params);
    i := i + 1;
  end loop;
  return new;
end $$;
