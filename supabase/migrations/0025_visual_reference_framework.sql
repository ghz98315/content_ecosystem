-- Shared visual-reference framework. Existing image-stage params remain valid.
create table if not exists public.visual_presets (
  id text primary key,
  category text not null,
  display_name text not null,
  generation_mode text not null default 'prompt' check (generation_mode in ('prompt', 'reference_image', 'hybrid')),
  visual_style text not null,
  prompt_direction text not null default '',
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.visual_reference_assets (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null references auth.users(id) on delete cascade,
  scope text not null default 'task' check (scope in ('task', 'category', 'global')),
  category text,
  display_name text not null,
  asset_kind text not null check (asset_kind in ('style', 'character', 'scene', 'cover')),
  storage_path text not null,
  reference_notes text not null default '',
  authorization_confirmed boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.task_visual_references (
  task_id uuid not null references public.tasks(id) on delete cascade,
  asset_id uuid not null references public.visual_reference_assets(id) on delete cascade,
  purpose text not null check (purpose in ('style', 'character', 'scene', 'cover')),
  strength text not null default 'medium' check (strength in ('low', 'medium', 'high')),
  sort_order integer not null default 0,
  primary key (task_id, asset_id, purpose)
);

alter table public.visual_presets enable row level security;
alter table public.visual_reference_assets enable row level security;
alter table public.task_visual_references enable row level security;

create policy "read enabled visual presets" on public.visual_presets for select using (enabled);
create policy "owners manage visual reference assets" on public.visual_reference_assets for all using (owner = auth.uid()) with check (owner = auth.uid());
create policy "owners manage task visual references" on public.task_visual_references for all using (
  exists (select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid())
) with check (
  exists (select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid())
);

insert into public.visual_presets (id, category, display_name, generation_mode, visual_style, prompt_direction)
values
  ('health-warm-editorial', 'health', '温暖生活叙事', 'prompt', 'warm_editorial', '明亮、温润的日常生活画面，人物不指向真实身份'),
  ('history-documentary', 'social_science', '史料感人物叙事', 'hybrid', 'documentary', '人物、服饰、器物与时代背景须保持一致；未绑定人物素材时只使用描述性提示词'),
  ('education-clean-modern', 'education', '现代商业阅读', 'prompt', 'clean_modern', '清晰、克制、可信赖的现代工作与阅读场景')
on conflict (id) do update set
  display_name = excluded.display_name,
  generation_mode = excluded.generation_mode,
  visual_style = excluded.visual_style,
  prompt_direction = excluded.prompt_direction,
  enabled = true,
  updated_at = now();
