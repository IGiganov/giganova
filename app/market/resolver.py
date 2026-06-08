import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

INDEX_ALIASES: List[Tuple[List[str], List[str]]] = [
    (["s&p 500", "s&p500", "sp500", "sp 500", "s&p", "spx"], ["^GSPC"]),
    (["nasdaq composite", "nasdaq", "ndx"], ["^IXIC"]),
    (["dow jones", "djia", "dow"], ["^DJI"]),
    (["russell 2000", "russell"], ["^RUT"]),
    (["stock market", "equity market", "equities", "the market", "markets", "market"], ["^GSPC", "^IXIC"]),
]

COMPANY_ALIASES: List[Tuple[List[str], str]] = [
    (["apple"], "AAPL"),
    (["microsoft"], "MSFT"),
    (["google", "alphabet"], "GOOGL"),
    (["amazon"], "AMZN"),
    (["nvidia"], "NVDA"),
    (["meta", "facebook"], "META"),
    (["tesla"], "TSLA"),
    (["netflix"], "NFLX"),
    (["amd"], "AMD"),
    (["intel"], "INTC"),
    (["oracle"], "ORCL"),
]

SYMBOL_LABELS = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ Composite",
    "^DJI": "Dow Jones Industrial Average",
    "^RUT": "Russell 2000",
    "SPY": "S&P 500 ETF (SPY)",
    "QQQ": "NASDAQ ETF (QQQ)",
    "DIA": "Dow ETF (DIA)",
}

TICKER_STOPWORDS = {
    "A", "I", "AM", "PM", "AI", "US", "UK", "EU", "CEO", "CFO", "ETF", "IPO", "GDP", "CPI",
    "FED", "SEC", "USD", "EUR", "GBP", "YOY", "QOQ", "MOM", "YTD", "ATH", "PE", "EPS",
    "NYSE", "NASDAQ", "ASDAQ", "NDAQ", "NASD", "DOW", "RUT", "SPX", "NDX", "WHAT", "WITH",
    "LAST", "WEEK", "THIS", "THAT", "THE", "FOR", "AND",
}

MARKET_KEYWORDS = [
    "stock", "stocks", "market", "markets", "ticker", "price", "trading", "index", "indices",
    "nasdaq", "s&p", "sp500", "dow", "equity", "equities", "headline", "headlines", "news",
    "rally", "selloff", "sell-off", "portfolio", "share", "shares", "happened", "performance",
]

QUERY_TYPO_FIXES = {
    "nsadaq": "nasdaq",
    "nadsaq": "nasdaq",
    "nasdaw": "nasdaq",
    "nasdaqq": "nasdaq",
    "nysaq": "nasdaq",
    "sp5oo": "sp500",
    "sp5000": "sp500",
    "snp 500": "s&p 500",
    "s and p": "s&p",
    "sandp": "s&p",
}

SUBJECT_PATTERN = re.compile(r"\b(?:with|for|about|on)\s+(\^?[A-Za-z]{2,10})\b", re.I)


@dataclass
class QueryResolution:
    tickers: List[str]
    period: str
    corrections: List[str] = field(default_factory=list)
    unresolved: Optional[str] = None
    broad_market: bool = False


def _normalize_query(message: str) -> str:
    lower = message.lower()
    for typo, fixed in QUERY_TYPO_FIXES.items():
        lower = lower.replace(typo, fixed)
    return lower


def _detect_corrections(message: str) -> List[str]:
    lower = message.lower()
    corrections = []
    for typo, fixed in QUERY_TYPO_FIXES.items():
        if typo != fixed and typo in lower:
            corrections.append(f"{typo.upper()} → {fixed.upper()}")
    return corrections


def infer_period(message: str) -> str:
    lower = _normalize_query(message)
    if any(p in lower for p in ["last week", "past week", "this week", "weekly", "week"]):
        return "5d"
    if any(p in lower for p in ["last month", "past month", "this month", "monthly", "month"]):
        return "1mo"
    if any(p in lower for p in ["3 months", "three months", "quarter", "3mo"]):
        return "3mo"
    if any(p in lower for p in ["6 months", "six months", "half year"]):
        return "6mo"
    if any(p in lower for p in ["year", "12 months", "1y", "annual"]):
        return "1y"
    if any(p in lower for p in ["today", "yesterday", "daily", "day"]):
        return "5d"
    return "1mo"


def _match_aliases(text: str) -> List[str]:
    lower = _normalize_query(text)
    found: List[str] = []
    for phrases, tickers in INDEX_ALIASES:
        if any(phrase in lower for phrase in phrases):
            for ticker in tickers:
                if ticker not in found:
                    found.append(ticker)
    return found


def _match_companies(text: str) -> List[str]:
    lower = _normalize_query(text)
    found: List[str] = []
    for names, ticker in COMPANY_ALIASES:
        if any(name in lower for name in names):
            if ticker not in found:
                found.append(ticker)
    return found


def _match_explicit_tickers(text: str) -> List[str]:
    found: List[str] = []
    for match in re.finditer(r"\^[A-Z]+\b", text):
        symbol = match.group().upper()
        if symbol not in found:
            found.append(symbol)
    for match in re.finditer(r"\b[A-Z]{1,5}\b", text):
        symbol = match.group().upper()
        if symbol in TICKER_STOPWORDS:
            continue
        if symbol not in found:
            found.append(symbol)
    return found


def _lookup_tickers(text: str, allow_broad_default: bool = False) -> List[str]:
    tickers = _match_aliases(text)
    for ticker in _match_companies(text):
        if ticker not in tickers:
            tickers.append(ticker)
    for ticker in _match_explicit_tickers(text):
        if ticker not in tickers:
            tickers.append(ticker)
    if not tickers and allow_broad_default and is_market_question(text):
        tickers = ["^GSPC", "^IXIC"]
    return tickers[:5]


def _extract_subject(message: str) -> Optional[str]:
    match = SUBJECT_PATTERN.search(message)
    return match.group(1) if match else None


def _resolve_subject(subject: str, corrections: List[str]) -> List[str]:
    tickers = _lookup_tickers(subject, allow_broad_default=False)
    if tickers:
        return tickers

    normalized = _normalize_query(subject)
    if normalized != subject.lower().strip():
        tickers = _lookup_tickers(normalized, allow_broad_default=False)
        if tickers:
            corrections.append(f"{subject.upper()} → {normalized.upper()}")
    return tickers


def is_market_question(message: str) -> bool:
    lower = _normalize_query(message)
    if _lookup_tickers(message, allow_broad_default=False):
        return True
    return any(keyword in lower for keyword in MARKET_KEYWORDS)


def resolve_query_full(message: str) -> QueryResolution:
    corrections = _detect_corrections(message)
    period = infer_period(message)
    subject = _extract_subject(message)

    if subject:
        if not _resolve_subject(subject, corrections):
            return QueryResolution([], period, corrections, unresolved=subject)

    tickers = _lookup_tickers(message, allow_broad_default=False)
    if not tickers and is_market_question(message):
        tickers = ["^GSPC", "^IXIC"]
        return QueryResolution(tickers, period, corrections, broad_market=True)

    return QueryResolution(tickers, period, corrections)


def resolve_tickers(message: str) -> List[str]:
    return resolve_query_full(message).tickers


def resolve_query(message: str) -> Tuple[List[str], str]:
    resolution = resolve_query_full(message)
    return resolution.tickers, resolution.period


def symbol_label(ticker: str) -> str:
    return SYMBOL_LABELS.get(ticker, ticker)
