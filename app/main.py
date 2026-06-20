import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.chat.agent import ask_analyst
from app.config import settings
from app.limits.budget import BudgetExceeded, RateLimitExceeded, get_usage_summary
from app.market.quotes import get_quote
from app.market.ticker_registry import get_registry, initialize_market_data

STATIC_DIR = Path(__file__).parent / "static"

MARKET_BAR_TICKERS = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "NASDAQ"),
    ("^DJI", "DOW"),
    ("^RUT", "RUSSELL"),
]
_market_cache: dict = {"ts": 0.0, "data": None}
MARKET_CACHE_TTL_SECONDS = 60


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_market_data()
    yield


app = FastAPI(title="GigaNova", description="AI market desk", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    usage: dict


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "name": "GigaNova", "ticker_registry": get_registry().status()}


@app.get("/api/config")
def public_config() -> dict:
    return {
        "model": settings.claude_model,
        "monthly_budget_usd": settings.monthly_budget_usd,
        "max_tokens": settings.claude_max_tokens,
        "max_requests_per_hour": settings.max_requests_per_hour,
    }


@app.get("/api/usage")
def usage() -> dict:
    return get_usage_summary()


@app.get("/api/markets")
def markets() -> dict:
    now = time.time()
    if _market_cache["data"] and now - _market_cache["ts"] < MARKET_CACHE_TTL_SECONDS:
        return _market_cache["data"]

    indices = []
    for symbol, label in MARKET_BAR_TICKERS:
        quote = get_quote(symbol)
        indices.append(
            {
                "symbol": symbol,
                "label": label,
                "price": quote.get("price"),
                "change_pct": quote.get("change_pct_day"),
            }
        )

    payload = {"indices": indices}
    _market_cache["ts"] = now
    _market_cache["data"] = payload
    return payload


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    try:
        result = ask_analyst(body.message.strip())
        return ChatResponse(**result)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc
