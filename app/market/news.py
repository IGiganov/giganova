from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

from app.config import settings
from app.market.quotes import _normalize_ticker


def get_news(ticker: str, limit: Optional[int] = None) -> dict:
    symbol = _normalize_ticker(ticker)
    max_items = min(limit or settings.max_news_items, settings.max_news_items)
    raw = yf.Ticker(symbol).news or []

    items = []
    for item in raw[:max_items]:
        content = item.get("content") or {}
        title = content.get("title") or item.get("title") or "Untitled"
        summary = content.get("summary") or item.get("summary") or ""
        if len(summary) > settings.news_summary_max_chars:
            summary = summary[: settings.news_summary_max_chars].rstrip() + "..."

        pub_date = content.get("pubDate") or item.get("providerPublishTime")
        publisher = (content.get("provider") or {}).get("displayName") or item.get("publisher")

        items.append(
            {
                "title": title,
                "summary": summary,
                "publisher": publisher,
                "published_at": pub_date,
            }
        )

    return {
        "ticker": symbol,
        "count": len(items),
        "headlines": items,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def get_news_with_fallback(ticker: str, fallbacks: Optional[list] = None, limit: Optional[int] = None) -> dict:
    candidates = []
    for symbol in [ticker] + (fallbacks or []):
        normalized = _normalize_ticker(symbol)
        if normalized not in candidates:
            candidates.append(normalized)

    for symbol in candidates:
        result = get_news(symbol, limit=limit)
        if result["count"] > 0:
            result["source_ticker"] = symbol
            result["requested_ticker"] = _normalize_ticker(ticker)
            return result

    return {
        "ticker": _normalize_ticker(ticker),
        "requested_ticker": _normalize_ticker(ticker),
        "source_ticker": None,
        "count": 0,
        "headlines": [],
        "as_of": datetime.now(timezone.utc).isoformat(),
        "error": "No news found.",
    }
