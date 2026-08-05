alter table public.tasks
  add column if not exists content_category text not null default 'health';

alter table public.tasks
  drop constraint if exists tasks_content_category_check;

alter table public.tasks
  add constraint tasks_content_category_check
  check (content_category in ('health', 'social_science', 'education'));
