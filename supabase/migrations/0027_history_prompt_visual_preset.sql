-- APIMart gpt-image-2 is currently text-to-image only. Keep history tasks
-- explicit about their prompt-based consistency strategy.
update public.visual_presets
set generation_mode = 'prompt',
    visual_style = 'history_heroic',
    prompt_direction = 'Historical character text-to-image: keep facial character, costume, era, and visual style stable; vary only action, scene, camera, and light.',
    updated_at = now()
where id = 'history-documentary';
