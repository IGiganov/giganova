import csv
import io
import json
import logging
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings

logger = logging.getLogger(__name__)

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

COMPANY_SUFFIXES = re.compile(
    r"\b("
    r"inc\.?|corp\.?|corporation|ltd\.?|limited|plc|co\.?|company|"
    r"holdings?|group|trust|fund|lp|llc|n\.?v\.?|sa|se|ag"
    r")\b",
    re.I,
)

FALLBACK_ALIASES = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "amazon": "AMZN",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "netflix": "NFLX",
    "amd": "AMD",
    "intel": "INTC",
    "oracle": "ORCL",
}

_refresh_lock = threading.Lock()
_refresh_thread: Optional[threading.Thread] = None


@dataclass
class TickerRegistry:
    tickers: Set[str] = field(default_factory=set)
    names: Dict[str, str] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)
    override_phrases: List[Tuple[str, str]] = field(default_factory=list)
    alias_phrases: List[Tuple[str, str]] = field(default_factory=list)
    alias_index: DefaultDict[str, List[Tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))
    fetched_at: Optional[str] = None
    sources: List[str] = field(default_factory=list)
    from_cache: bool = False
    refresh_error: Optional[str] = None
    refresh_in_progress: bool = False
    us_ticker_count: int = 0
    international_ticker_count: int = 0

    def status(self) -> dict:
        cache_age_hours = None
        refresh_due = False
        if self.fetched_at:
            try:
                fetched = datetime.fromisoformat(self.fetched_at)
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                cache_age_hours = round(
                    (datetime.now(timezone.utc) - fetched).total_seconds() / 3600,
                    1,
                )
                refresh_due = cache_age_hours >= settings.ticker_registry_max_age_hours
            except ValueError:
                refresh_due = True

        return {
            "loaded": bool(self.tickers or self.aliases),
            "fetched_at": self.fetched_at,
            "cache_age_hours": cache_age_hours,
            "refresh_due": refresh_due,
            "refresh_in_progress": self.refresh_in_progress,
            "max_age_hours": settings.ticker_registry_max_age_hours,
            "sources": self.sources,
            "from_cache": self.from_cache,
            "ticker_count": len(self.tickers),
            "us_ticker_count": self.us_ticker_count,
            "international_ticker_count": self.international_ticker_count,
            "alias_count": len(self.aliases),
            "refresh_error": self.refresh_error,
        }

    def match_companies(self, text: str) -> List[str]:
        lower = text.lower()
        found: List[str] = []
        seen_phrases: Set[str] = set()

        for phrase, ticker in self.override_phrases:
            if _phrase_matches(lower, phrase) and ticker not in found:
                found.append(ticker)
                seen_phrases.add(phrase)

        tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", lower))

        for phrase, ticker in self.alias_phrases:
            if " " in phrase and phrase in lower:
                if phrase not in seen_phrases and ticker not in found:
                    found.append(ticker)
                    seen_phrases.add(phrase)

        for token in tokens:
            for phrase, ticker in self.alias_index.get(token, []):
                if phrase in seen_phrases:
                    continue
                if _phrase_matches(lower, phrase) and ticker not in found:
                    found.append(ticker)
                    seen_phrases.add(phrase)

        return found

    def is_known_ticker(self, symbol: str) -> bool:
        if symbol.startswith("^"):
            return True
        if symbol in self.tickers:
            return True
        if re.match(r"^[A-Z0-9]{1,12}\.[A-Z]{1,4}$", symbol):
            return True
        return False


_registry = TickerRegistry()


def get_registry() -> TickerRegistry:
    return _registry


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _project_root() / candidate


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": settings.ticker_registry_user_agent})
    with urlopen(request, timeout=settings.ticker_registry_timeout_seconds) as response:
        return response.read().decode("utf-8")


def _fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": settings.ticker_registry_user_agent})
    with urlopen(request, timeout=settings.ticker_registry_timeout_seconds) as response:
        return response.read()


def _normalize_company_name(title: str) -> str:
    cleaned = title.lower()
    cleaned = re.sub(r"[^\w\s&]", " ", cleaned)
    cleaned = COMPANY_SUFFIXES.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _add_alias(aliases: Dict[str, str], phrase: str, ticker: str) -> None:
    phrase = phrase.strip().lower()
    if len(phrase) < 3:
        return
    existing = aliases.get(phrase)
    if existing and existing != ticker:
        return
    aliases[phrase] = ticker


