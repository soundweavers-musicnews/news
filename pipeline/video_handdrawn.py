"""Generate a multi-scene 9:16 hand-drawn sketchbook animation MP4 for music tech news."""

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


# Warm SoundWeavers sketchbook palette
BG_PAPER = (251, 248, 244)       # #FBF8F4
GRID_DOT = (229, 221, 214)       # #E5DDD6
MARGIN_LINE = (214, 180, 160)
INK_DARK = (61, 50, 41)          # #3D3229
INK_MUTED = (130, 114, 102)
WOOD_ACCENT = (196, 149, 106)    # #C4956A
CLAY_ACCENT = (166, 124, 82)     # #A67C52
HIGHLIGHT_YELLOW = (252, 232, 160)
HIGHLIGHT_CORAL = (244, 198, 178)
HIGHLIGHT_MINT = (188, 228, 212)
HIGHLIGHT_BLUE = (186, 210, 236)
ACCENT_BLUE = (107, 143, 191)    # #6B8FBF


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

    duration = n_frames / float(sr) if sr else 25.0
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
    noise = rng.integers(-5, 6, size=(height, width, 1), dtype=np.int16)
    arr = np.clip(base + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img)

    step = 44
    for y in range(56, height - 56, step):
        for x in range(56, width - 56, step):
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=GRID_DOT)

    draw.line([(68, 0), (68, height)], fill=MARGIN_LINE, width=2)
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
            px = x0 + (xe - x0) * t + rng.uniform(-2.0, 2.0)
            py = y0 + (ye - y0) * t + rng.uniform(-2.0, 2.0)
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


def _draw_sparkle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color=CLAY_ACCENT) -> None:
    draw.line([(cx - r, cy), (cx + r, cy)], fill=color, width=3)
    draw.line([(cx, cy - r), (cx, cy + r)], fill=color, width=3)
    d = r * 0.55
    draw.line([(cx - d, cy - d), (cx + d, cy + d)], fill=color, width=2)
    draw.line([(cx - d, cy + d), (cx + d, cy - d)], fill=color, width=2)


def _draw_note(draw: ImageDraw.ImageDraw, nx: float, ny: float, color=INK_DARK) -> None:
    draw.ellipse((nx - 14, ny - 10, nx + 14, ny + 10), fill=color)
    draw.line([(nx + 12, ny), (nx + 12, ny - 46)], fill=color, width=5)
    draw.line([(nx + 12, ny - 46), (nx + 34, ny - 34)], fill=color, width=5)


# ── 5 Rich Hand-Drawn Illustrated Scenes ──────────────────────────────────────

