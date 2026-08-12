-- PostgreSQL resolves the CASE result as text because p_decision is text.
-- Cast it explicitly before assigning to the stage_status enum column.
create or replace function public.review_render_stage(p_stage_id uuid, p_decision text, p_note text default null)
returns public.render_reviews language plpgsql security invoker set search_path = public as $$
declare v_task_id uuid; v_review public.render_reviews;
begin
  if p_decision not in ('approved', 'rejected') then raise exception 'invalid render review decision'; end if;
  select s.task_id into v_task_id from public.stages s join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id and s.kind = 'render' and s.status = 'needs_review' and t.owner = auth.uid() for update of s;
  if v_task_id is null then raise exception 'render stage is no longer awaiting review'; end if;
  insert into public.render_reviews(task_id, stage_id, reviewer, decision, note)
    values (v_task_id, p_stage_id, auth.uid(), p_decision, nullif(btrim(p_note), ''))
    returning * into v_review;
  update public.stages
     set status = (case when p_decision = 'approved' then 'done' else 'pending' end)::public.stage_status,
         error = case when p_decision = 'approved' then null else coalesce(nullif(btrim(p_note), ''), '人工审核要求重新生成') end
   where id = p_stage_id;
  update public.tasks set status = case when p_decision = 'approved' then 'done' else 'processing' end
   where id = v_task_id and status = 'needs_review';
  return v_review;
end;
$$;

grant execute on function public.review_render_stage(uuid, text, text) to authenticated;