def _build_aliases_from_name(
    title: str,
    ticker: str,
    aliases: Dict[str, str],
    reserved_phrases: Set[str],
) -> None:
    normalized = _normalize_company_name(title)
    if not normalized or normalized in reserved_phrases:
        return
    _add_alias(aliases, normalized, ticker)


def _parse_symbol_directory(text: str, symbol_index: int = 0, name_index: int = 1) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    for line in text.strip().splitlines()[1:]:
        if not line or line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) <= max(symbol_index, name_index):
            continue
        symbol = parts[symbol_index].strip()
        name = parts[name_index].strip()
        if symbol and name and symbol != "Symbol":
            rows.append((symbol.upper(), name))
    return rows


def _phrase_matches(text: str, phrase: str) -> bool:
    if " " in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _load_index_phrases() -> Set[str]:
    path = _resolve_path(settings.index_aliases_path)
    if not path.exists():
        return set()
    raw = json.loads(path.read_text(encoding="utf-8"))
    phrases: Set[str] = set()
    for entry in raw:
        for phrase in entry.get("phrases", []):
            phrases.add(str(phrase).lower())
    return phrases


def _load_json_dict(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {path}")
    return {str(key): value for key, value in data.items()}


def _load_exchange_suffix_maps() -> Tuple[Dict[str, str], Dict[str, str]]:
    exchange_suffixes = {
        key.upper(): value
        for key, value in _load_json_dict(_resolve_path(settings.exchange_yahoo_suffixes_path)).items()
    }
    country_suffixes = _load_json_dict(_resolve_path(settings.euronext_country_suffixes_path))
    return exchange_suffixes, country_suffixes


def _load_company_overrides() -> Dict[str, str]:
    path = _resolve_path(settings.company_overrides_path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(key).lower(): str(value).upper() for key, value in data.items()}


def _load_override_phrases() -> List[Tuple[str, str]]:
    phrases = [
        (phrase, ticker)
        for phrase, ticker in _load_company_overrides().items()
    ]
    return sorted(phrases, key=lambda item: len(item[0]), reverse=True)
def _merge_overrides(aliases: Dict[str, str], tickers: Optional[Set[str]] = None) -> List[Tuple[str, str]]:
    override_phrases: List[Tuple[str, str]] = []
    for phrase, ticker in _load_company_overrides().items():
        phrase = phrase.strip().lower()
        ticker = ticker.upper()
        aliases[phrase] = ticker
        if tickers is not None:
            tickers.add(ticker)
        override_phrases.append((phrase, ticker))
    return sorted(override_phrases, key=lambda item: len(item[0]), reverse=True)


def _yahoo_suffix_for_exchange(
    exchange: str,
    country: str,
    exchange_suffixes: Dict[str, str],
    country_suffixes: Dict[str, str],
) -> Optional[str]:
    exchange_key = exchange.strip().upper()
    if exchange_key == "EURONEXT":
        return country_suffixes.get(country.strip(), ".PA")
    if exchange_key not in exchange_suffixes:
        return None
    return exchange_suffixes[exchange_key]


def _to_yahoo_symbol(
    ticker: str,
    exchange: str,
    country: str,
    exchange_suffixes: Dict[str, str],
    country_suffixes: Dict[str, str],
) -> Optional[str]:
    suffix = _yahoo_suffix_for_exchange(exchange, country, exchange_suffixes, country_suffixes)
    if suffix is None:
        return None
    symbol = ticker.strip().upper()
    if not symbol:
        return None
    if suffix == "":
        return symbol
    return f"{symbol}{suffix}"


def _fetch_sec_companies() -> List[Tuple[str, str]]:
    sec_raw = json.loads(_fetch_text(SEC_COMPANY_TICKERS_URL))
    rows: List[Tuple[str, str]] = []
    for entry in sec_raw.values():
        rows.append((str(entry["ticker"]).upper(), str(entry["title"]).strip()))
    return rows


def _ingest_us_sources(
    tickers: Set[str],
    names: Dict[str, str],
    aliases: Dict[str, str],
    reserved_phrases: Set[str],
    sources: List[str],
) -> None:
    try:
        for ticker, title in _fetch_sec_companies():
            tickers.add(ticker)
            names[ticker] = title
            _build_aliases_from_name(title, ticker, aliases, reserved_phrases)
        sources.append("sec.gov/files/company_tickers.json")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("SEC ticker list unavailable, continuing with NASDAQ lists: %s", exc)

    for url, parser in (
        (NASDAQ_LISTED_URL, lambda text: _parse_symbol_directory(text, 0, 1)),
        (OTHER_LISTED_URL, lambda text: _parse_symbol_directory(text, 0, 1)),
    ):
        rows = parser(_fetch_text(url))
        sources.append(url)
        for ticker, title in rows:
            tickers.add(ticker)
            names.setdefault(ticker, title)
            _build_aliases_from_name(title, ticker, aliases, reserved_phrases)


def _ingest_international_listings(
    tickers: Set[str],
    names: Dict[str, str],
    aliases: Dict[str, str],
    reserved_phrases: Set[str],
    sources: List[str],
) -> int:
    exchange_suffixes, country_suffixes = _load_exchange_suffix_maps()
    added = 0
    payload = _fetch_bytes(settings.international_listings_url)
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8")))

    for row in reader:
        yahoo_symbol = _to_yahoo_symbol(
            row.get("ticker", ""),
            row.get("exchange", ""),
            row.get("country", ""),
            exchange_suffixes,
            country_suffixes,
        )
        if not yahoo_symbol:
            continue

        title = str(row.get("name", "")).strip()
        if not title:
            continue

        tickers.add(yahoo_symbol)
        names.setdefault(yahoo_symbol, title)
        _build_aliases_from_name(title, yahoo_symbol, aliases, reserved_phrases)

        for alias in str(row.get("aliases", "")).split("|"):
            alias = alias.strip()
            if alias:
                _add_alias(aliases, alias, yahoo_symbol)

        added += 1

    sources.append(settings.international_listings_url)
    return added


def _build_registry_payload() -> dict:
    tickers: Set[str] = set()
    names: Dict[str, str] = {}
    aliases: Dict[str, str] = {}
    sources: List[str] = []
    reserved_phrases = _load_index_phrases()

    _ingest_us_sources(tickers, names, aliases, reserved_phrases, sources)

    international_count = 0
    if settings.ticker_registry_include_international:
        _ingest_international_listings(
            tickers, names, aliases, reserved_phrases, sources
        )

    if not tickers:
        raise ValueError("No tickers fetched from public sources")

    override_phrases = _merge_overrides(aliases, tickers)

    us_count = sum(1 for ticker in tickers if "." not in ticker)
    international_count = sum(1 for ticker in tickers if "." in ticker)
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "tickers": sorted(tickers),
        "names": names,
        "aliases": aliases,
        "override_phrases": override_phrases,
        "us_ticker_count": us_count,
        "international_ticker_count": international_count,
    }


