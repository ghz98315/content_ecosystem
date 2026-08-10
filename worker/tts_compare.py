"""Generate isolated Edge/CosyVoice2 listening artifacts without touching tasks."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import config
from tts_providers import get_tts_provider


async def _render_provider(name: str, text: str, voice: str, output_dir: Path) -> dict:
    result = {
        "provider": name,
        "voice": voice,
        "status": "failed",
        "manual_review": {
            "pause_naturalness": "pending",
            "voice_quality": "pending",
            "subtitle_alignment": "pending",
        },
    }
    try:
        audio, boundaries, duration = await get_tts_provider(
            name, allow_experimental=True
        ).synthesize(text, voice)
        audio_path = output_dir / f"{name}.mp3"
        audio_path.write_bytes(audio)
        result.update({
            "status": "done",
            "file": audio_path.name,
            "duration": round(float(duration), 3),
            "boundary_count": len(boundaries),
            "sha256": hashlib.sha256(audio).hexdigest(),
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def generate_comparison(
    text: str,
    output_dir: Path,
    edge_voice: str,
    cosy_voice: str,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input.txt").write_text(text, encoding="utf-8")
    results = await asyncio.gather(
        _render_provider("edge", text, edge_voice, output_dir),
        _render_provider("cosyvoice2", text, cosy_voice, output_dir),
    )
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "isolated_tts_listening_comparison",
        "production_audio_replaced": False,
        "text_chars": len(text),
        "providers": results,
        "acceptance": {
            "duration": "compare generated durations and decoded playback",
            "pause_naturalness": "manual review required",
            "voice_quality": "manual review required",
            "subtitle_alignment": "manual review required before production switch",
        },
    }
    (output_dir / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成 Edge 与 CosyVoice2 的隔离试听对比产物，不修改正式任务。"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--text-file", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--edge-voice", default=config.TTS_VOICE)
    parser.add_argument("--cosy-voice", default=config.COSYVOICE2_VOICE)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        raise SystemExit("试听文本不能为空")
    output_dir = args.output_dir or Path("tts-comparisons") / datetime.now().strftime("%Y%m%d-%H%M%S")
    report = asyncio.run(generate_comparison(text, output_dir, args.edge_voice, args.cosy_voice))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "done" for item in report["providers"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
