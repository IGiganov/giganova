import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from app.auth import authenticate, get_session_user, needs_setup, require_user
from app.chat.agent import ask_analyst
from app.config import settings
from app.limits.budget import BudgetExceeded, RateLimitExceeded, get_usage_summary
from app.market.quotes import get_quote
from app.market.ticker_registry import get_registry, initialize_market_data
from app.users import (
    create_user,
    get_full_name,
    init_users_db,
    set_full_name,
    set_password,
)

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
    init_users_db()
    initialize_market_data()
    yield


app = FastAPI(title="GigaNova", description="AI market desk", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.auth_secret_key,
    session_cookie="giganova_session",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    usage: dict


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class SetupRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class ProfileRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)


@app.get("/setup")
def setup_page(request: Request) -> Response:
    if not settings.auth_enabled or not needs_setup():
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(STATIC_DIR / "setup.html")


@app.post("/api/setup")
def setup(body: SetupRequest, request: Request) -> dict:
    if not settings.auth_enabled:
        return {"ok": True, "username": body.username}
    if not needs_setup():
        raise HTTPException(status_code=409, detail="Setup already completed. Please sign in.")

    full_name = f"{body.first_name.strip()} {body.last_name.strip()}".strip()
    try:
        create_user(body.username, body.password, full_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request.session["user"] = body.username.strip()
    return {"ok": True, "username": body.username.strip()}


@app.get("/login")
def login_page(request: Request) -> Response:
    if settings.auth_enabled and needs_setup():
        return RedirectResponse(url="/setup", status_code=302)
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/api/login")
def login(body: LoginRequest, request: Request) -> dict:
    if not settings.auth_enabled:
        return {"ok": True, "username": body.username}

    if not authenticate(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    request.session["user"] = body.username.strip()
    return {"ok": True, "username": body.username.strip()}


@app.post("/api/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.post("/api/change-password")
def change_password(body: ChangePasswordRequest, request: Request, user: str = Depends(require_user)) -> dict:
    if not settings.auth_enabled:
        return {"ok": True}

    if not authenticate(user, body.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    set_password(user, body.new_password)
    return {"ok": True}


@app.post("/api/profile")
def update_profile(body: ProfileRequest, request: Request, user: str = Depends(require_user)) -> dict:
    full_name = f"{body.first_name.strip()} {body.last_name.strip()}".strip()
    if settings.auth_enabled:
        set_full_name(user, full_name)
    return {"ok": True, "full_name": full_name, "display_name": full_name or user}


@app.get("/api/me")
def me(request: Request) -> dict:
    if not settings.auth_enabled:
        return {
            "auth_enabled": False,
            "authenticated": True,
            "username": None,
            "full_name": None,
            "display_name": "there",
        }

    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    full_name = get_full_name(user)
    return {
        "auth_enabled": True,
        "authenticated": True,
        "username": user,
        "full_name": full_name,
        "display_name": full_name or user,
    }


@app.get("/")
def index(request: Request) -> Response:
    if settings.auth_enabled:
        if needs_setup():
            return RedirectResponse(url="/setup", status_code=302)
        if not get_session_user(request):
            return RedirectResponse(url="/login", status_code=302)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "name": "GigaNova", "ticker_registry": get_registry().status()}


@app.get("/api/config")
def public_config(_user: str = Depends(require_user)) -> dict:
    return {
        "model": settings.claude_model,
        "monthly_budget_usd": settings.monthly_budget_usd,
        "max_tokens": settings.claude_max_tokens,
        "max_requests_per_hour": settings.max_requests_per_hour,
    }


@app.get("/api/usage")
def usage(_user: str = Depends(require_user)) -> dict:
    return get_usage_summary()


@app.get("/api/markets")
def markets(_user: str = Depends(require_user)) -> dict:
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
def chat(body: ChatRequest, _user: str = Depends(require_user)) -> ChatResponse:
    try:
        result = ask_analyst(body.message.strip())
        return ChatResponse(**result)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc
