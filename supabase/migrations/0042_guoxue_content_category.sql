-- A new task can identify its copy/compliance domain independently of legacy
-- guoxue tasks that were historically stored as health. Existing rows stay put.
alter table public.tasks
  drop constraint if exists tasks_content_category_check;

alter table public.tasks
  add constraint tasks_content_category_check
  check (content_category in ('guoxue', 'health', 'social_science', 'education'));
