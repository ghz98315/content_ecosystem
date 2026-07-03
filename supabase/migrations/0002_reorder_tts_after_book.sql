-- 调整阶段顺序：tts 移至 book 之后（CTA 需要书籍信息）
-- 新顺序：ingest(1) transcribe(2) clean(3) rewrite(4) image(5) book(6) tts(7) render(8)
-- 注意：此迁移只影响新建任务；已有任务保持原始 seq 不变。

create or replace function public.seed_stages()
returns trigger
language plpgsql
as $$
declare
  kinds stage_kind[] := array[
    'ingest','transcribe','clean','rewrite','image','book','tts','render'
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
