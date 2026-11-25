"""Generate a 30-second 9:16 hand-drawn whiteboard animation MP4 for music tech news."""

from __future__ import annotations

import math
import random
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


# Warm sketchbook palette
BG_PAPER = (250, 245, 232)
GRID_DOT = (224, 216, 198)
MARGIN_RED = (232, 160, 154)
INK_DARK = (32, 34, 42)
INK_MUTED = (92, 96, 110)
HIGHLIGHT_YELLOW = (255, 228, 120)
HIGHLIGHT_CORAL = (255, 178, 150)
HIGHLIGHT_MINT = (168, 232, 206)
ACCENT_BLUE = (64, 120, 192)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _read_wav_envelope(wav_path: Path, fps: int) -> tuple[float, np.ndarray]:
    """Return (duration_sec, per_frame_rms_normalized_0_to_1)."""
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        raw = wf.readframes(n_frames)

    duration = n_frames / float(sr) if sr else 30.0
    dtype = np.int16 if sampwidth == 2 else np.uint8
    audio = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)
    if sampwidth == 2:
        audio /= 32768.0
    else:
        audio = (audio - 128.0) / 128.0

    total_video_frames = max(1, int(math.ceil(duration * fps)))
    samples_per_frame = max(1, int(sr / fps))
    env = np.zeros(total_video_frames, dtype=np.float32)
    for f in range(total_video_frames):
        s0 = f * samples_per_frame
        s1 = min(len(audio), s0 + samples_per_frame)
        if s1 > s0:
            env[f] = float(np.sqrt(np.mean(audio[s0:s1] ** 2)))
    peak = float(np.max(env)) if len(env) else 1.0
    if peak > 1e-5:
        env = env / peak
    return duration, env


def _make_paper_background(width: int, height: int) -> Image.Image:
    """Create a warm sketchbook paper texture with subtle grain and notebook lines."""
    rng = np.random.default_rng(42)
    base = np.full((height, width, 3), BG_PAPER, dtype=np.int16)
    noise = rng.integers(-6, 7, size=(height, width, 1), dtype=np.int16)
    arr = np.clip(base + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img)

    # Subtle dot grid
    step = 48
    for y in range(60, height - 60, step):
        for x in range(60, width - 60, step):
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=GRID_DOT)

    # Notebook vertical margin line
    draw.line([(72, 0), (72, height)], fill=MARGIN_RED, width=2)
    return img


def _sketch_line(
    draw: ImageDraw.ImageDraw,
    p0: tuple[float, float],
    p1: tuple[float, float],
    color: tuple[int, int, int] = INK_DARK,
    width: int = 4,
    seed: int = 0,
    progress: float = 1.0,
) -> None:
    """Draw a hand-drawn wobbly double-pass ink line."""
    if progress <= 0.0:
        return
    progress = min(1.0, progress)
    x0, y0 = p0
    x1, y1 = p1
    xe = x0 + (x1 - x0) * progress
    ye = y0 + (y1 - y0) * progress

    rng = random.Random(seed)
    steps = max(4, int(math.hypot(xe - x0, ye - y0) / 18))
    for pass_idx in range(2):
        pts = []
        for i in range(steps + 1):
            t = i / steps
            px = x0 + (xe - x0) * t + rng.uniform(-2.2, 2.2)
            py = y0 + (ye - y0) * t + rng.uniform(-2.2, 2.2)
            pts.append((px, py))
        draw.line(pts, fill=color, width=max(1, width - pass_idx))


def _sketch_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    color: tuple[int, int, int] = INK_DARK,
    width: int = 4,
    seed: int = 10,
    progress: float = 1.0,
) -> None:
    x0, y0, x1, y1 = box
    edges = [
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    ]
    for idx, (a, b) in enumerate(edges):
        seg_p = (progress * 4.0) - idx
        _sketch_line(draw, a, b, color=color, width=width, seed=seed + idx * 7, progress=seg_p)


