from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import db
import main as worker_main
from compliance import check_text, scan_text
from stages.clean import _clean_output_issue, _extract_opening_hook, _hook_preservation_issue, _summarize_changes
from prompt_profiles import (
    derive_keyword,
    load_compliance_rules,
    load_prompt,
    normalize_category,
    protected_terms,
    rewrite_prompt_kind,
)
from resolvers.self_resolver import select_hot_comments
from stages.image import (
    _build_grid_prompt,
    _grid_bounds,
    _split_grid,
    _split_storyboard,
    _validate_grid_source,
    _visual_scene,
)
from stages.ingest import _is_wechat_channels_url, _requires_manual_upload
from stages.image import _apimart_result_url
from quality import EXPECTED_STAGES, evaluate_render_quality
from stages.render import (
    _allocate_durations,
    _build_timeline,
    _concat_clips_exact,
    _compose_with_dissolve,
    _make_cover_clip,
    _make_image_clip,
    _timeline_clip_durations,
    _validate_timeline,
    _video_duration,
    H,
    W,
    TRANSITION_DUR,
    ZOOM_AMOUNT,
    ZOOM_OVERSAMPLE,
    COVER_FRAMES,
    INTRO_DUR,
    _disclaimer_text,
    _disclaimer_fill,
    DISCLAIMER_FONT_SIZE,
    DISCLAIMER_GAP_LINES,
    DISCLAIMER_OPACITY,
    RenderTimeout,
    _run_ffmpeg,
    _audio_mix_filter,
)
from stages.rewrite import _candidate_issues, _parse_candidates, _rewrite_structure
from stages.tts import _build_subtitle_cues, _clean_tts_text, _dialogue_turns, _split_tts_segments, _synthesize, _synthesize_detailed
from tts_compare import generate_comparison
from tts_providers import get_tts_provider
from narration import (
    has_disallowed_subtitle_punctuation,
    normalize_tts_numbers,
    pause_after_text,
    split_semantic_units,
    strip_subtitle_punctuation,
)


class RewriteQualityTests(unittest.TestCase):
    def test_structured_single_draft_is_complete(self):
        source = "这是原文内容。" * 20
        text = "这为原文内容。" * 20
        raw = json.dumps({"text": text}, ensure_ascii=False)
        candidates = _parse_candidates(raw)
        self.assertEqual(1, len(candidates))
        self.assertEqual([], _candidate_issues(candidates, source, "stop"))

    def test_length_finish_is_rejected(self):
        source = "完整原文。" * 20
        candidates = ["完整候选。" * 20]
        self.assertIn("模型输出达到长度上限", _candidate_issues(candidates, source, "length"))

    def test_large_rewrite_is_rejected(self):
        source = "你有没有发现越是着急越容易做错决定？中间讲清楚三个关键方法。最后记住先停下来再行动。" * 3
        rewritten = "今天分享一些完全不同的新鲜故事和人物经历，内容主题已经发生变化，最后也换成另一套营销引导。" * 3
        issues = _candidate_issues([rewritten], source, "stop")
        self.assertIn("改写幅度过大，未保持原文主体", issues)

    def test_rewrite_structure_keeps_model_hook_metadata(self):
        raw = json.dumps({
            "text": "第一段钩子。\n\n第二段展开。",
            "hook": "越省心的做法，可能越伤身体。",
            "hook_strategy": "contrast",
            "paragraphs": ["第一段钩子。", "第二段展开。"],
        }, ensure_ascii=False)
        structure = _rewrite_structure(raw, "第一段钩子。\n\n第二段展开。")
        self.assertEqual("越省心的做法，可能越伤身体。", structure["hook"])
        self.assertEqual("contrast", structure["hook_strategy"])
        self.assertEqual(["第一段钩子。", "第二段展开。"], structure["paragraphs"])

    def test_dialogue_turns_require_two_labelled_speakers(self):
        turns = _dialogue_turns("主持人：这个结论为什么反常识？\n嘉宾：因为它忽略了前提条件。")
        self.assertEqual(["主持人", "嘉宾"], [speaker for speaker, _ in turns])
        with self.assertRaisesRegex(ValueError, "至少需要"):
            _dialogue_turns("主持人：只有一段。")


class CleanSummaryTests(unittest.TestCase):
    def test_clean_summary_lists_deleted_source_spans(self):
        summary = _summarize_changes("栏目口号。正文第一句。关注我获取更多。", "正文第一句。")
        self.assertEqual(19, summary["raw_chars"])
        self.assertEqual(6, summary["clean_chars"])
        self.assertGreater(summary["removed_chars"], 0)
        self.assertTrue(any(item["kind"] == "delete" for item in summary["segments"]))

    def test_clean_output_rejects_abnormal_expansion(self):
        issue = _clean_output_issue("原文" * 100, "清洗后" * 130)
        self.assertIn("异常扩写", issue or "")

    def test_clean_output_allows_small_expansion(self):
        self.assertIsNone(_clean_output_issue("文" * 100, "文" * 105))

    def test_clean_output_rejects_empty_result(self):
        self.assertIn("空正文", _clean_output_issue("原文", "") or "")

    def test_opening_hook_uses_timestamped_first_ten_seconds(self):
        transcript = {"segments": [
            {"start": 0, "text": "开头反常识。"},
            {"start": 8.5, "text": "先别急着相信。"},
            {"start": 10, "text": "这里不应被包含。"},
        ]}
        self.assertEqual("开头反常识。先别急着相信。", _extract_opening_hook(transcript))

    def test_clean_rejects_when_opening_hook_is_missing(self):
        issue = _hook_preservation_issue("先别急着相信，这个习惯可能有问题。", "正文从第二个观点开始。")
        self.assertIn("开头钩子", issue or "")


