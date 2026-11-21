-- New tasks created outside the Web also receive the same background music default.
-- Existing tasks keep their saved mix level.
alter table public.tasks alter column bgm_volume set default 0.20;
