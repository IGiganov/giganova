import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import settings
from app.market.ticker_registry import get_registry

INDEX_ALIASES: List[Tuple[List[str], List[str]]] = []

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
    "LAST", "WEEK", "THIS", "THAT", "THE", "FOR", "AND", "COMPARE",
}

MARKET_KEYWORDS = [
    "stock", "stocks", "market", "markets", "ticker", "price", "trading", "index", "indices",
    "nasdaq", "s&p", "sp500", "dow", "equity", "equities", "headline", "headlines", "news",
    "rally", "selloff", "sell-off", "portfolio", "share", "shares", "happened", "performance",
]

COMMON_QUERY_WORDS = {
    "stock", "stocks", "market", "markets", "ticker", "price", "trading", "index", "indices",
    "equity", "equities", "headline", "headlines", "news", "performance", "happened", "happens",
    "happen", "last", "past", "this", "that", "week", "month", "year", "today", "yesterday",
    "daily", "weekly", "monthly", "annual", "quarter", "quarterly", "tell", "show", "give",
    "what", "when", "where", "which", "would", "could", "should", "about", "with", "from",
    "have", "been", "were", "will", "doing", "done", "going", "like", "just", "also", "more",
    "some", "any", "much", "many", "very", "over", "under", "into", "your", "please", "help",
    "compare", "versus", "against", "move", "moved", "moving", "change", "changed", "update",
}

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

SUBJECT_PATTERN = re.compile(
    r"\b(?:with|for|about|on)\s+(\^?[A-Za-z0-9]{1,12}(?:\.[A-Za-z]{1,4})?)\b",
    re.I,
)
EXPLICIT_TICKER_PATTERN = re.compile(
    r"\b(\^?[A-Z0-9][A-Z0-9]{0,11}(?:\.[A-Z]{1,4})?)\b"
)


@dataclass
class QueryResolution:
    tickers: List[str]
    period: str
    corrections: List[str] = field(default_factory=list)
    unresolved: Optional[str] = None
    broad_market: bool = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _project_root() / candidate


def load_index_aliases() -> None:
    global INDEX_ALIASES

    path = _resolve_path(settings.index_aliases_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    INDEX_ALIASES = [
        (entry["phrases"], entry["tickers"])
        for entry in raw
        if entry.get("phrases") and entry.get("tickers")
    ]


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
    return get_registry().match_companies(_normalize_query(text))


def _match_explicit_tickers(text: str) -> List[str]:
    registry = get_registry()
    upper = text.upper()
    matches = [
        match.group(1)
        for match in EXPLICIT_TICKER_PATTERN.finditer(upper)
        if match.group(1) not in TICKER_STOPWORDS
    ]
    matches.sort(key=len, reverse=True)

    found: List[str] = []
    for symbol in matches:
        if any(symbol != other and symbol in other for other in found):
            continue
        if registry.tickers and not registry.is_known_ticker(symbol):
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


def _is_broad_market_query(message: str) -> bool:
    lower = _normalize_query(message)
    broad_phrases = [
        "stock market", "equity market", "equities", "the market", "markets", "market",
        "how is the market", "how's the market", "what happened in the market",
        "what happened to the market", "u.s. market", "us market",
    ]
    return any(phrase in lower for phrase in broad_phrases)


def _likely_specific_security_mention(message: str) -> bool:
    if _extract_subject(message):
        return True
    if _match_explicit_tickers(message):
        return True
    lower = _normalize_query(message)
    for word in re.findall(r"\b[a-z]{4,}\b", lower):
        if word not in MARKET_KEYWORDS and word not in COMMON_QUERY_WORDS:
            return True
    return False


def _guess_unresolved_token(message: str) -> Optional[str]:
    subject = _extract_subject(message)
    if subject:
        return subject
    lower = _normalize_query(message)
    for word in re.findall(r"\b[a-z]{4,}\b", lower):
        if word not in MARKET_KEYWORDS and word not in COMMON_QUERY_WORDS:
            return word
    return None


def resolve_query_full(message: str) -> QueryResolution:
    corrections = _detect_corrections(message)
    period = infer_period(message)
    subject = _extract_subject(message)

    if subject:
        if not _resolve_subject(subject, corrections):
            return QueryResolution([], period, corrections, unresolved=subject)

    tickers = _lookup_tickers(message, allow_broad_default=False)
    if not tickers and is_market_question(message):
        if _likely_specific_security_mention(message):
            return QueryResolution(
                [],
                period,
                corrections,
                unresolved=_guess_unresolved_token(message) or "that symbol",
            )
        if _is_broad_market_query(message):
            tickers = ["^GSPC", "^IXIC"]
            return QueryResolution(tickers, period, corrections, broad_market=True)

    return QueryResolution(tickers, period, corrections)


def resolve_tickers(message: str) -> List[str]:
    return resolve_query_full(message).tickers


def resolve_query(message: str) -> Tuple[List[str], str]:
    resolution = resolve_query_full(message)
    return resolution.tickers, resolution.period


def symbol_label(ticker: str) -> str:
    registry = get_registry()
    if ticker in SYMBOL_LABELS:
        return SYMBOL_LABELS[ticker]
    return registry.names.get(ticker, ticker)