def _build_alias_index(alias_phrases: List[Tuple[str, str]]) -> DefaultDict[str, List[Tuple[str, str]]]:
    index: DefaultDict[str, List[Tuple[str, str]]] = defaultdict(list)
    for phrase, ticker in alias_phrases:
        if " " in phrase:
            continue
        first = phrase.split()[0]
        index[first].append((phrase, ticker))
    return index


def _apply_payload(payload: dict, from_cache: bool) -> None:
    aliases = payload.get("aliases", {})
    sorted_aliases = sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)

    _registry.tickers = {str(ticker).upper() for ticker in payload.get("tickers", [])}
    _registry.names = {str(k).upper(): str(v) for k, v in payload.get("names", {}).items()}
    _registry.aliases = {str(k).lower(): str(v).upper() for k, v in aliases.items()}
    _registry.alias_phrases = [(phrase, ticker) for phrase, ticker in sorted_aliases]
    _registry.alias_index = _build_alias_index(_registry.alias_phrases)
    override_phrases = payload.get("override_phrases")
    if override_phrases:
        _registry.override_phrases = [(str(p).lower(), str(t).upper()) for p, t in override_phrases]
    else:
        _registry.override_phrases = _load_override_phrases()

    for phrase, ticker in _registry.override_phrases:
        _registry.aliases[phrase] = ticker
        _registry.tickers.add(ticker)
    _registry.fetched_at = payload.get("fetched_at")
    _registry.sources = list(payload.get("sources", []))
    _registry.from_cache = from_cache
    _registry.refresh_error = None
    _registry.us_ticker_count = int(payload.get("us_ticker_count", 0))
    _registry.international_ticker_count = int(payload.get("international_ticker_count", 0))


