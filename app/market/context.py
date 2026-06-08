from typing import Any, Dict, List

from app.config import settings
from app.market.news import get_news_with_fallback
from app.market.quotes import get_price_summary, get_quote
from app.market.resolver import symbol_label

# Primary index ticker -> alternate tickers to try for news
NEWS_FALLBACKS = {
    "^GSPC": ["^GSPC", "SPY"],
    "^IXIC": ["^IXIC", "QQQ"],
    "^DJI": ["^DJI", "DIA"],
    "^RUT": ["^RUT", "IWM"],
    "SPY": ["SPY", "^GSPC"],
    "QQQ": ["QQQ", "^IXIC"],
}


def _news_fallbacks(ticker: str) -> List[str]:
    return NEWS_FALLBACKS.get(ticker, [ticker])


def _symbol_has_data(quote: dict, price_summary: dict, news: dict) -> bool:
    has_price = quote.get("price") is not None or "error" not in price_summary
    has_news = news.get("count", 0) > 0
    return has_price or has_news

def build_market_context(tickers: List[str], period: str) -> Dict[str, Any]:
    symbols = []
    for ticker in tickers[: settings.max_tickers_per_request]:
        quote = get_quote(ticker)
        price_summary = get_price_summary(ticker, period=period)
        news = get_news_with_fallback(ticker, fallbacks=_news_fallbacks(ticker))

        gaps = []
        if quote.get("price") is None:
            gaps.append("no_quote")
        if price_summary.get("error"):
            gaps.append("no_price_history")
        if news.get("count", 0) == 0:
            gaps.append("no_news")

        symbols.append(
            {
                "ticker": ticker,
                "label": symbol_label(ticker),
                "quote": quote,
                "price_summary": price_summary,
                "news": news,
                "news_source_ticker": news.get("source_ticker"),
                "gaps": gaps,
            }
        )

    has_any_data = any(_symbol_has_data(s["quote"], s["price_summary"], s["news"]) for s in symbols)

    return {
        "period": period,
        "symbols": symbols,
        "has_any_data": has_any_data,
    }
