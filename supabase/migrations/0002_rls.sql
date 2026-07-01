-- ============================================================
-- content_ecosystem  M0 RLS
-- 登录用户只能读写自己的数据。
-- worker 用 service_role key 连接，自动绕过 RLS，无需额外策略。
-- ============================================================

alter table public.tasks     enable row level security;
alter table public.stages    enable row level security;
alter table public.artifacts enable row level security;

-- ---------- tasks ----------
drop policy if exists tasks_owner_all on public.tasks;
create policy tasks_owner_all on public.tasks
  for all
  using (owner = auth.uid())
  with check (owner = auth.uid());

-- ---------- stages（通过 task 归属判断）----------
drop policy if exists stages_owner_all on public.stages;
create policy stages_owner_all on public.stages
  for all
  using (exists (
    select 1 from public.tasks t
    where t.id = stages.task_id and t.owner = auth.uid()
  ))
  with check (exists (
    select 1 from public.tasks t
    where t.id = stages.task_id and t.owner = auth.uid()
  ));

-- ---------- artifacts ----------
drop policy if exists artifacts_owner_all on public.artifacts;
create policy artifacts_owner_all on public.artifacts
  for all
  using (exists (
    select 1 from public.tasks t
    where t.id = artifacts.task_id and t.owner = auth.uid()
  ))
  with check (exists (
    select 1 from public.tasks t
    where t.id = artifacts.task_id and t.owner = auth.uid()
  ));

-- ---------- Realtime ----------
-- 让前端能订阅这三张表的变更
alter publication supabase_realtime add table public.tasks;
alter publication supabase_realtime add table public.stages;
alter publication supabase_realtime add table public.artifacts;