def _load_cache(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read ticker registry cache at %s: %s", path, exc)
        return None


def _save_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _cache_is_fresh(payload: dict, max_age_hours: int) -> bool:
    fetched_at = payload.get("fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - fetched < timedelta(hours=max_age_hours)


def _apply_fallback() -> None:
    aliases = dict(FALLBACK_ALIASES)
    tickers = set(aliases.values())
    override_phrases = _merge_overrides(aliases, tickers)
    payload = {
        "fetched_at": None,
        "sources": ["built-in-fallback"],
        "tickers": sorted(tickers),
        "names": {},
        "aliases": aliases,
        "override_phrases": override_phrases,
        "us_ticker_count": len(set(aliases.values())),
        "international_ticker_count": 0,
    }
    _apply_payload(payload, from_cache=False)
    _registry.refresh_error = "Using built-in fallback ticker aliases"


def load_registry_from_cache() -> TickerRegistry:
    cache_path = _resolve_path(settings.ticker_registry_path)
    cached = _load_cache(cache_path)
    if cached:
        _apply_payload(cached, from_cache=True)
        logger.info(
            "Loaded ticker registry from cache (%s tickers, %s aliases)",
            len(_registry.tickers),
            len(_registry.aliases),
        )
        return _registry

    _apply_fallback()
    logger.warning("No ticker registry cache found; using fallback until background refresh completes")
    return _registry


def refresh_registry(force: bool = False) -> TickerRegistry:
    cache_path = _resolve_path(settings.ticker_registry_path)
    max_age = settings.ticker_registry_max_age_hours

    if not force:
        cached = _load_cache(cache_path)
        if cached and _cache_is_fresh(cached, max_age):
            _apply_payload(cached, from_cache=True)
            return _registry

    _registry.refresh_in_progress = True
    try:
        payload = _build_registry_payload()
        _save_cache(cache_path, payload)
        _apply_payload(payload, from_cache=False)
        logger.info(
            "Refreshed ticker registry (%s tickers: %s US, %s international; %s aliases)",
            len(_registry.tickers),
            _registry.us_ticker_count,
            _registry.international_ticker_count,
            len(_registry.aliases),
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Ticker registry refresh failed: %s", exc)
        cached = _load_cache(cache_path)
        if cached:
            _apply_payload(cached, from_cache=True)
            _registry.refresh_error = f"Refresh failed; using cached data ({exc})"
        else:
            _apply_fallback()
            _registry.refresh_error = f"Refresh failed; using built-in fallback ({exc})"
    finally:
        _registry.refresh_in_progress = False

    return _registry


def _background_refresh_worker(force: bool) -> None:
    with _refresh_lock:
        refresh_registry(force=force)


def schedule_background_refresh_if_stale(force: bool = False) -> None:
    global _refresh_thread

    if not settings.ticker_registry_background_refresh and not force:
        return

    cache_path = _resolve_path(settings.ticker_registry_path)
    cached = _load_cache(cache_path)
    if not force and cached and _cache_is_fresh(cached, settings.ticker_registry_max_age_hours):
        return

    if _refresh_thread and _refresh_thread.is_alive():
        return

    _refresh_thread = threading.Thread(
        target=_background_refresh_worker,
        kwargs={"force": force},
        daemon=True,
        name="ticker-registry-refresh",
    )
    _refresh_thread.start()
    logger.info("Scheduled background ticker registry refresh")


def initialize_market_data(force: bool = False) -> TickerRegistry:
    from app.market.resolver import load_index_aliases

    load_index_aliases()

    if force or settings.ticker_registry_refresh_on_start:
        return refresh_registry(force=force)

    load_registry_from_cache()
    schedule_background_refresh_if_stale(force=force)
    return _registry


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Refresh GigaNova ticker registry cache")
    parser.add_argument("--force", action="store_true", help="Ignore cache age and refresh now")
    args = parser.parse_args()

    from app.market.resolver import load_index_aliases

    load_index_aliases()
    refresh_registry(force=True if args.force else False)
    status = _registry.status()
    print(
        f"Registry ready: {status['ticker_count']} tickers "
        f"({status['us_ticker_count']} US, {status['international_ticker_count']} international), "
        f"{status['alias_count']} aliases"
    )
    if status.get("refresh_error"):
        print(f"Warning: {status['refresh_error']}")


if __name__ == "__main__":
    main()