class PromptProfileTests(unittest.TestCase):
    def test_health_prompts_are_loaded_and_reserved_profiles_are_rejected(self):
        clean_prompt = load_prompt("health", "clean")
        self.assertIn("长度优先不超过原文", clean_prompt)
        self.assertIn("禁止借补标点之名添加", clean_prompt)
        self.assertIn("首次去重", load_prompt("health", "initial_dedup"))
        self.assertIn("二次发布", load_prompt("health", "repost_dedup"))
        self.assertEqual("initial_dedup", rewrite_prompt_kind("initial_dedup"))
        self.assertEqual("repost_dedup", rewrite_prompt_kind("repost_dedup"))
        self.assertIn("首次去重", load_prompt("health", "rewrite"))
        self.assertIn("疗效和安全承诺", load_compliance_rules("health"))
        self.assertEqual("social_science", normalize_category("social_science"))
        self.assertEqual("education", normalize_category("education"))
        self.assertIn("不得杜撰史料", load_prompt("social_science", "initial_dedup"))
        self.assertIn("个性化投资建议", load_prompt("education", "initial_dedup"))
        self.assertIn("伪造史实", load_compliance_rules("social_science"))
        self.assertIn("收益承诺", load_compliance_rules("education"))

    def test_prompt_context_preserves_book_numbers_and_keyword(self):
        source = "《控糖方法》建议连续观察14天，变化约为12%。"
        self.assertEqual("控糖、控糖方法", derive_keyword("#控糖 《控糖方法》", source))
        self.assertEqual(["《控糖方法》", "14", "12%"], protected_terms(source))


class _FakeCompletions:
    def __init__(self, payload: dict):
        self.payload = payload

    def create(self, **_kwargs):
        message = type("Message", (), {"content": json.dumps(self.payload, ensure_ascii=False)})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, payload: dict):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(payload)})()


class ComplianceTests(unittest.TestCase):
    def test_treatment_promise_blocks_final_script(self):
        text = "照着这个方法做，三天见效，而且不用去医院。"
        report = check_text(_FakeClient({"issues": []}), "test", "health", text, {})
        self.assertEqual("blocked", report["status"])
        self.assertTrue(any(item["level"] == "high" for item in report["issues"]))

    def test_contextual_chapter_word_does_not_trigger_absolute_claim(self):
        self.assertEqual([], scan_text("第一章介绍作者的求学经历。"))

    def test_disease_term_requires_review_without_automatic_block(self):
        report = check_text(_FakeClient({"issues": []}), "test", "health", "书中回顾了糖尿病研究的历史。", {})
        self.assertEqual("warning", report["status"])


