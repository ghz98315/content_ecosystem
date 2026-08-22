-- Historical visual styles are task-selectable and intentionally isolated from health defaults.
insert into public.visual_presets (id, category, display_name, generation_mode, visual_style, prompt_direction)
values
  ('history-ink-scroll', 'social_science', '历史：水墨绢本叙事', 'prompt', 'history_ink_scroll', '泛黄绢本、墨线水墨、低饱和赭石土黄；强调环境、留白、景深和行进方向；中老年审美；无字无水印'),
  ('history-gongbi-cinematic', 'social_science', '历史：古工笔厚涂史诗', 'prompt', 'history_gongbi_cinematic', '中式古工笔与厚涂油画融合、暗金低饱和、烛光或侧光；强调人物面部、服饰、道具和时代环境；无字无水印'),
  ('history-heroic', 'social_science', '历史：英雄叙事', 'prompt', 'history_heroic', '保留既有历史英雄叙事风格；固定人物气质、服饰、时代与画风；仅变化动作、场景、镜头与光线；无字无水印')
on conflict (id) do update set
  display_name = excluded.display_name,
  category = excluded.category,
  generation_mode = excluded.generation_mode,
  visual_style = excluded.visual_style,
  prompt_direction = excluded.prompt_direction;
