import json

from anthropic import Anthropic

from app.chat.prompts import GENERAL_PROMPT, SYSTEM_PROMPT
from app.config import settings
from app.limits.budget import check_limits, record_request, record_usage
from app.market.context import build_market_context
from app.market.resolver import QueryResolution, is_market_question, resolve_query_full, symbol_label


def _usage_payload(input_tokens: int, output_tokens: int) -> dict:
    cost = record_usage(input_tokens, output_tokens)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost,
    }


def _no_data_answer(tickers: list) -> str:
    labels = ", ".join(symbol_label(t) for t in tickers)
    return (
        f"I couldn't retrieve usable market data or news for **{labels}** from the feed right now.\n\n"
        "Please try again later, or ask about a specific ticker (e.g. AAPL, QQQ, ^GSPC)."
    )


def _clarify_answer(resolution: QueryResolution) -> str:
    token = resolution.unresolved or "that symbol"
    return (
        f"I couldn't match **{token}** to a US stock or index in our feed.\n\n"
        "Could you clarify? For example:\n"
        "- **Ticker:** AAPL, NVDA, MSFT\n"
        "- **Index:** NASDAQ, S&P 500, Dow\n"
        "- **Company name:** Apple, Nvidia, Tesla\n\n"
        "Once I know the symbol, I'll pull live price data and headlines for you."
    )


def ask_analyst(message: str) -> dict:
    check_limits()
    record_request()

    client = Anthropic(api_key=settings.anthropic_api_key)

    if is_market_question(message):
        resolution = resolve_query_full(message)

        if resolution.unresolved:
            return {"answer": _clarify_answer(resolution), "usage": _usage_payload(0, 0)}

        if not resolution.tickers:
            return {"answer": _clarify_answer(resolution), "usage": _usage_payload(0, 0)}

        context = build_market_context(resolution.tickers, resolution.period)

        if not context["has_any_data"]:
            return {"answer": _no_data_answer(resolution.tickers), "usage": _usage_payload(0, 0)}

        correction_note = ""
        if resolution.corrections:
            joined = ", ".join(resolution.corrections)
            correction_note = (
                f"Auto-corrections applied: {joined}. "
                "Briefly note the interpreted symbol in the Executive Summary if helpful. "
                "Do not ask the user to re-type.\n\n"
            )

        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{correction_note}"
                        f"Prefetched market data (JSON):\n{json.dumps(context, default=str)}\n\n"
                        f"User question: {message}"
                    ),
                }
            ],
        )
        answer = "".join(block.text for block in response.content if block.type == "text").strip()
        return {
            "answer": answer,
            "usage": _usage_payload(response.usage.input_tokens, response.usage.output_tokens),
        }

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        system=GENERAL_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    answer = "".join(block.text for block in response.content if block.type == "text").strip()
    return {
        "answer": answer,
        "usage": _usage_payload(response.usage.input_tokens, response.usage.output_tokens),
    }
