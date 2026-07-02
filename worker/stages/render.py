"""⑧ 成片 render：逐句图 + TTS音频 + 字幕 + 片头片尾 → 9:16 竖版 MP4。

V1 模板：
  ┌ 片头卡  2s（书名+作者，黑底白字）
  │ 逐句图幻灯片（TTS总时长，等时分配，每张图缩放填充到1080×1920）
  └ 片尾卡  3s（免责声明，黑底白字）

  音轨：TTS mp3 从片头卡后开始播放
  字幕：ASS 格式烧入，按 tts_subtitles.json 的 segment 时间戳显示
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

import config
import db
import storage

W, H = 1080, 1920
FPS = 30
INTRO_DUR = 2.0   # 片头秒数
OUTRO_DUR = 3.0   # 片尾秒数

DISCLAIMER_TMPL = (
    "本视频基于{author}《{book}》\n及相关资料整理，\n"
    "仅供健康科普参考，\n不构成任何建议或行为指导。"
)


def ff() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


# ── 资产收集 ────────────────────────────────────────────────────────────────

def _load_json_artifact(task_id: str, artifact_type: str) -> dict | list | None:
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", artifact_type)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    local = storage.download_artifact(res.data[0]["storage_path"], ".json")
    try:
        return json.load(open(local, encoding="utf-8"))
    finally:
        try: os.remove(local)
        except OSError: pass


def _load_audio(task_id: str) -> str | None:
    """下载 TTS 音频到临时文件，返回路径。"""
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("stage_kind", "tts")
        .eq("type", "audio")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return storage.download_artifact(res.data[0]["storage_path"], ".mp3")


# ── ASS 字幕生成 ─────────────────────────────────────────────────────────────

def _fmt_ass_time(t: float) -> str:
    """秒 → ASS 时间格式 H:MM:SS.cs（注意字幕从 INTRO_DUR 后开始）。"""
    t = max(0.0, t + INTRO_DUR)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _make_ass(segments: list[dict], out_path: str) -> None:
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,"
        "Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,"
        "Encoding\n"
        "Style: Default,微软雅黑,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,4,2,2,80,80,120,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,"
        "Effect,Text\n"
    )
    lines = [header]
    for seg in segments:
        start = _fmt_ass_time(seg["start"])
        end   = _fmt_ass_time(seg["end"])
        text  = seg["text"].replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


# ── 图片片段生成 ──────────────────────────────────────────────────────────────

def _make_image_clip(img_path: str, duration: float, out_mp4: str) -> None:
    """单张图片 → 固定时长 MP4 片段（缩放到 1080×1920，保持比例，黑边填充）。"""
    cmd = [
        ff(), "-y",
        "-loop", "1", "-t", str(duration), "-i", img_path,
        "-vf", (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
        ),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-an",
        out_mp4,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _find_cjk_font() -> str:
    """在 Windows Fonts 目录中找中文字体，返回路径；找不到抛 FileNotFoundError。"""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\STZHONGS.TTF",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    raise FileNotFoundError("未找到中文字体，请确认 C:\\Windows\\Fonts 下有 msyh.ttc 或 simhei.ttf")


def _make_text_card(text: str, duration: float, out_mp4: str) -> None:
    """纯文字卡片 → MP4 片段（Pillow 绘制，避免 ffmpeg drawtext 中文字体问题）。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = _find_cjk_font()
    font_size = 52
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    lines = text.replace("\\n", "\n").split("\n")
    line_spacing = 20
    line_heights = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bb[3] - bb[1])
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
    y = (H - total_h) // 2

    for i, line in enumerate(lines):
        bb = draw.textbbox((0, 0), line, font=font)
        lw = bb[2] - bb[0]
        x = (W - lw) // 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_heights[i] + line_spacing

    # PNG → 临时文件，再用 ffmpeg loop 成 MP4
    tmp_png = out_mp4.replace(".mp4", "_card.png")
    img.save(tmp_png, "PNG")
    try:
        subprocess.run([
            ff(), "-y",
            "-loop", "1", "-t", str(duration), "-i", tmp_png,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-an",
            out_mp4,
        ], check=True, capture_output=True)
    finally:
        try: os.remove(tmp_png)
        except OSError: pass


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]

    # 收集资产
    img_index = _load_json_artifact(task_id, "image_index")
    subs_data = _load_json_artifact(task_id, "subtitle")
    book_data  = _load_json_artifact(task_id, "book")
    audio_path = _load_audio(task_id)

    if not img_index or not audio_path:
        db.set_stage(stage["id"], "failed",
                     error="缺少图片或音频产物（请确认 image/tts 阶段已完成）")
        return "failed", None

    images: list[dict] = img_index if isinstance(img_index, list) else []
    segments: list[dict] = (subs_data.get("segments", []) if subs_data else [])
    tts_dur: float = (subs_data.get("duration", 0.0) if subs_data else 0.0) or 1.0
    book_name   = (book_data.get("book_name", "")   if book_data else "") or "《本书》"
    author      = (book_data.get("author", "")      if book_data else "") or "作者"

    tmpdir = tempfile.mkdtemp(prefix="render_")
    try:
        # 1. 下载所有图片
        img_locals: list[str] = []
        for item in images:
            local = storage.download_artifact(item["path"], ".png")
            img_locals.append(local)

        if not img_locals:
            db.set_stage(stage["id"], "failed", error="图片列表为空")
            return "failed", None

        each_dur = tts_dur / len(img_locals)

        # 2. 生成图片 MP4 片段
        clip_paths: list[str] = []
        for i, img_local in enumerate(img_locals):
            clip = os.path.join(tmpdir, f"clip_{i:03d}.mp4")
            _make_image_clip(img_local, each_dur, clip)
            clip_paths.append(clip)
            os.remove(img_local)

        # 3. 片头卡
        intro_text = f"《{book_name.strip('《》')}》\\n{author}"
        intro_mp4 = os.path.join(tmpdir, "intro.mp4")
        _make_text_card(intro_text, INTRO_DUR, intro_mp4)

        # 4. 片尾卡
        disclaimer = DISCLAIMER_TMPL.format(
            author=author, book=book_name.strip("《》")
        ).replace("\n", "\\n")
        outro_mp4 = os.path.join(tmpdir, "outro.mp4")
        _make_text_card(disclaimer, OUTRO_DUR, outro_mp4)

        # 5. concat 列表（片头 + 图片片段 + 片尾）
        concat_txt = os.path.join(tmpdir, "concat.txt")
        with open(concat_txt, "w") as f:
            for p in [intro_mp4] + clip_paths + [outro_mp4]:
                f.write(f"file '{p}'\n")

        video_only = os.path.join(tmpdir, "video_only.mp4")
        subprocess.run([
            ff(), "-y", "-f", "concat", "-safe", "0",
            "-i", concat_txt, "-c", "copy", video_only,
        ], check=True, capture_output=True)

        # 6. ASS 字幕（字幕从 INTRO_DUR 后开始，见 _fmt_ass_time）
        ass_path = os.path.join(tmpdir, "subs.ass")
        _make_ass(segments, ass_path)

        # 7. 合并视频 + 音频 + 字幕，输出 final.mp4
        final = os.path.join(tmpdir, "final.mp4")
        # Windows 路径中 "C:" 的冒号在 ffmpeg filter graph 里需转义
        ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
        # 音频从 INTRO_DUR 处开始，片头无声
        subprocess.run([
            ff(), "-y",
            "-i", video_only,
            "-itsoffset", str(INTRO_DUR), "-i", audio_path,
            "-vf", f"ass={ass_escaped}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            final,
        ], check=True, capture_output=True)

        # 8. 上传
        sp = f"{task_id}/final.mp4"
        storage.upload(sp, final, "video/mp4")
        storage.add_artifact(task_id, "render", "final", sp, meta={
            "width": W, "height": H,
            "tts_duration": tts_dur,
            "image_count": len(img_locals),
        })
        return "done", sp

    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", errors="ignore")[-500:]
        db.set_stage(stage["id"], "failed", error=f"ffmpeg 失败: {err}")
        return "failed", None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if audio_path and os.path.exists(audio_path):
            try: os.remove(audio_path)
            except OSError: pass
