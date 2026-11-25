"""GPT-SoVITS v5turbo TTS client for SoundWeavers Music News."""

from __future__ import annotations

import math
import re
import struct
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

import requests


def _find_latest_weight(folder: Path, extensions: tuple[str, ...]) -> Path | None:
    if not folder.exists():
        return None
    candidates = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _ensure_wav_ref_audio(ref_audio_path: Path, cache_dir: Path) -> Path:
    """Convert .m4a reference audio to 32kHz mono WAV for GPT-SoVITS stability."""
    if ref_audio_path.suffix.lower() == ".wav":
        return ref_audio_path
    cache_dir.mkdir(parents=True, exist_ok=True)
    wav_path = cache_dir / f"{ref_audio_path.stem}_ref.wav"
    if wav_path.exists() and wav_path.stat().st_mtime >= ref_audio_path.stat().st_mtime:
        return wav_path
    cmd = [
        "ffmpeg", "-y", "-i", str(ref_audio_path),
        "-ar", "32000", "-ac", "1", "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return wav_path


def _is_api_ready(api_url: str) -> bool:
    try:
        # Any HTTP response (even 400/404) means uvicorn is listening
        requests.get(f"{api_url.rstrip('/')}/docs", timeout=2)
        return True
    except Exception:
        return False


def _start_gptsovits_server(tts_cfg: dict[str, Any]) -> subprocess.Popen | None:
    gsv_dir = Path(tts_cfg["gptsovits_dir"])
    py_exe = Path(tts_cfg["runtime_python"])
    if not py_exe.exists():
        print(f"[tts] WARN: runtime python not found at {py_exe}")
        return None
    api_script = gsv_dir / "api_v2.py"
    if not api_script.exists():
        print(f"[tts] WARN: api_v2.py not found at {api_script}")
        return None

    print(f"[tts] Starting GPT-SoVITS api_v2.py from {gsv_dir} ...")
    proc = subprocess.Popen(
        [str(py_exe), str(api_script), "-a", "127.0.0.1", "-p", "9880"],
        cwd=str(gsv_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    api_url = tts_cfg.get("api_url", "http://127.0.0.1:9880")
    for _ in range(90):
        if _is_api_ready(api_url):
            print("[tts] GPT-SoVITS API is ready!")
            return proc
        if proc.poll() is not None:
            print(f"[tts] WARN: GPT-SoVITS exited early with code {proc.returncode}")
            return None
        time.sleep(1)
    print("[tts] WARN: Timed out waiting for GPT-SoVITS API.")
    return proc


def _configure_v5turbo_weights(tts_cfg: dict[str, Any]) -> None:
    api_url = tts_cfg.get("api_url", "http://127.0.0.1:9880").rstrip("/")
    gsv_dir = Path(tts_cfg["gptsovits_dir"])

    gpt_custom = _find_latest_weight(gsv_dir / tts_cfg.get("gpt_weights_dir", "GPT_weights_v5turbo"), (".ckpt",))
    sovits_custom = _find_latest_weight(gsv_dir / tts_cfg.get("sovits_weights_dir", "SoVITS_weights_v5turbo"), (".pth",))

    gpt_path = str(gpt_custom) if gpt_custom else tts_cfg["fallback_gpt_weights"]
    sovits_path = str(sovits_custom) if sovits_custom else tts_cfg["fallback_sovits_weights"]

    try:
        r1 = requests.get(f"{api_url}/set_gpt_weights", params={"weights_path": gpt_path}, timeout=60)
        print(f"[tts] set_gpt_weights ({Path(gpt_path).name}): {r1.status_code}")
    except Exception as exc:
        print(f"[tts] WARN: set_gpt_weights failed: {exc}")

    try:
        r2 = requests.get(f"{api_url}/set_sovits_weights", params={"weights_path": sovits_path}, timeout=60)
        print(f"[tts] set_sovits_weights ({Path(sovits_path).name}): {r2.status_code}")
    except Exception as exc:
        print(f"[tts] WARN: set_sovits_weights failed: {exc}")


def generate_placeholder_audio(output_wav: Path, duration: float = 30.0) -> Path:
    """Generate a gentle warm chord-pad WAV as fallback when TTS is skipped/unavailable."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sr = 24000
    n_samples = int(sr * duration)
    freqs = [220.0, 277.18, 329.63, 440.0]  # A major warm pad
    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sr
            env = min(1.0, t / 0.8) * min(1.0, (duration - t) / 1.0)
            lfo = 0.65 + 0.35 * math.sin(2 * math.pi * 0.4 * t)
            val = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
            sample = int(max(-1.0, min(1.0, val * 0.18 * env * lfo)) * 32767)
            frames.extend(struct.pack("<h", sample))
        wf.writeframes(bytes(frames))
    return output_wav


# Music-tech TTS pronunciation normalization (applied ONLY to TTS input, never alters on-screen subtitles)
BRAND_PRONUNCIATION = {
    "AKAI": "阿開",
    "Akai": "阿開",
    "Roland": "羅蘭",
    "Moog": "穆格",
    "Korg": "寇格",
    "Ableton": "艾伯頓",
    "Steinberg": "史坦伯格",
    "MIDI": "米迪",
    "Pad": "打擊墊",
    "Sample": "Sample",
}

POLYPHONE_FIXES = {
    "16階音階": "十六段音階",
    "16 階音階": "十六段音階",
    "16階": "十六段",
    "1.4": "一點四",
    "VST2": "V S T 二",
    "VST3": "V S T 三",
    "Mk1": "一代",
    "Mk2": "二代",
}


def _to_simplified(text: str) -> str:
    """Convert Traditional Chinese to Simplified Chinese so GPT-SoVITS's native polyphone G2P matches accurately."""
    if not text:
        return text
    try:
        import opencc
        return opencc.OpenCC("t2s").convert(text)
    except Exception:
        return text


def normalize_tts_text(text: str) -> str:
    """Normalize music-tech brands, acronyms, numbers, and convert to Simplified for clean GPT-SoVITS G2P."""
    out = text
    for src, dst in POLYPHONE_FIXES.items():
        out = out.replace(src, dst)
    for brand, pron in BRAND_PRONUNCIATION.items():
        out = re.sub(rf"\b{re.escape(brand)}\b", pron, out)

    # Space out remaining uppercase acronyms (e.g., SDK -> S D K, MPC -> M P C, DAW -> D A W)
    def _expand_acronym(m: re.Match[str]) -> str:
        token = m.group(0)
        return " ".join(list(token))

    out = re.sub(r"\b[A-Z]{2,5}[0-9]?\b", _expand_acronym, out)
    # Add light pause around English words embedded in Chinese so leading vowels are never swallowed
    out = re.sub(r"([\u4e00-\u9fff])([A-Za-z])", r"\1 \2", out)
    out = re.sub(r"([A-Za-z])([\u4e00-\u9fff])", r"\1 \2", out)
    out = re.sub(r"\s+", " ", out).strip()
    return _to_simplified(out)


def synthesize_tts(
    text: str,
    output_wav: Path,
    tts_cfg: dict[str, Any],
    cache_dir: Path,
    skip_tts: bool = False,
    target_duration: float = 30.0,
) -> tuple[Path, bool]:
    """Synthesize speech using GPT-SoVITS v5turbo. Returns (wav_path, used_gptsovits)."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    if skip_tts:
        print("[tts] --skip-tts enabled -> generating ambient placeholder audio.")
        return generate_placeholder_audio(output_wav, duration=target_duration), False

    api_url = tts_cfg.get("api_url", "http://127.0.0.1:9880").rstrip("/")
    started_proc: subprocess.Popen | None = None
    try:
        if not _is_api_ready(api_url):
            started_proc = _start_gptsovits_server(tts_cfg)
            if not _is_api_ready(api_url):
                print("[tts] WARN: GPT-SoVITS API unavailable -> using placeholder audio.")
                return generate_placeholder_audio(output_wav, duration=target_duration), False

        _configure_v5turbo_weights(tts_cfg)

        ref_src = Path(tts_cfg["ref_audio_path"])
        if not ref_src.exists():
            raise FileNotFoundError(f"Reference audio not found: {ref_src}")
        ref_wav = _ensure_wav_ref_audio(ref_src, cache_dir)

        tts_text = normalize_tts_text(text)
        print(f"[tts] Normalized TTS text: {tts_text}")

        payload = {
            "text": tts_text,
            "text_lang": tts_cfg.get("text_lang", "auto"),
            "ref_audio_path": str(ref_wav),
            "prompt_text": _to_simplified(tts_cfg.get("prompt_text", "")),
            "prompt_lang": tts_cfg.get("prompt_lang", "zh"),
            "text_split_method": "cut5",
            "batch_size": 1,
            "speed_factor": float(tts_cfg.get("speed_factor", 1.05)),
            "fragment_interval": float(tts_cfg.get("fragment_interval", 0.15)),
            "temperature": float(tts_cfg.get("temperature", 0.75)),
            "top_k": int(tts_cfg.get("top_k", 10)),
            "media_type": "wav",
            "streaming_mode": False,
        }
        print(f"[tts] Requesting GPT-SoVITS synthesis ({len(text)} chars)...")
        resp = requests.post(f"{api_url}/tts", json=payload, timeout=180)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        output_wav.write_bytes(resp.content)

        # Studio broadcast vocal cleanup: remove vocoder buzz/hum & normalize loudness
        filters: list[str] = []
        pitch_shift = float(tts_cfg.get("pitch_shift", 1.0))
        if abs(pitch_shift - 1.0) > 0.01:
            filters.append(f"asetrate=48000*{pitch_shift},aresample=48000")
        if tts_cfg.get("audio_cleanup", True):
            # Gentle broadcast EQ only (no aggressive FFT denoiser that can eat speech)
            filters.append("highpass=f=80,lowpass=f=12000")
        if filters:
            try:
                import imageio_ffmpeg
                ff_bin = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ff_bin = "ffmpeg"
            cleaned = output_wav.with_suffix(".clean.wav")
            subprocess.run(
                [
                    ff_bin, "-y", "-i", str(output_wav),
                    "-af", ",".join(filters),
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
                    str(cleaned),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            cleaned.replace(output_wav)
        print(f"[tts] Saved synthesized audio -> {output_wav}")
        return output_wav, True
    except Exception as exc:
        print(f"[tts] WARN: GPT-SoVITS failed ({exc}) -> using placeholder audio.")
        return generate_placeholder_audio(output_wav, duration=target_duration), False
    finally:
        if started_proc is not None:
            try:
                started_proc.terminate()
            except Exception:
                pass
