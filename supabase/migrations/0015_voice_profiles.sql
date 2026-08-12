create table if not exists public.voice_profiles (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null references auth.users(id) on delete cascade,
  display_name text not null check (char_length(btrim(display_name)) between 1 and 80),
  provider text not null check (provider in ('edge', 'cosyvoice2')),
  voice_id text not null check (char_length(btrim(voice_id)) between 1 and 160),
  model text,
  sample_path text,
  authorization_confirmed boolean not null default false,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_voice_profiles_owner_enabled on public.voice_profiles(owner, enabled, updated_at desc);
alter table public.voice_profiles enable row level security;
drop policy if exists "owners manage voice profiles" on public.voice_profiles;
create policy "owners manage voice profiles" on public.voice_profiles for all using (owner = auth.uid()) with check (owner = auth.uid());

create or replace function public.toggle_voice_profile(p_id uuid, p_enabled boolean)
returns public.voice_profiles language plpgsql security invoker set search_path = public as $$
declare v_profile public.voice_profiles;
begin
  update public.voice_profiles set enabled = p_enabled, updated_at = now()
   where id = p_id and owner = auth.uid() returning * into v_profile;
  if v_profile.id is null then raise exception 'voice profile not found or not owned by current user'; end if;
  return v_profile;
end;
$$;
grant execute on function public.toggle_voice_profile(uuid, boolean) to authenticated;

create or replace function public.delete_voice_profile(p_id uuid)
returns void language plpgsql security invoker set search_path = public as $$
begin
  delete from public.voice_profiles where id = p_id and owner = auth.uid();
  if not found then raise exception 'voice profile not found or not owned by current user'; end if;
end;
$$;
grant execute on function public.delete_voice_profile(uuid) to authenticated;
