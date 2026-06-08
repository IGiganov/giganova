from datetime import datetime, timezone

import yfinance as yf

from app.config import settings


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()[:12]


def get_quote(ticker: str) -> dict:
    symbol = _normalize_ticker(ticker)
    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        fast = stock.fast_info

        price = info.get("regularMarketPrice")
        prev_close = info.get("regularMarketPreviousClose")
        if price is None:
            price = getattr(fast, "last_price", None)
        if prev_close is None:
            prev_close = getattr(fast, "previous_close", None)
    except Exception as exc:
        return {
            "ticker": symbol,
            "error": f"Quote unavailable: {exc}",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    change_pct = None
    if price is not None and prev_close:
        change_pct = round(((price - prev_close) / prev_close) * 100, 2)

    return {
        "ticker": symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "price": round(float(price), 2) if price is not None else None,
        "currency": info.get("currency", "USD"),
        "change_pct_day": change_pct,
        "market_state": info.get("marketState"),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def get_price_summary(ticker: str, period: str = "1mo") -> dict:
    symbol = _normalize_ticker(ticker)
    hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    if hist.empty:
        return {"ticker": symbol, "period": period, "error": "No price history found."}

    start = float(hist["Close"].iloc[0])
    end = float(hist["Close"].iloc[-1])
    high = float(hist["High"].max())
    low = float(hist["Low"].min())
    change_pct = round(((end - start) / start) * 100, 2) if start else None

    return {
        "ticker": symbol,
        "period": period,
        "start_close": round(start, 2),
        "latest_close": round(end, 2),
        "period_change_pct": change_pct,
        "period_high": round(high, 2),
        "period_low": round(low, 2),
        "sessions": len(hist),
    }


def compare_tickers(tickers: list[str], period: str = "1mo") -> dict:
    limited = [_normalize_ticker(t) for t in tickers[: settings.max_tickers_per_request]]
    rows = [get_price_summary(t, period=period) for t in limited]
    return {"period": period, "comparisons": rows}