class StoryboardTests(unittest.TestCase):

    def test_wechat_channels_uses_authorized_manual_upload_path(self):
        self.assertTrue(_requires_manual_upload("wechat_channels"))
        self.assertFalse(_requires_manual_upload("douyin"))
        self.assertTrue(_is_wechat_channels_url("https://weixin.qq.com/sph/AAhaArJeEf"))
        self.assertTrue(_is_wechat_channels_url("https://channels.weixin.qq.com/foo"))

    def test_bgm_mix_keeps_narration_primary_and_uses_fade(self):
        filter_graph = _audio_mix_filter(True, 0.08, 1.0, 42.0)
        self.assertIn("[1:a]volume=1.000", filter_graph)
        self.assertIn("[2:a]volume=0.080", filter_graph)
        self.assertIn("afade=t=in", filter_graph)
        self.assertIn("afade=t=out:st=41.200", filter_graph)
        self.assertIn("amix=inputs=2:duration=first", filter_graph)

    def test_no_bgm_uses_only_narration_filter(self):
        self.assertEqual("[1:a]volume=1.000[narration]", _audio_mix_filter(False, 0.08, 1.0))
    def test_apimart_async_image_result_is_parsed(self):
        self.assertIsNone(_apimart_result_url({"data": {"status": "processing"}}))
        self.assertEqual(
            "https://example.test/image.png",
            _apimart_result_url({
                "data": {
                    "status": "completed",
                    "result": {"images": [{"url": "https://example.test/image.png"}]},
                }
            }),
        )
        self.assertEqual(
            "https://example.test/image.png",
            _apimart_result_url({
                "data": {
                    "status": "completed",
                    "result": {"images": [{"url": ["https://example.test/image.png"]}]},
                }
            }),
        )
        with self.assertRaisesRegex(RuntimeError, "failed"):
            _apimart_result_url({"data": {"status": "failed"}})

    def test_cover_uses_first_image_for_fifteen_frames(self):
        from PIL import Image

        with tempfile.TemporaryDirectory(prefix="render_cover_test_") as tmpdir:
            root = Path(tmpdir)
            image = root / "image.png"
            layout = root / "layout.png"
            output = root / "cover.mp4"
            Image.new("RGB", (800, 600), (220, 30, 30)).save(image)
            Image.new("RGB", (W, H), (0, 0, 0)).save(layout)
            _make_cover_clip(str(image), str(layout), INTRO_DUR, str(output))
            self.assertEqual(15, COVER_FRAMES)
            self.assertAlmostEqual(0.5, INTRO_DUR, places=3)
            self.assertAlmostEqual(INTRO_DUR, _video_duration(str(output)), delta=0.08)

    def test_disclaimer_uses_book_title_and_two_requested_lines(self):
        self.assertEqual(
            "本视频基于《身体重置》及相关研究资料整理，\n仅用于科普分享，不构成任何建议或行为引导。",
            _disclaimer_text("《身体重置》"),
        )
        self.assertEqual(30, DISCLAIMER_FONT_SIZE)
        self.assertEqual(4, DISCLAIMER_GAP_LINES)
        self.assertEqual(0.5, DISCLAIMER_OPACITY)
        self.assertEqual((114, 117, 122), _disclaimer_fill())

    def test_zoom_uses_oversampling_and_visible_eased_motion(self):
        self.assertGreaterEqual(ZOOM_OVERSAMPLE, 4)
        self.assertGreaterEqual(ZOOM_AMOUNT, 0.08)
        self.assertLessEqual(ZOOM_AMOUNT, 0.12)

    def test_grid_bounds_cover_source_without_gaps(self):
        bounds = _grid_bounds(1536)
        self.assertEqual([(0, 512), (512, 1024), (1024, 1536)], bounds)
        self.assertEqual(1536, bounds[-1][1])

    def test_grid_split_produces_exact_4_3_tiles(self):
        from PIL import Image

        source = Image.new("RGB", (1536, 1024), (40, 80, 120))
        buf = io.BytesIO()
        source.save(buf, format="PNG")
        pieces = _split_grid(buf.getvalue(), 9)
        self.assertEqual(9, len(pieces))
        for piece_bytes in pieces:
            with Image.open(io.BytesIO(piece_bytes)) as piece:
                self.assertGreaterEqual(piece.width, 430)
                self.assertGreaterEqual(piece.height, 320)
                self.assertAlmostEqual(4 / 3, piece.width / piece.height, places=2)

    def test_grid_split_removes_provider_separator_lines(self):
        from PIL import Image, ImageDraw

        source = Image.new("RGB", (1536, 1024), (40, 80, 120))
        draw = ImageDraw.Draw(source)
        for x in (512, 1024):
            draw.rectangle((x - 5, 0, x + 5, 1023), fill=(255, 255, 255))
        for y in (341, 683):
            draw.rectangle((0, y - 5, 1535, y + 5), fill=(255, 255, 255))
        buf = io.BytesIO()
        source.save(buf, format="PNG")

        for piece_bytes in _split_grid(buf.getvalue(), 9):
            with Image.open(io.BytesIO(piece_bytes)) as piece:
                self.assertEqual((40, 80, 120), piece.getpixel((0, 0)))
                self.assertEqual((40, 80, 120), piece.getpixel((piece.width - 1, piece.height - 1)))

    def test_grid_prompt_forbids_dividers_and_visible_text(self):
        prompt = _build_grid_prompt(["《身体重置》介绍三个健康方法123"])
        self.assertNotIn("《身体重置》", prompt)
        self.assertIn("不要绘制任何分隔线", prompt)
        self.assertIn("禁止出现中文、外文、字母、数字", prompt)
        safe_prompt = _build_grid_prompt(["糖尿病患者需要治疗、用药并关注症状"])
        self.assertNotIn("糖尿病", safe_prompt)
        self.assertNotIn("治疗", safe_prompt)
        self.assertNotIn("用药", safe_prompt)
        self.assertNotIn("症状", safe_prompt)
        self.assertNotIn("医院", _build_grid_prompt(["医院、器官、伤口和监护仪"])
        )
        self.assertNotIn("器官", _build_grid_prompt(["医院、器官、伤口和监护仪"]))
        self.assertNotIn("伤口", _build_grid_prompt(["医院、器官、伤口和监护仪"]))
        self.assertNotIn("监护仪", _build_grid_prompt(["医院、器官、伤口和监护仪"]))
        self.assertNotIn("带货", safe_prompt)
        self.assertEqual("一本素色无字封面的书介绍三个健康方法", _visual_scene("《身体重置》介绍三个健康方法123"))

    def test_category_visual_directions_are_distinct(self):
        history = _build_grid_prompt(["一段历史叙事"], "social_science")
        business = _build_grid_prompt(["一本经管书的方法"], "education")
        self.assertIn("史料感", history)
        self.assertIn("保证收益", business)

    def test_grid_source_rejects_unexpected_square_canvas(self):
        _validate_grid_source(1536, 1024)
        with self.assertRaisesRegex(ValueError, "已停止切图"):
            _validate_grid_source(1024, 1024)

    def test_render_quality_report_passes_expected_technical_checks(self):
        stages = [
            {"kind": kind, "status": "processing" if kind == "render" else "done"}
            for kind in EXPECTED_STAGES
        ]
        images = [{"path": "a.png"}, {"path": "b.png"}]
        timeline = [
            {"start": 0.0, "end": 2.0, "duration": 2.0},
            {"start": 2.0, "end": 4.0, "duration": 2.0},
        ]
        cues = [
            {"text": "介绍《超越百岁》", "start": 0.0, "end": 2.0},
            {"text": "第二句字幕", "start": 2.0, "end": 4.0},
        ]
        report = evaluate_render_quality(
            media={
                "duration": 4.5, "width": 1080, "height": 1920, "fps": 30.0,
                "has_video": True, "has_audio": True, "file_size": 2_000_000,
            },
            black_segments=[], stage_rows=stages, images=images, cues=cues,
            timeline=timeline, tts_duration=4.0, width=1080, height=1920,
            fps=30, intro_duration=0.5,
        )
        self.assertEqual("passed", report["status"])
        self.assertEqual(0, report["summary"]["failed"])

    def test_render_quality_report_fails_missing_audio(self):
        stages = [
            {"kind": kind, "status": "processing" if kind == "render" else "done"}
            for kind in EXPECTED_STAGES
        ]
        report = evaluate_render_quality(
            media={
                "duration": 2.5, "width": 1080, "height": 1920, "fps": 30.0,
                "has_video": True, "has_audio": False, "file_size": 1_000_000,
            },
            black_segments=[], stage_rows=stages, images=[{"path": "a.png"}],
            cues=[{"text": "字幕正常", "start": 0.0, "end": 2.0}],
            timeline=[{"start": 0.0, "end": 2.0, "duration": 2.0}],
            tts_duration=2.0, width=1080, height=1920, fps=30, intro_duration=0.5,
        )
        self.assertEqual("failed", report["status"])
        self.assertEqual("failed", next(check for check in report["checks"] if check["id"] == "audio")["status"])
    def test_storyboard_targets_eight_seconds(self):
        source = "这是一个用于测试语义分镜的完整文案，它包含多个观点和自然停顿。" * 12
        shots = _split_storyboard(source)
        self.assertTrue(shots)
        self.assertEqual(len(source), sum(shot["char_count"] for shot in shots))
        self.assertTrue(all(32 <= shot["char_count"] <= 42 for shot in shots))
        self.assertTrue(all(shot["motion"] == "zoom_in" for shot in shots))
        self.assertEqual(0, shots[0]["char_start"])
        self.assertEqual(shots[-1]["char_end"], sum(shot["char_count"] for shot in shots))
        self.assertTrue(all(a["char_end"] == b["char_start"] for a, b in zip(shots, shots[1:])))

    def test_tts_numbers_use_natural_reading_rules(self):
        self.assertIn("十天", normalize_tts_numbers("10天"))
        self.assertIn("百分之十", normalize_tts_numbers("10%"))
        self.assertIn("三点零", normalize_tts_numbers("3.0"))
        self.assertIn("二〇二六年", normalize_tts_numbers("2026年"))

    def test_render_duration_compensates_dissolves(self):
        images = [{"char_count": 28}] * 4
        durations = _allocate_durations(images, 32.0)
        final_duration = sum(durations) - TRANSITION_DUR * (len(images) - 1)
        self.assertAlmostEqual(32.0, final_duration, places=2)

    def test_image_clips_and_exact_concat_preserve_timeline_duration(self):
        from PIL import Image

        with tempfile.TemporaryDirectory(prefix="render_duration_test_") as tmpdir:
            root = Path(tmpdir)
            layout = root / "layout.png"
            Image.new("RGB", (W, H), (0, 0, 0)).save(layout)
            clips: list[str] = []
            durations = [1.2, 1.6]
            for index, color in enumerate(((220, 30, 30), (30, 220, 30))):
                image = root / f"image_{index}.png"
                clip = root / f"clip_{index}.mp4"
                Image.new("RGB", (800, 600), color).save(image)
                _make_image_clip(str(image), str(layout), durations[index], str(clip))
                self.assertAlmostEqual(durations[index], _video_duration(str(clip)), delta=0.08)
                clips.append(str(clip))

            output = root / "content.mp4"
            _concat_clips_exact(clips, sum(durations), str(output), tmpdir)
            self.assertAlmostEqual(sum(durations), _video_duration(str(output)), delta=0.08)

    def test_balanced_dissolves_preserve_long_timeline_math(self):
        from PIL import Image

        with tempfile.TemporaryDirectory(prefix="render_dissolve_test_") as tmpdir:
            root = Path(tmpdir)
            layout = root / "layout.png"
            Image.new("RGB", (W, H), (0, 0, 0)).save(layout)
            durations = [0.9, 1.0, 1.1, 0.8]
            clips: list[str] = []
            for index, duration in enumerate(durations):
                image = root / f"image_{index}.png"
                clip = root / f"clip_{index}.mp4"
                Image.new("RGB", (800, 600), (40 + index * 45, 80, 160)).save(image)
                _make_image_clip(str(image), str(layout), duration, str(clip))
                clips.append(str(clip))

            output = root / "dissolved.mp4"
            _compose_with_dissolve(clips, durations, str(output))
            expected = sum(durations) - TRANSITION_DUR * (len(durations) - 1)
            self.assertAlmostEqual(expected, _video_duration(str(output)), delta=0.08)


