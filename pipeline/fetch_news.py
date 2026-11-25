"""Fetch recent music technology news, product launches, and tutorials from RSS feeds."""

from __future__ import annotations

import email.utils
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36 SoundWeaversNewsBot/1.0"
)

MUSIC_TECH_KEYWORDS = [
    "synth", "plugin", "vst", "daw", "midi", "audio", "ai", "dsp",
    "ableton", "logic", "cubase", "fl studio", "sampler", "drum",
    "modular", "eurorack", "tutorial", "mix", "master", "reverb",
    "eq", "compressor", "controller", "interface", "guitar", "pedal",
    "music", "sound", "spatial", "stem", "vocal", "production",
]


def _clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # ISO-8601 fallback (Atom feeds)
    try:
        iso = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _text(elem: ET.Element | None, *tags: str) -> str:
    if elem is None:
        return ""
    for tag in tags:
        found = elem.find(tag)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _parse_feed_xml(xml_bytes: bytes, source_name: str, default_category: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    root = ET.fromstring(xml_bytes)

    # RSS 2.0 <item>
    rss_items = root.findall(".//item")
    if rss_items:
        for item in rss_items:
            title = _clean_html(_text(item, "title"))
            link = _text(item, "link")
            pub_raw = _text(item, "pubDate", "{http://purl.org/dc/elements/1.1/}date")
            desc = _text(
                item,
                "{http://purl.org/rss/1.0/modules/content/}encoded",
                "description",
            )
            pub_dt = _parse_date(pub_raw)
            if not title or not link:
                continue
            items.append(
                {
                    "id": hashlib.sha1(link.encode("utf-8")).hexdigest()[:12],
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "default_category": default_category,
                    "published_at": pub_dt.isoformat() if pub_dt else None,
                    "published_dt": pub_dt,
                    "raw_summary": _clean_html(desc)[:1500],
                }
            )
        return items

    # Atom <entry>
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = _clean_html(_text(entry, "atom:title"))
        link_el = entry.find("atom:link", ns)
        link = link_el.attrib.get("href", "").strip() if link_el is not None else ""
        pub_raw = _text(entry, "atom:published", "atom:updated")
        desc = _text(entry, "atom:content", "atom:summary")
        pub_dt = _parse_date(pub_raw)
        if not title or not link:
            continue
        items.append(
            {
                "id": hashlib.sha1(link.encode("utf-8")).hexdigest()[:12],
                "title": title,
                "url": link,
                "source": source_name,
                "default_category": default_category,
                "published_at": pub_dt.isoformat() if pub_dt else None,
                "published_dt": pub_dt,
                "raw_summary": _clean_html(desc)[:1500],
            }
        )
    return items


def _relevance_score(article: dict[str, Any]) -> int:
    haystack = f"{article['title']} {article['raw_summary']}".lower()
    score = sum(1 for kw in MUSIC_TECH_KEYWORDS if kw in haystack)
    return score


def fetch_recent_news(
    feeds: list[dict[str, str]],
    days_lookback: int = 7,
    max_articles: int = 5,
    existing_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch, deduplicate, and rank recent music tech articles."""
    existing_ids = existing_ids or set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback)
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set(existing_ids)

    for feed in feeds:
        url = feed["url"]
        name = feed["name"]
        default_cat = feed.get("default_category", "產品發表")
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            parsed = _parse_feed_xml(resp.content, name, default_cat)
            print(f"[fetch] {name}: {len(parsed)} items fetched")
            for art in parsed:
                if art["id"] in seen_ids:
                    continue
                pub_dt = art.get("published_dt")
                if pub_dt is not None and pub_dt < cutoff:
                    continue
                seen_ids.add(art["id"])
                collected.append(art)
        except Exception as exc:
            print(f"[fetch] WARN: failed to fetch {name} ({url}): {exc}")

    # Sort by recency + relevance
    def sort_key(a: dict[str, Any]) -> tuple[float, int]:
        dt = a.get("published_dt")
        ts = dt.timestamp() if dt else 0.0
        return (ts, _relevance_score(a))

    collected.sort(key=sort_key, reverse=True)

    # Strip non-JSON-serializable datetime object before returning
    results: list[dict[str, Any]] = []
    for art in collected[:max_articles]:
        clean = {k: v for k, v in art.items() if k != "published_dt"}
        if not clean["published_at"]:
            clean["published_at"] = datetime.now(timezone.utc).isoformat()
        results.append(clean)

    return results
