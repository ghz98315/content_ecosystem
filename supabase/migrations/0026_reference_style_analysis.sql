-- Preserve machine-readable identity and style analysis beside each reference asset.
alter table public.visual_reference_assets
  add column if not exists identity_profile jsonb not null default '{}'::jsonb,
  add column if not exists style_profile jsonb not null default '{}'::jsonb;
