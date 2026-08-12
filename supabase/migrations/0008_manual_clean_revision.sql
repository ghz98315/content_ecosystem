-- Persist a confirmed human clean-copy revision without overwriting clean.json.

create or replace function public.confirm_clean_revision(
  p_stage_id uuid,
  p_cleaned_text text
)
returns public.stages
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_task_id uuid;
  v_seq int;
  v_stage public.stages;
begin
  if nullif(btrim(p_cleaned_text), '') is null then
    raise exception 'cleaned text must not be empty';
  end if;

  select s.task_id, s.seq
    into v_task_id, v_seq
    from public.stages s
    join public.tasks t on t.id = s.task_id
   where s.id = p_stage_id
     and s.kind = 'clean'
     and s.status = 'done'
     and t.owner = auth.uid()
   for update of s;

  if v_task_id is null then
    raise exception 'clean stage is not complete or not owned by current user';
  end if;

  update public.stages
     set params = params || jsonb_build_object(
       'manual_clean_text', btrim(p_cleaned_text),
       'manual_clean_confirmed', true,
       'manual_clean_updated_at', now()
     )
   where id = p_stage_id
   returning * into v_stage;

  update public.stages
     set status = 'pending',
         error = null,
         output_ref = null,
         params = params - 'chosen_index' - 'final_text' - 'manual_book_name' - 'book_confirmed'
   where task_id = v_task_id
     and seq > v_seq
     and status <> 'cancelled';

  update public.tasks
     set status = 'processing'
   where id = v_task_id;

  return v_stage;
end;
$$;

grant execute on function public.confirm_clean_revision(uuid, text) to authenticated;
