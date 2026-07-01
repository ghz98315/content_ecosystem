-- ============================================================
-- content_ecosystem  M0 schema
-- tasks / stages / artifacts + RLS + 建 task 自动生成 8 个 stage
-- ============================================================

-- 需要 gen_random_uuid()（Supabase 默认已启用 pgcrypto）
create extension if not exists pgcrypto;

-- ---------- 枚举 ----------
-- 8 个阶段类型
do $$ begin
  create type stage_kind as enum
    ('ingest','transcribe','clean','rewrite','tts','image','book','render');
exception when duplicate_object then null; end $$;

-- 阶段状态
do $$ begin
  create type stage_status as enum
    ('pending','processing','done','failed','needs_review');
exception when duplicate_object then null; end $$;

-- ---------- tasks ----------
create table if not exists public.tasks (
  id          uuid primary key default gen_random_uuid(),
  owner       uuid references auth.users(id) on delete cascade,
  source_url  text,
  title       text,
  play_count  bigint,
  author      jsonb,
  status      text not null default 'pending',   -- 总状态汇总
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ---------- stages ----------
create table if not exists public.stages (
  id          uuid primary key default gen_random_uuid(),
  task_id     uuid not null references public.tasks(id) on delete cascade,
  kind        stage_kind not null,
  seq         int not null,                       -- 1..8 顺序
  status      stage_status not null default 'pending',
  params      jsonb not null default '{}'::jsonb, -- 可编辑参数
  input_ref   text,
  output_ref  text,
  error       text,
  updated_at  timestamptz not null default now(),
  unique (task_id, kind)
);
create index if not exists idx_stages_task on public.stages(task_id);
-- worker 认领用：找最靠前的 pending
create index if not exists idx_stages_claim on public.stages(status, seq);

-- ---------- artifacts ----------
create table if not exists public.artifacts (
  id           uuid primary key default gen_random_uuid(),
  task_id      uuid not null references public.tasks(id) on delete cascade,
  stage_kind   stage_kind not null,
  type         text not null,        -- video/transcript/clean/rewrite/audio/image/book/subtitle/final
  storage_path text not null,
  meta         jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);
create index if not exists idx_artifacts_task on public.artifacts(task_id);

-- ---------- 建 task 时自动生成 8 个 stage ----------
create or replace function public.seed_stages()
returns trigger
language plpgsql
as $$
declare
  kinds stage_kind[] := array[
    'ingest','transcribe','clean','rewrite','tts','image','book','render'
  ]::stage_kind[];
  k stage_kind;
  i int := 1;
begin
  foreach k in array kinds loop
    insert into public.stages (task_id, kind, seq) values (new.id, k, i);
    i := i + 1;
  end loop;
  return new;
end $$;

drop trigger if exists trg_seed_stages on public.tasks;
create trigger trg_seed_stages
  after insert on public.tasks
  for each row execute function public.seed_stages();

-- ---------- updated_at 自动维护 ----------
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;

drop trigger if exists trg_touch_tasks on public.tasks;
create trigger trg_touch_tasks before update on public.tasks
  for each row execute function public.touch_updated_at();

drop trigger if exists trg_touch_stages on public.stages;
create trigger trg_touch_stages before update on public.stages
  for each row execute function public.touch_updated_at();
