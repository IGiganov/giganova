from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.chat.agent import ask_analyst
from app.config import settings
from app.limits.budget import BudgetExceeded, RateLimitExceeded, get_usage_summary

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="GigaNova", description="AI market desk")
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
    return {"status": "ok", "name": "GigaNova"}


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
