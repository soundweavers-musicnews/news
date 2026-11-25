"""Main daily orchestrator for SoundWeavers Music Tech News."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Allow running as `python pipeline/run_daily.py` from repo root
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.analyze_news import analyze_article
from pipeline.fetch_news import fetch_recent_news
from pipeline.tts_gptsovits import synthesize_tts
from pipeline.video_handdrawn import render_handdrawn_video


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_existing_data(data_file: Path) -> dict[str, Any]:
    if data_file.exists():
        try:
            return json.loads(data_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated_at": None, "site": {}, "items": []}


def run_pipeline(
    config_path: Path,
    skip_tts: bool = False,
    skip_video: bool = False,
    max_articles_override: int | None = None,
    from_json: Path | None = None,
) -> None:
    cfg = load_config(config_path)
    data_file = ROOT_DIR / cfg["site"]["data_file"]
    media_dir = ROOT_DIR / cfg["site"]["media_dir"]
    cache_dir = ROOT_DIR / ".cache"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    existing = load_existing_data(data_file)
    existing_items: list[dict[str, Any]] = existing.get("items", [])
    existing_ids = {item["id"] for item in existing_items if "id" in item}

    news_cfg = cfg["news"]
    max_articles = max_articles_override or int(news_cfg.get("max_articles_per_run", 5))
    videos_per_run = int(news_cfg.get("videos_per_run", 1))

    if from_json is not None:
        print(f"=== [1-2/4] Loading pre-analyzed articles from {from_json} (no API key needed) ===")
        enriched = json.loads(from_json.read_text(encoding="utf-8"))
        for item in enriched:
            item.setdefault("fetched_at", datetime.now(timezone.utc).isoformat())
    else:
        print("=== [1/4] Fetching recent music tech news ===")
        raw_articles = fetch_recent_news(
            feeds=news_cfg["feeds"],
            days_lookback=int(news_cfg.get("days_lookback", 7)),
            max_articles=max_articles,
            existing_ids=existing_ids,
        )
        if not raw_articles:
            print("[pipeline] No new articles found since last run.")
            return

        print(f"=== [2/4] Analyzing {len(raw_articles)} articles ===")
        gemini_cfg = cfg.get("gemini", {})
        enriched: list[dict[str, Any]] = []
        for art in raw_articles:
            analyzed = analyze_article(
                art,
                api_key_env=gemini_cfg.get("api_key_env", "GEMINI_API_KEY"),
                model=gemini_cfg.get("model", "gemini-2.5-flash"),
                timeout_seconds=int(gemini_cfg.get("timeout_seconds", 45)),
            )
            analyzed["fetched_at"] = datetime.now(timezone.utc).isoformat()
            enriched.append(analyzed)

    print("=== [3/4] Generating TTS & 30s hand-drawn short videos ===")
    today_str = datetime.now().strftime("%Y%m%d")
    for idx, item in enumerate(enriched):
        if idx >= videos_per_run or skip_video:
            item["video_url"] = None
            item["audio_url"] = None
            item["video_duration"] = None
            continue

        stem = f"{today_str}_{item['id']}"
        wav_path = media_dir / f"{stem}.wav"
        mp4_path = media_dir / f"{stem}.mp4"

        wav_out, used_gsv = synthesize_tts(
            text=item["broadcast_script"],
            output_wav=wav_path,
            tts_cfg=cfg["tts"],
            cache_dir=cache_dir,
            skip_tts=skip_tts,
            target_duration=float(cfg["video"].get("target_duration", 30.0)),
        )
        _, dur = render_handdrawn_video(
            article=item,
            wav_path=wav_out,
            output_mp4=mp4_path,
            video_cfg=cfg["video"],
        )
        # Strictly relative paths so site works under `/` or `/news/`
        item["video_url"] = f"./media/{mp4_path.name}"
        item["audio_url"] = f"./media/{wav_out.name}"
        item["video_duration"] = dur
        item["tts_engine"] = "GPT-SoVITS-v5turbo" if used_gsv else "placeholder"

    print("=== [4/4] Updating site/data/news.json ===")
    max_archive = int(cfg["site"].get("max_archive_items", 60))
    merged = enriched + existing_items
    merged = merged[:max_archive]

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "site": {
            "title": cfg["site"]["title"],
            "subtitle": cfg["site"]["subtitle"],
        },
        "items": merged,
    }
    data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[pipeline] Successfully wrote {len(merged)} items to {data_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SoundWeavers Daily Music Tech News Pipeline")
    parser.add_argument("--config", default=str(ROOT_DIR / "config.yaml"))
    parser.add_argument("--skip-tts", action="store_true", help="Skip GPT-SoVITS and use ambient placeholder audio")
    parser.add_argument("--skip-video", action="store_true", help="Skip video generation")
    parser.add_argument("--max-articles", type=int, default=None, help="Override max articles per run")
    parser.add_argument("--from-json", type=str, default=None, help="Load pre-analyzed articles JSON (no Gemini API key needed)")
    args = parser.parse_args()

    run_pipeline(
        config_path=Path(args.config),
        skip_tts=args.skip_tts,
        skip_video=args.skip_video,
        max_articles_override=args.max_articles,
        from_json=Path(args.from_json) if args.from_json else None,
    )


if __name__ == "__main__":
    main()
