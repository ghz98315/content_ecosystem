-- New scene tasks opt in; existing task snapshots are untouched.
alter table public.tasks drop constraint if exists tasks_content_category_check;
alter table public.tasks add constraint tasks_content_category_check
  check (content_category in ('guoxue','health','social_science','education','scene'));
