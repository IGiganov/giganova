import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings


class BudgetExceeded(Exception):
    pass


class RateLimitExceeded(Exception):
    pass


def _connect() -> sqlite3.Connection:
    path = Path(settings.budget_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _hour_ago_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def check_limits() -> None:
    conn = _connect()
    try:
        month_start = _month_start_iso()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM usage WHERE created_at >= ?",
            (month_start,),
        ).fetchone()
        spent = float(row[0] or 0)
        if spent >= settings.monthly_budget_usd:
            raise BudgetExceeded(
                f"Monthly AI budget reached (${spent:.2f} / ${settings.monthly_budget_usd:.2f})."
            )

        hour_start = _hour_ago_iso()
        count_row = conn.execute(
            "SELECT COUNT(*) FROM request_log WHERE created_at >= ?",
            (hour_start,),
        ).fetchone()
        count = int(count_row[0] or 0)
        if count >= settings.max_requests_per_hour:
            raise RateLimitExceeded(
                f"Rate limit reached ({settings.max_requests_per_hour} requests/hour)."
            )
    finally:
        conn.close()


def record_request() -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO request_log (created_at) VALUES (?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()


def record_usage(input_tokens: int, output_tokens: int) -> float:
    cost = settings.estimate_cost(input_tokens, output_tokens)
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO usage (created_at, input_tokens, output_tokens, cost_usd) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), input_tokens, output_tokens, cost),
        )
        conn.commit()
    finally:
        conn.close()
    return cost


def get_usage_summary() -> dict:
    conn = _connect()
    try:
        month_start = _month_start_iso()
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(cost_usd), 0),
                COALESCE(SUM(input_tokens), 0),
                COALESCE(SUM(output_tokens), 0),
                COUNT(*)
            FROM usage WHERE created_at >= ?
            """,
            (month_start,),
        ).fetchone()
        spent = float(row[0] or 0)
        return {
            "monthly_budget_usd": settings.monthly_budget_usd,
            "spent_usd": round(spent, 4),
            "remaining_usd": round(max(settings.monthly_budget_usd - spent, 0), 4),
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "requests": int(row[3] or 0),
            "model": settings.claude_model,
        }
    finally:
        conn.close()
