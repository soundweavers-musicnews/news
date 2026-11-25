"""Analyze music tech news articles using Gemini API (REST) with graceful fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


PROMPT_TEMPLATE = """你是一位專業的「音樂科技與音訊工程」新聞播報主編，請將以下英文或外語音樂科技新聞整理成繁體中文的深度播報資料。

新聞標題：{title}
來源：{source}
內文摘要：{raw_summary}

請嚴格以 JSON 格式回傳（不要加上 markdown 程式碼區塊以外的多餘文字），欄位如下：
{{
  "title_zh": "吸引人且精準的繁體中文新聞標題（25字以內）",
  "category": "從以下擇一：產品發表、AI 音樂、技術教學、硬體合成器、插件工具",
  "summary": "網站用精簡摘要（80-120字，清楚說明這是什麼產品/技術/教學以及亮點）",
  "highlights": [
    "重點一（20-35字）",
    "重點二（20-35字）",
    "重點三（20-35字）"
  ],
  "tech_analysis": "技術分析（120-180字，從 DSP、音訊演算法、工作流整合、硬體架構或音樂製作實務角度切入分析其價值與影響）",
  "broadcast_script": "30秒短影片口播稿（105-130個繁體中文字，語氣自然親切像隔壁女孩在分享音樂新知，開頭直接切入亮點，結尾一句簡短收尾，不要包含括號動作指示或表情符號）",
  "keywords": ["關鍵詞1", "關鍵詞2", "關鍵詞3"]
}}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace:
            text = brace.group(1)
    return json.loads(text)


def _fallback_analysis(article: dict[str, Any]) -> dict[str, Any]:
    title = article["title"]
    summary_raw = article.get("raw_summary", "")
    short_desc = summary_raw[:160] + ("..." if len(summary_raw) > 160 else "")
    cat = article.get("default_category", "產品發表")
    script = (
        f"哈囉大家好，歡迎來到 SoundWeavers 音樂科技速報！"
        f"今天要跟大家分享來自 {article['source']} 的最新焦點：{title}。"
        f"這項最新的音樂科技動態在製作流程與音色表現上都有不少亮點，"
        f"非常值得音樂製作人與音訊工程師關注。想看完整技術分析，記得點進網站看看喔！"
    )
    return {
        "title_zh": title,
        "category": cat,
        "summary": short_desc or f"來自 {article['source']} 的最新音樂科技報導：{title}。",
        "highlights": [
            f"消息來源：{article['source']}",
            "涵蓋最新音樂科技產品或製作技術動態",
            "設定 GEMINI_API_KEY 後將自動產出完整繁體中文重點整理",
        ],
        "tech_analysis": (
            f"本篇報導聚焦於 {title}。目前以離線備援模式呈現原文重點；"
            "啟用 Gemini API 後，系統將自動從音訊 DSP、軟硬體架構與 DAW 實戰工作流角度提供深度技術解析。"
        ),
        "broadcast_script": script,
        "keywords": [cat, article["source"], "MusicTech"],
        "analyzed_by": "fallback",
    }


def analyze_article(
    article: dict[str, Any],
    api_key_env: str = "GEMINI_API_KEY",
    model: str = "gemini-2.5-flash",
    timeout_seconds: int = 45,
) -> dict[str, Any]:
    """Enrich an article with Traditional Chinese summary, tech analysis, and 30s script."""
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        print(f"[analyze] {api_key_env} not set -> using fallback for: {article['title'][:50]}")
        return {**article, **_fallback_analysis(article)}

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    prompt = PROMPT_TEMPLATE.format(
        title=article["title"],
        source=article["source"],
        raw_summary=article.get("raw_summary", "")[:1200],
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _extract_json(raw_text)
        parsed["analyzed_by"] = model
        print(f"[analyze] Gemini OK: {parsed.get('title_zh', article['title'])[:40]}")
        return {**article, **parsed}
    except Exception as exc:
        print(f"[analyze] WARN: Gemini API failed ({exc}), falling back.")
        return {**article, **_fallback_analysis(article)}
