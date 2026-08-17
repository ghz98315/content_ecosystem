alter table public.tasks
  add column if not exists bgm_path text,
  add column if not exists bgm_volume numeric not null default 0.08,
  add column if not exists narration_volume numeric not null default 1.0,
  add column if not exists bgm_authorization_confirmed boolean not null default false;

alter table public.tasks
  drop constraint if exists tasks_bgm_volume_check;
alter table public.tasks
  add constraint tasks_bgm_volume_check check (bgm_volume >= 0.02 and bgm_volume <= 0.30);

alter table public.tasks
  drop constraint if exists tasks_narration_volume_check;
alter table public.tasks
  add constraint tasks_narration_volume_check check (narration_volume >= 0.50 and narration_volume <= 1.50);
