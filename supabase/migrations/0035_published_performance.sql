-- 发布表现独立于采集源数据与 15 天媒体清理，长期保留用于选题分析。
create table if not exists public.published_posts (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null references auth.users(id) on delete cascade,
  task_id uuid not null references public.tasks(id) on delete cascade,
  platform text not null check (platform in ('douyin','kuaishou','xiaohongshu','shipinhao','bilibili','other')),
  title text not null default '',
  post_url text,
  published_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_published_posts_owner_date on public.published_posts(owner, published_at desc);
create index if not exists idx_published_posts_task on public.published_posts(task_id);
create table if not exists public.published_post_metrics (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.published_posts(id) on delete cascade,
  recorded_at timestamptz not null default now(),
  views bigint not null default 0 check (views >= 0),
  likes bigint not null default 0 check (likes >= 0),
  comments bigint not null default 0 check (comments >= 0),
  shares bigint not null default 0 check (shares >= 0),
  saves bigint not null default 0 check (saves >= 0),
  follows bigint not null default 0 check (follows >= 0),
  notes text not null default ''
);
create index if not exists idx_published_metrics_latest on public.published_post_metrics(post_id, recorded_at desc);
drop trigger if exists trg_touch_published_posts on public.published_posts;
create trigger trg_touch_published_posts before update on public.published_posts
  for each row execute function public.touch_updated_at();
alter table public.published_posts enable row level security;
alter table public.published_post_metrics enable row level security;
create policy published_posts_owner_select on public.published_posts for select to authenticated
  using (owner = auth.uid());
create policy published_posts_owner_insert on public.published_posts for insert to authenticated
  with check (owner = auth.uid() and exists (select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()));
create policy published_posts_owner_update on public.published_posts for update to authenticated
  using (owner = auth.uid())
  with check (owner = auth.uid() and exists (select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()));
create policy published_posts_owner_delete on public.published_posts for delete to authenticated
  using (owner = auth.uid());
create policy published_metrics_owner_select on public.published_post_metrics for select to authenticated
  using (exists (select 1 from public.published_posts p where p.id = post_id and p.owner = auth.uid()));
create policy published_metrics_owner_insert on public.published_post_metrics for insert to authenticated
  with check (exists (select 1 from public.published_posts p where p.id = post_id and p.owner = auth.uid()));
create policy published_metrics_owner_delete on public.published_post_metrics for delete to authenticated
  using (exists (select 1 from public.published_posts p where p.id = post_id and p.owner = auth.uid()));