def _scene_broadcast_mic(draw: ImageDraw.ImageDraw, cx: int, cy: int, f: int, p: float, amp: float) -> None:
    """Scene 0: Studio Condenser Mic + Broadcast Radio Waves + Sparkles."""
    # Soft watercolor circle backdrop
    r_bg = int(175 * min(1.0, p * 1.4))
    if r_bg > 10:
        draw.ellipse((cx - r_bg, cy - r_bg, cx + r_bg, cy + r_bg), fill=HIGHLIGHT_CORAL)

    # Mic capsule
    mx0, my0, mx1, my1 = cx - 64, cy - 135, cx + 64, cy + 25
    draw.rounded_rectangle((mx0, my0, mx1, my1), radius=58, fill=BG_PAPER, outline=INK_DARK, width=5)
    for gy in range(my0 + 30, my1 - 24, 20):
        _sketch_line(draw, (mx0 + 18, gy), (mx1 - 18, gy), INK_DARK, width=3, seed=gy, progress=p * 1.5)

    # U-mount & stand
    if p > 0.25:
        draw.arc((cx - 92, cy - 55, cx + 92, cy + 70), start=0, end=180, fill=INK_DARK, width=6)
        _sketch_line(draw, (cx, cy + 70), (cx, cy + 140), INK_DARK, width=6, seed=21, progress=(p - 0.2) * 2)
        _sketch_line(draw, (cx - 75, cy + 140), (cx + 75, cy + 140), INK_DARK, width=7, seed=22, progress=(p - 0.3) * 2)

    # Animated radio broadcast waves on both sides
    if p > 0.35:
        for side in (-1, 1):
            for w_idx in range(3):
                phase = ((f * 0.12 + w_idx * 0.9) % 3.0)
                rad = 110 + w_idx * 42 + int(amp * 28)
                start_a = -42 if side == 1 else 138
                end_a = 42 if side == 1 else 222
                col = ACCENT_BLUE if w_idx == 1 else INK_DARK
                if phase < 2.4:
                    draw.arc((cx - rad, cy - 60 - rad // 2, cx + rad, cy - 60 + rad // 2), start=start_a, end=end_a, fill=col, width=4)

    _draw_sparkle(draw, cx - 220, cy - 110 + math.sin(f * 0.15) * 8, 16)
    _draw_sparkle(draw, cx + 220, cy - 95 + math.cos(f * 0.15) * 8, 14)


def _scene_mpc_sampler(draw: ImageDraw.ImageDraw, cx: int, cy: int, f: int, p: float, amp: float) -> None:
    """Scene 1: Hand-Drawn MPC Sampler with 4x4 Glowing Pads + Screen + Knobs."""
    w, h = 640, 340
    x0, y0, x1, y1 = cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2

    if p > 0.15:
        draw.rounded_rectangle((x0 + 12, y0 + 14, x1 - 4, y1 - 4), radius=20, fill=HIGHLIGHT_MINT)
    _sketch_rect(draw, (x0, y0, x1, y1), INK_DARK, width=5, seed=101, progress=p * 1.4)

    # Left: 4x4 MPC Pads (illuminated rhythmically)
    if p > 0.3:
        pad_size = 56
        gap = 12
        px_start, py_start = x0 + 36, y0 + 38
        active_pad = (f // 5) % 16
        for row in range(4):
            for col in range(4):
                idx = row * 4 + col
                px0 = px_start + col * (pad_size + gap)
                py0 = py_start + row * (pad_size + gap)
                fill = HIGHLIGHT_YELLOW if idx == active_pad else (HIGHLIGHT_CORAL if idx == (active_pad + 5) % 16 else BG_PAPER)
                draw.rounded_rectangle((px0, py0, px0 + pad_size, py0 + pad_size), radius=8, fill=fill, outline=INK_DARK, width=3)

    # Right top: OLED waveform screen
    if p > 0.4:
        sx0, sy0, sx1, sy1 = x0 + 335, y0 + 38, x1 - 36, y0 + 165
        draw.rounded_rectangle((sx0, sy0, sx1, sy1), radius=10, fill=(48, 44, 40), outline=INK_DARK, width=4)
        pts = []
        for i in range(32):
            t = i / 31.0
            wx = sx0 + 12 + t * (sx1 - sx0 - 24)
            wy = (sy0 + sy1) / 2 + math.sin(t * 11 + f * 0.35) * (16 + amp * 30)
            pts.append((wx, wy))
        draw.line(pts, fill=(140, 235, 195), width=3)

        # Right bottom: 4 Q-Link Knobs
        for i in range(4):
            kx = x0 + 370 + i * 64
            ky = y0 + 240
            draw.ellipse((kx - 22, ky - 22, kx + 22, ky + 22), fill=BG_PAPER, outline=INK_DARK, width=4)
            ang = -2.1 + i * 0.8 + math.sin(f * 0.1 + i) * 0.4
            draw.line([(kx, ky), (kx + math.cos(ang) * 15, ky + math.sin(ang) * 15)], fill=INK_DARK, width=4)

    _draw_note(draw, x0 + 40, y0 - 38 + math.sin(f * 0.16) * 10)
    _draw_note(draw, x1 - 60, y0 - 48 + math.cos(f * 0.16) * 10)


def _scene_plugin_sdk(draw: ImageDraw.ImageDraw, cx: int, cy: int, f: int, p: float, amp: float) -> None:
    """Scene 2: Open-Source Audio Plugin / SDK Rack + Code Brackets + Signal Flow."""
    # Left: Code window
    lx0, ly0, lx1, ly1 = cx - 320, cy - 140, cx - 30, cy + 120
    draw.rounded_rectangle((lx0 + 8, ly0 + 10, lx1 + 8, ly1 + 10), radius=14, fill=HIGHLIGHT_BLUE)
    draw.rounded_rectangle((lx0, ly0, lx1, ly1), radius=14, fill=BG_PAPER)
    _sketch_rect(draw, (lx0, ly0, lx1, ly1), INK_DARK, width=4, seed=201, progress=p * 1.4)
    # Window dots
    for i in range(3):
        draw.ellipse((lx0 + 18 + i * 20, ly0 + 16, lx0 + 28 + i * 20, ly0 + 26), fill=INK_DARK)
    # Sketchy code lines
    if p > 0.25:
        code_widths = [150, 210, 130, 195, 110, 175]
        for idx, cw in enumerate(code_widths):
            cy_line = ly0 + 58 + idx * 30
            col = ACCENT_BLUE if idx % 2 == 0 else INK_DARK
            _sketch_line(draw, (lx0 + 28, cy_line), (lx0 + 28 + cw, cy_line), col, width=4, seed=210 + idx, progress=(p - 0.15) * 1.8)

    # Center: Animated signal arrow ->
    if p > 0.35:
        ax0, ax1 = cx - 15, cx + 45
        _sketch_line(draw, (ax0, cy - 10), (ax1, cy - 10), CLAY_ACCENT, width=5, seed=230, progress=(p - 0.3) * 2)
        draw.polygon([(ax1 + 8, cy - 10), (ax1 - 10, cy - 24), (ax1 - 10, cy + 4)], fill=CLAY_ACCENT)

    # Right: VST FX Pedal / Rack unit
    rx0, ry0, rx1, ry1 = cx + 65, cy - 150, cx + 325, cy + 135
    draw.rounded_rectangle((rx0 + 8, ry0 + 10, rx1 + 8, ry1 + 10), radius=18, fill=HIGHLIGHT_YELLOW)
    draw.rounded_rectangle((rx0, ry0, rx1, ry1), radius=18, fill=BG_PAPER)
    _sketch_rect(draw, (rx0, ry0, rx1, ry1), INK_DARK, width=4, seed=240, progress=p * 1.4)

    if p > 0.4:
        # 3 big FX knobs
        for i, (kx, ky) in enumerate([(rx0 + 75, ry0 + 78), (rx1 - 75, ry0 + 78), ((rx0 + rx1) // 2, ry0 + 165)]):
            draw.ellipse((kx - 32, ky - 32, kx + 32, ky + 32), fill=HIGHLIGHT_CORAL if i == 2 else BG_PAPER, outline=INK_DARK, width=4)
            ang = -1.8 + i * 1.1 + math.sin(f * 0.14 + i) * 0.5 + amp * 0.5
            draw.line([(kx, ky), (kx + math.cos(ang) * 22, ky + math.sin(ang) * 22)], fill=INK_DARK, width=4)
        # Footswitch / LED
        draw.ellipse(((rx0 + rx1) // 2 - 10, ry1 - 45, (rx0 + rx1) // 2 + 10, ry1 - 25), fill=ACCENT_BLUE if (f // 8) % 2 == 0 else HIGHLIGHT_MINT, outline=INK_DARK, width=3)


def _scene_headphones_daw(draw: ImageDraw.ImageDraw, cx: int, cy: int, f: int, p: float, amp: float) -> None:
    """Scene 3: Studio Headphones + Piano Keys + EQ Curve."""
    # Headphone arc
    draw.arc((cx - 130, cy - 165, cx + 130, cy + 75), start=180, end=360, fill=INK_DARK, width=10)
    draw.arc((cx - 118, cy - 153, cx + 118, cy + 63), start=190, end=350, fill=WOOD_ACCENT, width=5)
    # Ear cups
    draw.rounded_rectangle((cx - 165, cy - 65, cx - 105, cy + 55), radius=24, fill=HIGHLIGHT_CORAL, outline=INK_DARK, width=5)
    draw.rounded_rectangle((cx + 105, cy - 65, cx + 165, cy + 55), radius=24, fill=HIGHLIGHT_CORAL, outline=INK_DARK, width=5)

    # Center EQ curve inside headphones
    if p > 0.25:
        pts = []
        for i in range(24):
            t = i / 23.0
            ex = cx - 85 + t * 170
            ey = cy + math.sin(t * 7 + f * 0.28) * (24 + amp * 35)
            pts.append((ex, ey))
        draw.line(pts, fill=ACCENT_BLUE, width=5)

    # Bottom mini piano strip
    if p > 0.35:
        kx0, ky0, kx1, ky1 = cx - 260, cy + 88, cx + 260, cy + 175
        _sketch_rect(draw, (kx0, ky0, kx1, ky1), INK_DARK, width=4, seed=310, progress=p * 1.4)
        n_keys = 12
        kw = (kx1 - kx0) / n_keys
        for i in range(n_keys):
            x_a = kx0 + i * kw
            fill = HIGHLIGHT_YELLOW if i == (f // 4) % n_keys else BG_PAPER
            draw.rectangle((x_a + 2, ky0 + 2, x_a + kw - 2, ky1 - 2), fill=fill, outline=INK_DARK, width=2)
        for i in range(n_keys - 1):
            if i % 7 in (2, 6):
                continue
            bx = kx0 + (i + 1) * kw - 10
            draw.rectangle((bx, ky0 + 2, bx + 18, ky0 + 52), fill=INK_DARK)

    _draw_sparkle(draw, cx - 230, cy - 90 + math.sin(f * 0.14) * 8, 14)
    _draw_note(draw, cx + 225, cy - 75 + math.cos(f * 0.14) * 10)


def _scene_checklist_outro(draw: ImageDraw.ImageDraw, cx: int, cy: int, f: int, p: float, amp: float) -> None:
    """Scene 4: Sketchbook Takeaway Card + Checkmarks + Star Burst."""
    x0, y0, x1, y1 = cx - 250, cy - 145, cx + 250, cy + 145
    draw.rounded_rectangle((x0 + 12, y0 + 12, x1 + 12, y1 + 12), radius=18, fill=HIGHLIGHT_YELLOW)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=BG_PAPER)
    _sketch_rect(draw, (x0, y0, x1, y1), INK_DARK, width=5, seed=401, progress=p * 1.4)

    # 3 animated checkmarks + lines
    for i in range(3):
        ry = y0 + 68 + i * 74
        bx = x0 + 48
        draw.rounded_rectangle((bx, ry - 18, bx + 36, ry + 18), radius=6, fill=HIGHLIGHT_MINT, outline=INK_DARK, width=3)
        if p > 0.2 + i * 0.15:
            draw.line([(bx + 8, ry), (bx + 16, ry + 10), (bx + 30, ry - 12)], fill=INK_DARK, width=5)
            _sketch_line(draw, (bx + 58, ry), (x1 - 52, ry), INK_DARK, width=5, seed=420 + i, progress=(p - 0.15 * i) * 1.8)

    _draw_sparkle(draw, x1 + 35, y0 - 20 + math.sin(f * 0.18) * 8, 18, color=CLAY_ACCENT)
    _draw_sparkle(draw, x0 - 38, y1 - 15 + math.cos(f * 0.18) * 8, 15, color=ACCENT_BLUE)


SCENES = [
    _scene_broadcast_mic,
    _scene_mpc_sampler,
    _scene_plugin_sdk,
    _scene_headphones_daw,
    _scene_checklist_outro,
]


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
    merged: list[str] = []
    for p in parts:
        if merged and len(merged[-1]) + len(p) <= 17:
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
    """Render a multi-scene 9:16 hand-drawn sketchbook animation MP4 synced to wav_path."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    width = int(video_cfg.get("width", 1080))
    height = int(video_cfg.get("height", 1920))
    fps = int(video_cfg.get("fps", 24))

    duration, env = _read_wav_envelope(wav_path, fps)
    total_frames = len(env)

    # Refined SoundWeavers typography: Noto Serif TC + Noto Sans TC
    font_title = _load_font(video_cfg.get("font_zh", "C:/Windows/Fonts/NotoSerifTC-VF.ttf"), 56)
    font_sub = _load_font(video_cfg.get("font_zh", "C:/Windows/Fonts/NotoSerifTC-VF.ttf"), 50)
    font_small = _load_font(video_cfg.get("font_zh_bold", "C:/Windows/Fonts/NotoSansTC-VF.ttf"), 30)
    font_en = _load_font(video_cfg.get("font_en", "C:/Windows/Fonts/segoeprb.ttf"), 34)

    paper_bg = _make_paper_background(width, height)

    # Load optional custom hand-drawn illustrations tailored to the article
    custom_imgs: list[Image.Image] = []
    for p_str in article.get("illustrations") or []:
        p_img = Path(p_str)
        if p_img.exists():
            try:
                custom_imgs.append(Image.open(p_img).convert("RGB"))
            except Exception:
                pass

    title_zh = article.get("title_zh") or article.get("title", "音樂科技速報")
    category = article.get("category", "音樂科技")
    source = article.get("source", "SoundWeavers")
    script = article.get("broadcast_script") or article.get("summary", title_zh)
    chunks = _split_script_chunks(script)
    title_lines = _wrap_cjk(title_zh, 14)[:3]

    total_chars = sum(len(c) for c in chunks) or 1
    chunk_bounds: list[tuple[int, int, str, int]] = []
    cur_f = 0
    for idx, ch_text in enumerate(chunks):
        span = int(round(total_frames * (len(ch_text) / total_chars)))
        end_f = total_frames if idx == len(chunks) - 1 else min(total_frames, cur_f + max(1, span))
        scene_idx = idx % len(SCENES)
        chunk_bounds.append((cur_f, end_f, ch_text, scene_idx))
        cur_f = end_f

    print(f"[video] Rendering {total_frames} frames ({duration:.1f}s @ {fps}fps, {len(chunks)} scenes) -> {output_mp4.name}")
    with tempfile.TemporaryDirectory(prefix="sw_frames_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for f in range(total_frames):
            t_sec = f / float(fps)
            amp = float(env[f])
            frame = paper_bg.copy()
            draw = ImageDraw.Draw(frame)

            # 1. Top editorial sketchbook header
            draw.rounded_rectangle((96, 82, width - 96, 166), radius=14, fill=HIGHLIGHT_CORAL)
            _sketch_rect(draw, (90, 76, width - 90, 160), INK_DARK, width=4, seed=1, progress=min(1.0, t_sec / 0.6))
            draw.text((126, 98), "SOUNDWEAVERS  MUSIC  NEWS", fill=INK_DARK, font=font_en)

            # Category stamp + Source
            draw.rounded_rectangle((100, 192, 320, 248), radius=24, fill=HIGHLIGHT_YELLOW, outline=INK_DARK, width=3)
            draw.text((128, 202), f"# {category}", fill=INK_DARK, font=font_small)
            draw.text((345, 204), f"來源：{source}", fill=INK_MUTED, font=font_small)

            # 2. Headline with animated highlighter underline
            y_cursor = 278
            hl_prog = min(1.0, max(0.0, (t_sec - 0.15) / 0.8))
            for line in title_lines:
                if hl_prog > 0:
                    bar_w = int((width - 210) * hl_prog)
                    draw.rectangle((104, y_cursor + 46, 104 + bar_w, y_cursor + 66), fill=HIGHLIGHT_YELLOW)
                draw.text((108, y_cursor), line, fill=INK_DARK, font=font_title)
                y_cursor += 76

            # Determine active subtitle chunk & scene (lead by 0.45s so subtitles never lag behind speech)
            f_sub = min(total_frames - 1, f + int(round(fps * 0.45)))
            active_text = chunks[-1]
            scene_idx = 0
            scene_local_p = 1.0
            for s_f, e_f, txt, sc_i in chunk_bounds:
                if s_f <= f_sub < e_f:
                    active_text = txt
                    scene_idx = sc_i
                    scene_local_p = min(1.0, max(0.0, (f_sub - s_f) / max(1.0, fps * 0.9)))
                    break

            # 3. Multi-scene hand-drawn illustration stage (custom article art with Ken Burns, or procedural fallback)
            if custom_imgs:
                img_idx = scene_idx % len(custom_imgs)
                src_img = custom_imgs[img_idx]
                box_w, box_h = 720, 440
                bx0, by0 = (width - box_w) // 2, 555
                # Subtle Ken Burns slow zoom (1.0 -> 1.07)
                zoom = 1.0 + 0.07 * scene_local_p
                sw, sh = src_img.size
                # Center-crop to aspect ratio with zoom
                target_ar = box_w / float(box_h)
                if sw / float(sh) > target_ar:
                    crop_h = sh / zoom
                    crop_w = crop_h * target_ar
                else:
                    crop_w = sw / zoom
                    crop_h = crop_w / target_ar
                cx_i, cy_i = sw / 2.0, sh / 2.0
                cropped = src_img.crop((cx_i - crop_w / 2, cy_i - crop_h / 2, cx_i + crop_w / 2, cy_i + crop_h / 2))
                resized = cropped.resize((box_w, box_h), Image.Resampling.BILINEAR)
                # Sketchbook shadow + frame + tape
                draw.rounded_rectangle((bx0 + 10, by0 + 10, bx0 + box_w + 10, by0 + box_h + 10), radius=18, fill=GRID_DOT)
                frame.paste(resized, (bx0, by0))
                _sketch_rect(draw, (bx0, by0, bx0 + box_w, by0 + box_h), INK_DARK, width=5, seed=300 + img_idx, progress=1.0)
                draw.rectangle((bx0 - 18, by0 - 12, bx0 + 54, by0 + 22), fill=WOOD_ACCENT)
                draw.rectangle((bx0 + box_w - 54, by0 + box_h - 22, bx0 + box_w + 18, by0 + box_h + 12), fill=WOOD_ACCENT)
            else:
                SCENES[scene_idx](draw, width // 2, 775, f, scene_local_p, amp)

            # 4. Subtitle card (hand-drawn sketchbook note with tape corners)
            card_box = (96, 1055, width - 96, 1465)
            draw.rounded_rectangle(
                (card_box[0] + 10, card_box[1] + 10, card_box[2] + 10, card_box[3] + 10),
                radius=22,
                fill=GRID_DOT,
            )
            draw.rounded_rectangle(card_box, radius=22, fill=(255, 254, 251))
            _sketch_rect(draw, card_box, INK_DARK, width=4, seed=55 + scene_idx, progress=1.0)
            # Decorative masking tape on top center of card
            draw.rectangle((width // 2 - 75, 1036, width // 2 + 75, 1072), fill=WOOD_ACCENT)

            sub_lines = _wrap_cjk(active_text, 14)[:5]
            sy = 1110 + max(0, (4 - len(sub_lines)) * 28)
            for sline in sub_lines:
                draw.text((134, sy), sline, fill=INK_DARK, font=font_sub)
                sy += 68

            # 5. Reactive hand-drawn audio waveform
            wf_y = 1615
            n_bars = 26
            bar_gap = (width - 240) / n_bars
            for b in range(n_bars):
                bx = 120 + b * bar_gap
                wave_mod = 0.4 + 0.6 * abs(math.sin(f * 0.24 + b * 0.55))
                bh = int(14 + (amp * 92 + 16) * wave_mod)
                col = CLAY_ACCENT if b % 3 == 0 else INK_DARK
                draw.rounded_rectangle((bx, wf_y - bh, bx + 16, wf_y + bh), radius=6, fill=col)

            # 6. Progress bar + Footer
            prog = f / float(max(1, total_frames - 1))
            draw.rectangle((100, 1770, width - 100, 1784), fill=GRID_DOT)
            draw.rectangle((100, 1770, 100 + int((width - 200) * prog), 1784), fill=CLAY_ACCENT)
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
