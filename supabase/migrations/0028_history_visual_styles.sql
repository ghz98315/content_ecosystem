-- Historical visual styles are task-selectable and isolated from health defaults.
insert into public.visual_presets (
  id, category, display_name, generation_mode, visual_style, prompt_direction
)
values
  (
    'history-ink-scroll',
    'social_science',
    'History: Ink Scroll Narrative',
    'prompt',
    'history_ink_scroll',
    'Aged silk paper, ink wash, brush contours, restrained ochre and earth-yellow palette, environment-led historical composition, no text or watermark.'
  ),
  (
    'history-gongbi-cinematic',
    'social_science',
    'History: Gongbi Cinematic',
    'prompt',
    'history_gongbi_cinematic',
    'Chinese gongbi contour detail with painterly impasto, subdued antique gold and charcoal palette, candlelight or side light, character-led historical composition, no text or watermark.'
  ),
  (
    'history-heroic',
    'social_science',
    'History: Heroic Narrative',
    'prompt',
    'history_heroic',
    'Existing heroic historical painting direction with stable character identity, costume, era and visual style; no text or watermark.'
  )
on conflict (id) do update set
  category = excluded.category,
  display_name = excluded.display_name,
  generation_mode = excluded.generation_mode,
  visual_style = excluded.visual_style,
  prompt_direction = excluded.prompt_direction,
  enabled = true,
  updated_at = now();
