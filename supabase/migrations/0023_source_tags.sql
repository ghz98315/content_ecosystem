-- Keep source titles and topic tags structurally separate for topic selection.

alter table public.tasks
  add column if not exists source_tags text[] not null default '{}'::text[];

create index if not exists idx_tasks_source_tags_gin
  on public.tasks using gin (source_tags);

-- Backfill descriptions produced by the Douyin resolver, where underscores
-- separate punctuation and `_#` separates hashtags.
with parsed as (
  select t.id,
         btrim(regexp_replace(split_part(t.title, '#', 1), '_+', ' ', 'g'), ' ') as clean_title,
         array(
           select trim(both '_' from trim(both '#' from part))
             from unnest(regexp_split_to_array(substring(t.title from position('#' in t.title)), '_+#')) part
            where nullif(trim(both '_' from trim(both '#' from part)), '') is not null
         ) as tags
    from public.tasks t
   where cardinality(t.source_tags) = 0
     and t.title like '%#%'
)
update public.tasks t
   set source_tags = parsed.tags,
       title = parsed.clean_title
  from parsed
 where t.id = parsed.id;