def _draw_synth_doodle(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    frame_idx: int,
    draw_progress: float,
    amp: float,
) -> None:
    """Draw an animated hand-drawn synthesizer & musical notes doodle."""
    w, h = 620, 320
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2

    # Subtle marker fill behind synth
    if draw_progress > 0.25:
        draw.rounded_rectangle(
            (x0 + 10, y0 + 14, x1 - 6, y1 - 6),
            radius=18,
            fill=HIGHLIGHT_MINT,
        )

    # Outer chassis
    _sketch_rect(draw, (x0, y0, x1, y1), INK_DARK, width=5, seed=101, progress=draw_progress * 1.4)

    # Top control panel divider
    panel_y = y0 + 135
    _sketch_line(draw, (x0 + 14, panel_y), (x1 - 14, panel_y), INK_DARK, width=3, seed=130, progress=(draw_progress - 0.2) * 2)

    # Knobs
    if draw_progress > 0.35:
        for i in range(4):
            kx = x0 + 75 + i * 90
            ky = y0 + 68
            r = 26
            draw.ellipse((kx - r, ky - r, kx + r, ky + r), outline=INK_DARK, width=4, fill=BG_PAPER)
            angle = -2.2 + i * 0.9 + math.sin(frame_idx * 0.08 + i) * 0.35 + amp * 0.6
            draw.line([(kx, ky), (kx + math.cos(angle) * 18, ky + math.sin(angle) * 18)], fill=INK_DARK, width=4)

        # Mini oscilloscope screen
        sx0, sy0, sx1, sy1 = x0 + 420, y0 + 30, x1 - 30, y0 + 110
        draw.rectangle((sx0, sy0, sx1, sy1), fill=(40, 48, 56), outline=INK_DARK, width=3)
        wave_pts = []
        for i in range(28):
            t = i / 27.0
            wx = sx0 + 8 + t * (sx1 - sx0 - 16)
            wy = (sy0 + sy1) / 2 + math.sin(t * 10 + frame_idx * 0.35) * (12 + amp * 20)
            wave_pts.append((wx, wy))
        draw.line(wave_pts, fill=(130, 240, 190), width=3)

    # Piano keys
    if draw_progress > 0.5:
        n_white = 10
        key_w = (w - 40) / n_white
        for i in range(n_white):
            kx0 = x0 + 20 + i * key_w
            kx1 = kx0 + key_w - 4
            fill = HIGHLIGHT_YELLOW if (i == (frame_idx // 6) % n_white) else BG_PAPER
            draw.rectangle((kx0, panel_y + 12, kx1, y1 - 16), fill=fill, outline=INK_DARK, width=3)
        for i in range(n_white - 1):
            if i % 7 in (2, 6):
                continue
            bx = x0 + 20 + (i + 1) * key_w - 14
            draw.rectangle((bx, panel_y + 12, bx + 24, panel_y + 105), fill=INK_DARK)

    # Floating hand-drawn musical notes bobbing above synth
    if draw_progress > 0.45:
        for idx, (nx, base_ny) in enumerate([(x0 + 60, y0 - 55), (cx + 10, y0 - 85), (x1 - 70, y0 - 50)]):
            bob = math.sin(frame_idx * 0.14 + idx * 1.8) * (10 + amp * 12)
            ny = base_ny + bob
            draw.ellipse((nx - 14, ny - 10, nx + 14, ny + 10), fill=INK_DARK)
            draw.line([(nx + 12, ny), (nx + 12, ny - 46)], fill=INK_DARK, width=5)
            draw.line([(nx + 12, ny - 46), (nx + 34, ny - 34)], fill=INK_DARK, width=5)


def _wrap_cjk(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        cur += ch
        if len(cur) >= max_chars:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def _split_script_chunks(script: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[。！？!?，,；;]+", script) if p.strip()]
    if not parts:
        return [script]
    # Merge very short fragments so each subtitle card feels natural
    merged: list[str] = []
    for p in parts:
        if merged and len(merged[-1]) + len(p) <= 18:
            merged[-1] = f"{merged[-1]}，{p}"
        else:
            merged.append(p)
    return merged


def render_handdrawn_video(
    article: dict[str, Any],
    wav_path: Path,
    output_mp4: Path,
    video_cfg: dict[str, Any],
) -> tuple[Path, float]:
    """Render a 9:16 hand-drawn whiteboard animation MP4 synced to wav_path."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    width = int(video_cfg.get("width", 1080))
    height = int(video_cfg.get("height", 1920))
    fps = int(video_cfg.get("fps", 24))

    duration, env = _read_wav_envelope(wav_path, fps)
    total_frames = len(env)

    font_title = _load_font(video_cfg.get("font_zh_bold", "C:/Windows/Fonts/msjhbd.ttc"), 54)
    font_sub = _load_font(video_cfg.get("font_zh", "C:/Windows/Fonts/kaiu.ttf"), 50)
    font_small = _load_font(video_cfg.get("font_zh_bold", "C:/Windows/Fonts/msjhbd.ttc"), 32)
    font_en = _load_font(video_cfg.get("font_en", "C:/Windows/Fonts/segoeprb.ttf"), 36)

    paper_bg = _make_paper_background(width, height)

    title_zh = article.get("title_zh") or article.get("title", "音樂科技速報")
    category = article.get("category", "音樂科技")
    source = article.get("source", "SoundWeavers")
    script = article.get("broadcast_script") or article.get("summary", title_zh)
    chunks = _split_script_chunks(script)
    title_lines = _wrap_cjk(title_zh, 14)[:3]

    # Allocate time per subtitle chunk proportionally to character length
    total_chars = sum(len(c) for c in chunks) or 1
    chunk_bounds: list[tuple[int, int, str]] = []
    cur_f = 0
    for idx, ch_text in enumerate(chunks):
        span = int(round(total_frames * (len(ch_text) / total_chars)))
        end_f = total_frames if idx == len(chunks) - 1 else min(total_frames, cur_f + max(1, span))
        chunk_bounds.append((cur_f, end_f, ch_text))
        cur_f = end_f

    print(f"[video] Rendering {total_frames} frames ({duration:.1f}s @ {fps}fps) -> {output_mp4.name}")
    with tempfile.TemporaryDirectory(prefix="sw_frames_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for f in range(total_frames):
            t_sec = f / float(fps)
            amp = float(env[f])
            frame = paper_bg.copy()
            draw = ImageDraw.Draw(frame)

            # 1. Top sketchbook header
            draw.rounded_rectangle((96, 86, width - 96, 174), radius=14, fill=HIGHLIGHT_CORAL)
            _sketch_rect(draw, (90, 80, width - 90, 168), INK_DARK, width=4, seed=1, progress=min(1.0, t_sec / 0.8))
            draw.text((126, 102), "SOUNDWEAVERS MUSIC NEWS", fill=INK_DARK, font=font_en)

            # Category stamp pill
            pill_w = 240
            draw.rounded_rectangle((100, 200, 100 + pill_w, 258), radius=24, fill=HIGHLIGHT_YELLOW, outline=INK_DARK, width=3)
            draw.text((128, 210), f"# {category}", fill=INK_DARK, font=font_small)
            draw.text((365, 212), f"來源：{source}", fill=INK_MUTED, font=font_small)

            # 2. Headline with animated highlighter underline
            y_cursor = 290
            hl_prog = min(1.0, max(0.0, (t_sec - 0.2) / 0.9))
            for li, line in enumerate(title_lines):
                if hl_prog > 0:
                    bar_w = int((width - 210) * hl_prog)
                    draw.rectangle((104, y_cursor + 44, 104 + bar_w, y_cursor + 64), fill=HIGHLIGHT_YELLOW)
                draw.text((108, y_cursor), line, fill=INK_DARK, font=font_title)
                y_cursor += 76

            # 3. Hand-drawn synthesizer & notes doodle
            _draw_synth_doodle(draw, width // 2, 770, f, draw_progress=min(1.0, t_sec / 1.8), amp=amp)

            # 4. Active subtitle card (hand-drawn quote box)
            active_text = chunks[-1]
            for s_f, e_f, txt in chunk_bounds:
                if s_f <= f < e_f:
                    active_text = txt
                    break

            card_box = (96, 1050, width - 96, 1460)
            draw.rounded_rectangle(
                (card_box[0] + 10, card_box[1] + 10, card_box[2] + 10, card_box[3] + 10),
                radius=22,
                fill=(232, 224, 204),
            )
            draw.rounded_rectangle(card_box, radius=22, fill=(255, 253, 246))
            _sketch_rect(draw, card_box, INK_DARK, width=4, seed=55, progress=min(1.0, t_sec / 1.0))

            sub_lines = _wrap_cjk(active_text, 14)[:5]
            sy = 1105 + max(0, (4 - len(sub_lines)) * 28)
            for sline in sub_lines:
                draw.text((134, sy), sline, fill=INK_DARK, font=font_sub)
                sy += 68

            # 5. Reactive hand-drawn audio waveform
            wf_y = 1610
            n_bars = 26
            bar_gap = (width - 240) / n_bars
            for b in range(n_bars):
                bx = 120 + b * bar_gap
                wave_mod = 0.4 + 0.6 * abs(math.sin(f * 0.22 + b * 0.55))
                bh = int(14 + (amp * 95 + 16) * wave_mod)
                col = ACCENT_BLUE if b % 3 == 0 else INK_DARK
                draw.rounded_rectangle((bx, wf_y - bh, bx + 16, wf_y + bh), radius=6, fill=col)

            # 6. Progress bar + Footer
            prog = f / float(max(1, total_frames - 1))
            draw.rectangle((100, 1770, width - 100, 1784), fill=GRID_DOT)
            draw.rectangle((100, 1770, 100 + int((width - 200) * prog), 1784), fill=INK_DARK)
            draw.text((100, 1810), "soundweavers-music.github.io/news", fill=INK_MUTED, font=font_en)

            frame.save(tmp_path / f"frame_{f:05d}.jpg", "JPEG", quality=88)

        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = "ffmpeg"

        ffmpeg_cmd = [
            ffmpeg_bin, "-y",
            "-framerate", str(fps),
            "-i", str(tmp_path / "frame_%05d.jpg"),
            "-i", str(wav_path),
            "-vf", "scale=720:1280",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_mp4),
        ]
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg failed (code {res.returncode}): {res.stderr[-400:]}")

    print(f"[video] Done -> {output_mp4} ({duration:.1f}s)")
    return output_mp4, round(duration, 1)
