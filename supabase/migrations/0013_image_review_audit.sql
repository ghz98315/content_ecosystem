create table if not exists public.image_reviews (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(id) on delete cascade,
  stage_id uuid not null references public.stages(id) on delete cascade,
  image_index integer not null check (image_index >= 0),
  reviewer uuid not null references auth.users(id) on delete cascade,
  decision text not null check (decision in ('approved', 'replace_requested')),
  note text,
  created_at timestamptz not null default now()
);
create index if not exists idx_image_reviews_lookup on public.image_reviews(task_id, image_index, created_at desc);
alter table public.image_reviews enable row level security;
drop policy if exists "owners read image reviews" on public.image_reviews;
create policy "owners read image reviews" on public.image_reviews for select using (exists (select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()));
drop policy if exists "owners create image reviews" on public.image_reviews;
create policy "owners create image reviews" on public.image_reviews for insert with check (reviewer = auth.uid() and exists (select 1 from public.tasks t where t.id = task_id and t.owner = auth.uid()));

create or replace function public.review_image_frame(p_stage_id uuid, p_image_index integer, p_decision text, p_note text default null)
returns public.image_reviews language plpgsql security invoker set search_path = public as $$
declare v_task_id uuid; v_review public.image_reviews;
begin
  if p_image_index < 0 then raise exception 'image index must be non-negative'; end if;
  if p_decision not in ('approved', 'replace_requested') then raise exception 'invalid image review decision'; end if;
  select s.task_id into v_task_id from public.stages s join public.tasks t on t.id = s.task_id where s.id = p_stage_id and s.kind = 'image' and t.owner = auth.uid();
  if v_task_id is null then raise exception 'image stage not found or not owned by current user'; end if;
  insert into public.image_reviews(task_id, stage_id, image_index, reviewer, decision, note) values (v_task_id, p_stage_id, p_image_index, auth.uid(), p_decision, nullif(btrim(p_note), '')) returning * into v_review;
  return v_review;
end;
$$;
grant execute on function public.review_image_frame(uuid, integer, text, text) to authenticated;
