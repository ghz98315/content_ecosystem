-- Keep the production constraint aligned with the content-production preset UI.
alter table public.tasks
  drop constraint if exists tasks_bgm_volume_check;

alter table public.tasks
  add constraint tasks_bgm_volume_check
  check (bgm_volume >= 0.02 and bgm_volume <= 0.30);
