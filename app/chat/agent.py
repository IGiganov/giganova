import json

from anthropic import Anthropic

from app.chat.prompts import SYSTEM_PROMPT, TOOLS
from app.config import settings
from app.limits.budget import check_limits, record_request, record_usage
from app.market.news import get_news
from app.market.quotes import compare_tickers, get_price_summary, get_quote


def _run_tool(name: str, tool_input: dict) -> dict:
    if name == "get_quote":
        return get_quote(tool_input["ticker"])
    if name == "get_price_summary":
        return get_price_summary(tool_input["ticker"], tool_input.get("period", "1mo"))
    if name == "get_news":
        return get_news(tool_input["ticker"], tool_input.get("limit"))
    if name == "compare_tickers":
        return compare_tickers(tool_input["tickers"], tool_input.get("period", "1mo"))
    return {"error": f"Unknown tool: {name}"}


def ask_analyst(message: str) -> dict:
    check_limits()
    record_request()

    client = Anthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": message}]

    total_input = 0
    total_output = 0

    for _ in range(settings.claude_max_tool_rounds + 1):
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

        if response.stop_reason != "tool_use":
            text_blocks = [block.text for block in response.content if block.type == "text"]
            cost = record_usage(total_input, total_output)
            return {
                "answer": "\n".join(text_blocks).strip(),
                "usage": {
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                    "estimated_cost_usd": cost,
                },
            }

        tool_results = []
        assistant_content = []
        for block in response.content:
            assistant_content.append(block)
            if block.type == "tool_use":
                result = _run_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    cost = record_usage(total_input, total_output)
    return {
        "answer": "I couldn't finish the analysis within the tool limit. Try a simpler question.",
        "usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "estimated_cost_usd": cost,
        },
    }