class TtsInputTests(unittest.TestCase):
    def test_subtitles_keep_words_compounds_titles_and_units_intact(self):
        text = (
            "阿尔茨海默病患者需要长期健康管理和专业人员帮助，"
            "人工智能技术连续观察14天，再参考《身体重置方法》调整方案。"
        )
        units = split_semantic_units(text, max_chars=14)
        screens = [unit["text"] for unit in units]
        for protected in (
            "阿尔茨海默病患者", "健康管理", "专业人员", "人工智能技术",
            "14天", "身体重置方法",
        ):
            self.assertTrue(any(protected in screen for screen in screens), (protected, screens))
        self.assertTrue(all(unit["char_count"] <= 14 for unit in units))
        self.assertEqual(strip_subtitle_punctuation(text), "".join(screens))

    def test_subtitle_word_cuts_do_not_leave_two_character_tail(self):
        text = "保持词语的完整性非常重要，字幕不能把人工智能技术从中间切开。"
        units = split_semantic_units(text, max_chars=14)
        self.assertGreaterEqual(units[-1]["char_count"], 4)
        self.assertTrue(any("人工智能技术" in unit["text"] for unit in units))

    def test_subtitle_rejects_an_unsplittable_overlong_word(self):
        with self.assertRaisesRegex(ValueError, "无法保持完整的词语"):
            split_semantic_units("Supercalifragilistic", max_chars=14)

    def test_subtitles_use_semantic_breaks_without_punctuation(self):
        text = "先把最重要的事情说清楚，然后再解释为什么这样做。最后给出一个可以执行的方法。"
        units = split_semantic_units(text, max_chars=12)
        self.assertEqual(strip_subtitle_punctuation(text), "".join(unit["text"] for unit in units))
        self.assertTrue(all(unit["char_count"] <= 12 for unit in units))
        self.assertTrue(all(strip_subtitle_punctuation(unit["text"]) == unit["text"] for unit in units))
        self.assertTrue(any(unit["pause_after"] > 0 for unit in units))

        anchors = [{
            "text": text,
            "start": 0.2,
            "end": 12.2,
            "char_start": 0,
            "char_end": len(text),
        }]
        cues = _build_subtitle_cues(text, anchors, 12.5)
        self.assertTrue(all(cue["char_count"] <= 12 for cue in cues))
        self.assertTrue(all(a["end"] <= b["start"] for a, b in zip(cues, cues[1:])))
        self.assertEqual(len(text), cues[-1]["char_end"])

    def test_pause_profile_matches_tts_requirement(self):
        self.assertEqual(0.3, pause_after_text("先说清楚，"))
        self.assertEqual(0.8, pause_after_text("一句结束。"))
        self.assertEqual(0.9, pause_after_text("真的吗？"))
        self.assertEqual(0.7, pause_after_text("这里转折——"))
        self.assertEqual(0.9, pause_after_text("稍作停顿……"))
        self.assertEqual(0.45, pause_after_text("分层说明："))

    def test_image_audio_subtitle_timeline_uses_character_boundaries(self):
        cues = [
            {"text": "一" * 12, "char_start": 0, "char_end": 12, "start": 0.0, "end": 3.0},
            {"text": "二" * 12, "char_start": 12, "char_end": 24, "start": 3.0, "end": 6.0},
            {"text": "三" * 12, "char_start": 24, "char_end": 36, "start": 6.0, "end": 9.0},
            {"text": "四" * 12, "char_start": 36, "char_end": 48, "start": 9.0, "end": 12.0},
        ]
        images = [
            {"path": "a.png", "char_start": 0, "char_end": 24, "char_count": 24},
            {"path": "b.png", "char_start": 24, "char_end": 48, "char_count": 24},
        ]
        timeline = _build_timeline(images, cues, 14.0)
        _validate_timeline(timeline, cues, 14.0)
        self.assertEqual([0.0, 6.0], [item["start"] for item in timeline])
        self.assertEqual(14.0, timeline[-1]["end"])
        gross = _timeline_clip_durations(timeline)
        self.assertAlmostEqual(14.0, sum(gross) - TRANSITION_DUR, places=2)

    def test_render_rejects_punctuated_subtitles(self):
        timeline = [{"path": "a.png", "start": 0.0, "end": 2.0, "duration": 2.0}]
        with self.assertRaisesRegex(ValueError, "标点"):
            _validate_timeline(timeline, [{"text": "字幕不要出现。", "start": 0.0, "end": 1.0}], 2.0)

    def test_render_allows_paired_book_title_marks(self):
        timeline = [{"path": "a.png", "start": 0.0, "end": 2.0, "duration": 2.0}]
        cues = [{"text": "把《超越百岁》带回家", "start": 0.0, "end": 2.0}]
        _validate_timeline(timeline, cues, 2.0)
        self.assertFalse(has_disallowed_subtitle_punctuation(cues[0]["text"]))
        self.assertTrue(has_disallowed_subtitle_punctuation("《超越百岁"))
        self.assertTrue(has_disallowed_subtitle_punctuation("《超越百岁》。"))

    def test_render_rejects_overlong_or_reversed_subtitles(self):
        timeline = [{"path": "a.png", "start": 0.0, "end": 2.0, "duration": 2.0}]
        with self.assertRaisesRegex(ValueError, "超过 14"):
            _validate_timeline(timeline, [{"text": "一" * 15, "start": 0.0, "end": 1.0}], 2.0)
        with self.assertRaisesRegex(ValueError, "结束时间早于"):
            _validate_timeline(timeline, [{"text": "字幕正常", "start": 1.0, "end": 0.5}], 2.0)

    def test_only_narration_survives_storyboard_formatting(self):
        formatted = """# 分镜脚本
[00:00-00:08]
画面：老人站在窗边，镜头缓慢推进
旁白：这是第一句正文。
- **文案：这是第二句正文。**
字幕：重复字幕不要朗读
转场：叠化 0.5 秒
---
结尾：这是最后一句。
"""
        self.assertEqual(
            "这是第一句正文。\n这是第二句正文。\n这是最后一句。",
            _clean_tts_text(formatted),
        )

    def test_json_wrapper_and_escaped_ssml_are_removed(self):
        wrapped = json.dumps({"text": "正文一。&lt;break time=\"800ms\"/&gt;正文二。"}, ensure_ascii=False)
        self.assertEqual("正文一。正文二。", _clean_tts_text(wrapped))

    def test_edge_tts_receives_plain_text_not_custom_ssml(self):
        captured: dict[str, str] = {}

        class FakeCommunicate:
            def __init__(self, text, voice, **kwargs):
                captured.update(text=text, voice=voice, boundary=kwargs.get("boundary"))

            async def stream(self):
                yield {"type": "audio", "data": b"audio"}
                yield {"type": "SentenceBoundary", "text": "纯正文。", "offset": 0, "duration": 10_000_000}

        with patch("stages.tts.config.TTS_PROVIDER", "edge"), patch("edge_tts.Communicate", FakeCommunicate):
            audio, segments = asyncio.run(_synthesize("纯正文。", "test-voice"))

        self.assertEqual(b"audio", audio)
        self.assertEqual("纯正文。", captured["text"])
        self.assertNotIn("<speak", captured["text"])
        self.assertEqual("SentenceBoundary", captured["boundary"])
        self.assertEqual(1.0, segments[0]["end"])

    def test_explicit_provider_override_uses_selected_provider(self):
        class FakeProvider:
            def __init__(self):
                self.voice = None

            async def synthesize(self, text, voice):
                self.voice = voice
                return b"audio", [{"text": text, "start": 0.0, "end": 1.0}], 1.0

        fake_provider = FakeProvider()
        with patch("stages.tts.get_tts_provider", return_value=fake_provider) as get_provider:
            audio, segments, batches = asyncio.run(_synthesize_detailed("纯正文。", "snapshot-voice", "edge"))

        self.assertEqual(b"audio", audio)
        self.assertEqual("snapshot-voice", fake_provider.voice)
        self.assertEqual("edge", get_provider.call_args.args[0])
        self.assertEqual(1.0, segments[0]["end"])
        self.assertEqual(1, len(batches))

    def test_long_script_splits_without_changing_a_character(self):
        text = "第一段说明一个观点，并保留正常停顿。第二段继续解释原因，让内容自然推进。" * 12
        parts = _split_tts_segments(text)
        self.assertGreater(len(parts), 1)
        self.assertEqual(text, "".join(parts))
        self.assertTrue(all(1 <= len(part) <= 105 for part in parts))
        self.assertTrue(all(part[-1] in "。！？!?；;\n" for part in parts[:-1]))

    def test_parallel_parts_merge_timestamps_in_original_order(self):
        text = "第一句内容完整结束。" * 20

        async def fake_part(part, _voice):
            return part.encode("utf-8"), [{"text": part, "start": 0.1, "end": 2.0}]

        with patch("stages.tts._synthesize_part", side_effect=fake_part), patch(
            "stages.tts._concat_mp3", return_value=b"merged"
        ) as concat:
            audio, segments = asyncio.run(_synthesize(text, "test-voice"))

        self.assertEqual(b"merged", audio)
        self.assertGreater(len(segments), 1)
        self.assertEqual(text, "".join(segment["text"] for segment in segments))
        self.assertEqual(0.1, segments[0]["start"])
        self.assertEqual(2.1, segments[1]["start"])
        self.assertEqual(len(segments), len(concat.call_args.args[0]))


