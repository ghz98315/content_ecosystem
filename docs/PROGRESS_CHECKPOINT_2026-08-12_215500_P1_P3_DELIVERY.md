# P1-P3 Delivery Checkpoint

Updated: 2026-08-12 21:55:00 Asia/Shanghai

## P1 Background Music

- Task-scoped private Storage upload, authorization confirmation, preview, BGM and narration volume settings.
- Render loops BGM to narration duration, applies 0.8 second fades, and mixes it below narration by default.
- No BGM continues through the existing narration-only render path.

## P2 Workflow Templates

- New tasks can select Health, History/Social Science, or Business/Management.
- All templates use the same eight-stage pipeline, with category-specific narrative boundaries, review rules, and visual directions.
- Existing Health tasks remain unchanged.

## P3 Dialogue and WeChat Channels

- Dual dialogue requires a second voice snapshot; reviewed scripts use explicit `主持人：` / `嘉宾：` turns and synthesize each voice separately before timeline composition.
- WeChat Channels links are marked as a distinct source. They require authorized manual audio/video upload, then reuse the existing transcript-to-render pipeline. No unsupported automatic downloader is claimed or installed.

## Required SQL

Execute these in Supabase SQL Editor in order:

1. `supabase/migrations/0019_task_background_music.sql`
2. `supabase/migrations/0020_source_and_dialogue_modes.sql`

## Verification

- `python -m unittest tests.test_video_quality -q`: 71 tests passed.
- `npm.cmd run build`: Next.js production build passed.

## Unified Manual Test

After deployment and Worker restart, create separate isolated tasks for: Health single voice with BGM, History/Social Science, Business/Management, Dual Dialogue with two voices, and WeChat Channels manual upload. Do not run the global worker queue during these tests.