class NetworkRetryTests(unittest.TestCase):
    def test_tts_provider_defaults_to_edge(self):
        self.assertEqual("EdgeTTSProvider", type(get_tts_provider("edge")).__name__)

    def test_cosyvoice2_provider_is_isolated_and_requires_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "尚未通过生产启用门"):
                get_tts_provider("cosyvoice2")
            provider = get_tts_provider("cosyvoice2", allow_experimental=True)
            self.assertEqual("CosyVoice2Provider", type(provider).__name__)
            with self.assertRaisesRegex(ValueError, "CosyVoice2 未配置"):
                asyncio.run(provider.synthesize("试听文本", "test-voice"))

    def test_cosyvoice2_openai_compatible_audio_response(self):
        captured = {}

        class FakeResponse:
            headers = {"content-type": "audio/mpeg"}
            content = b"cosy-audio"

            @staticmethod
            def raise_for_status():
                return None

        class FakeClient:
            def __init__(self, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, endpoint, **kwargs):
                captured["endpoint"] = endpoint
                captured["request"] = kwargs["json"]
                return FakeResponse()

        env = {
            "COSYVOICE2_BASE_URL": "https://tts.example/v1",
            "COSYVOICE2_MODEL": "cosyvoice-v2",
            "COSYVOICE2_VOICE": "sample-voice",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "tts_providers.httpx.AsyncClient", FakeClient
        ), patch("tts_providers._probe_duration", return_value=2.75):
            audio, boundaries, duration = asyncio.run(
                get_tts_provider(
                    "cosyvoice2", allow_experimental=True
                ).synthesize("试听文本。", "ignored")
            )

        self.assertEqual(b"cosy-audio", audio)
        self.assertEqual(2.75, duration)
        self.assertEqual("试听文本。", boundaries[0]["text"])
        self.assertEqual("https://tts.example/v1/audio/speech", captured["endpoint"])
        self.assertEqual("ignored", captured["request"]["voice"])
        self.assertEqual("mp3", captured["request"]["response_format"])

    def test_cosyvoice2_task_voice_overrides_environment_default(self):
        captured = {}

        class FakeResponse:
            headers = {"content-type": "audio/mpeg"}
            content = b"cosy-audio"
            status_code = 200
            is_error = False
            text = ""
            @staticmethod
            def raise_for_status(): return None

        class FakeClient:
            def __init__(self, **_kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): return None
            async def post(self, _endpoint, **kwargs):
                captured["request"] = kwargs["json"]
                return FakeResponse()

        env = {"DASHSCOPE_API_KEY": "key", "DASHSCOPE_MODEL": "default-model", "DASHSCOPE_VOICE": "environment-voice", "DASHSCOPE_ENDPOINT": "https://tts.example"}
        with patch.dict(os.environ, env, clear=True), patch("tts_providers.httpx.AsyncClient", FakeClient), patch("tts_providers._probe_duration", return_value=1.0):
            asyncio.run(get_tts_provider("cosyvoice2", allow_experimental=True, model="snapshot-model").synthesize("测试", "snapshot-voice"))

        self.assertEqual("snapshot-voice", captured["request"]["input"]["voice"])
        self.assertEqual("snapshot-model", captured["request"]["model"])

    def test_tts_comparison_writes_isolated_audio_and_report(self):
        class FakeProvider:
            def __init__(self, name):
                self.name = name

            async def synthesize(self, text, _voice):
                return self.name.encode(), [{"text": text, "start": 0, "end": 1}], 1.0

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "tts_compare.get_tts_provider",
            side_effect=lambda name, **_kwargs: FakeProvider(name),
        ):
            output_dir = Path(tmpdir) / "comparison"
            report = asyncio.run(generate_comparison(
                "同一段试听文本。", output_dir, "edge-voice", "cosy-voice"
            ))
            saved = json.loads((output_dir / "comparison.json").read_text(encoding="utf-8"))

        self.assertFalse(report["production_audio_replaced"])
        self.assertEqual(["done", "done"], [item["status"] for item in saved["providers"]])
        self.assertEqual("pending", saved["providers"][0]["manual_review"]["voice_quality"])

    def test_render_ffmpeg_timeout_is_converted_to_render_timeout(self):
        import stages.render as render_module

        original_deadline = render_module._ACTIVE_DEADLINE
        try:
            render_module._ACTIVE_DEADLINE = __import__("time").monotonic() + 0.05
            with patch("stages.render.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 0.05)):
                with self.assertRaises(RenderTimeout):
                    _run_ffmpeg(["ffmpeg"], check=True)
        finally:
            render_module._ACTIVE_DEADLINE = original_deadline

    def test_stage_heartbeat_refreshes_processing_lease(self):
        with patch("main.db.touch_stage") as touch:
            heartbeat = worker_main.StageHeartbeat("stage-id", 0.01)
            heartbeat.interval = 0.01
            heartbeat.start()
            import time
            time.sleep(0.04)
            heartbeat.stop()
        self.assertGreaterEqual(touch.call_count, 1)

    def test_worker_startup_recovers_orphaned_stage(self):
        stale = [{"id": "stage-id", "task_id": "task-id", "kind": "image"}]
        with patch("main.db.recover_stale_stages", return_value=stale) as recover:
            self.assertEqual(stale, worker_main.recover_orphaned_stages())
        recover.assert_called_once_with(
            worker_main.config.WORKER_TASK_ID,
            worker_main.config.WORKER_STALE_STAGE_SECONDS,
        )

    def test_failed_stage_marks_task_failed_instead_of_processing(self):
        response = type("Response", (), {"data": {"status": "processing"}})()
        task_query = MagicMock()
        task_query.select.return_value = task_query
        task_query.eq.return_value = task_query
        task_query.single.return_value = task_query
        task_query.execute.return_value = response
        stage_query = MagicMock()
        stage_query.select.return_value = stage_query
        stage_query.eq.return_value = stage_query
        stage_query.execute.return_value = type("Response", (), {"data": [{"status": "failed"}, {"status": "pending"}]})()
        client = MagicMock()
        client.table.side_effect = [task_query, stage_query]

        with patch("main.db.get_client", return_value=client), patch(
            "main.db.set_task_status"
        ) as set_task_status:
            worker_main.maybe_finish_task("failed-task")

        set_task_status.assert_called_once_with("failed-task", "failed")

    def test_cancelled_task_is_not_reactivated_after_stage_finishes(self):
        response = type("Response", (), {"data": {"status": "cancelled"}})()
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.single.return_value = query
        query.execute.return_value = response
        client = MagicMock()
        client.table.return_value = query

        with patch("main.db.get_client", return_value=client), patch(
            "main.db.set_task_status"
        ) as set_task_status:
            worker_main.maybe_finish_task("cancelled-task")

        set_task_status.assert_not_called()

    def test_claim_next_stage_can_be_limited_to_one_task(self):
        sb = MagicMock()
        query = MagicMock()
        sb.table.return_value.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.execute.return_value = type("Response", (), {"data": []})()
        with patch("db.get_client", return_value=sb):
            self.assertIsNone(db.claim_next_stage("target-task"))
        query.eq.assert_any_call("status", "pending")
        query.eq.assert_any_call("task_id", "target-task")

    def test_claim_skips_stage_when_task_is_failed(self):
        pending = {"id": "stage-id", "task_id": "task-id", "seq": 1}
        stages_query = MagicMock()
        stages_query.select.return_value = stages_query
        stages_query.eq.return_value = stages_query
        stages_query.order.return_value = stages_query
        stages_query.execute.return_value = type("Response", (), {"data": [pending]})()
        task_query = MagicMock()
        task_query.select.return_value = task_query
        task_query.eq.return_value = task_query
        task_query.single.return_value = task_query
        task_query.execute.return_value = type("Response", (), {"data": {"status": "failed"}})()
        sb = MagicMock()
        sb.table.side_effect = [stages_query, task_query]

        with patch("db.get_client", return_value=sb):
            self.assertIsNone(db.claim_next_stage())
        self.assert_not_called_with_status_update(stages_query)

    def test_claim_skips_stage_when_a_prior_stage_failed(self):
        pending = {"id": "stage-id", "task_id": "task-id", "seq": 3}
        stages_query = MagicMock()
        stages_query.select.return_value = stages_query
        stages_query.eq.return_value = stages_query
        stages_query.order.return_value = stages_query
        stages_query.execute.return_value = type("Response", (), {"data": [pending]})()
        task_query = MagicMock()
        task_query.select.return_value = task_query
        task_query.eq.return_value = task_query
        task_query.single.return_value = task_query
        task_query.execute.return_value = type("Response", (), {"data": {"status": "processing"}})()
        prior_query = MagicMock()
        prior_query.select.return_value = prior_query
        prior_query.eq.return_value = prior_query
        prior_query.lt.return_value = prior_query
        prior_query.execute.return_value = type("Response", (), {"data": [{"status": "done"}, {"status": "failed"}]})()
        sb = MagicMock()
        sb.table.side_effect = [stages_query, task_query, prior_query]

        with patch("db.get_client", return_value=sb):
            self.assertIsNone(db.claim_next_stage())
        prior_query.execute.assert_called_once()

    @staticmethod
    def assert_not_called_with_status_update(query):
        query.update.assert_not_called()

    def test_ssl_eof_is_transient_and_retried(self):
        calls = 0

        def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
            return "ok"

        with patch("db.reset_client"), patch("db.time.sleep"):
            self.assertEqual("ok", db.retry(flaky, attempts=3))
        self.assertEqual(3, calls)

    def test_reset_client_does_not_close_a_client_used_by_heartbeat(self):
        client = MagicMock()
        db._http_client = client
        db.get_client.cache_clear()

        db.reset_client()

        client.close.assert_not_called()
        self.assertIsNone(db._http_client)

    def test_stale_recovery_rebuilds_query_after_client_reset(self):
        first_query = MagicMock()
        first_query.select.return_value = first_query
        first_query.eq.return_value = first_query
        first_query.lt.return_value = first_query
        first_query.execute.side_effect = httpx.ReadTimeout("timed out")
        first_client = MagicMock()
        first_client.table.return_value = first_query

        second_query = MagicMock()
        second_query.select.return_value = second_query
        second_query.eq.return_value = second_query
        second_query.lt.return_value = second_query
        second_query.execute.return_value = type("Response", (), {"data": []})()
        second_client = MagicMock()
        second_client.table.return_value = second_query

        with patch("db.get_client", side_effect=[first_client, second_client]), patch(
            "db.reset_client"
        ) as reset_client, patch("db.time.sleep"):
            self.assertEqual([], db.recover_stale_stages("task-id"))

        reset_client.assert_called_once()
        self.assertEqual(1, first_query.execute.call_count)
        self.assertEqual(1, second_query.execute.call_count)

    def test_provider_timeout_is_transient(self):
        class APITimeoutError(Exception):
            pass

        self.assertTrue(db.is_transient_error(APITimeoutError()))
        self.assertTrue(db.is_transient_error(ConnectionError()))

    def test_business_error_is_not_retried(self):
        calls = 0

        def invalid():
            nonlocal calls
            calls += 1
            raise ValueError("invalid payload")

        with self.assertRaisesRegex(ValueError, "invalid payload"):
            db.retry(invalid)
        self.assertEqual(1, calls)

    def test_missing_category_column_falls_back_to_legacy_task_fields(self):
        missing_column = RuntimeError("42703 column tasks.content_category does not exist")
        modern = type("Query", (), {"data": None})()
        legacy = type("Query", (), {"data": {"title": "标题", "author": {"name": "作者"}}})()
        with patch("db.retry", side_effect=[missing_column, legacy]):
            task = db.get_task_prompt_context("task-id")
        self.assertEqual("标题", task["title"])
        self.assertNotIn("content_category", task)


class CommentRankingTests(unittest.TestCase):
    def test_replies_affect_ranking_and_duplicates_are_removed(self):
        comments = [
            {"text": "点赞较高", "likes": 20, "replies": 0},
            {"text": "讨论很多", "likes": 1, "replies": 5},
            {"text": "点赞较高", "likes": 3, "replies": 0},
        ]
        ranked = select_hot_comments(comments)
        self.assertEqual(["讨论很多", "点赞较高"], [item["text"] for item in ranked])


if __name__ == "__main__":
    unittest.main()
