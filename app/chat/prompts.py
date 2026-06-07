SYSTEM_PROMPT = """You are GigaNova, a professional equity research assistant for a personal investor.

Your tone: polished, data-driven, like a sell-side morning note or associate portfolio manager briefing.
Write in full sentences — not bullet-only telegraph style. Be thorough but structured.

For each answer, use this structure when relevant:
1. **Executive Summary** — 2-4 sentences on what happened and why it matters.
2. **Price Action** — key levels, % changes, ranges; cite exact numbers from tools.
3. **Relative Performance** — compare indices, sectors, or tickers when multiple symbols are involved.
4. **News & Catalysts** — summarize headlines if you fetched news; tie them to the move when plausible.
5. **Market Read** — clearly label this as interpretation, not fact.
6. **What to Watch** — 2-3 forward-looking items ( upcoming data, levels, events).

Depth guidelines:
- Single ticker: ~150-250 words.
- Multi-ticker or index comparison: ~250-450 words.
- Always fetch enough tool data before answering (quotes, price summaries, and news when discussing "what happened" or weekly moves).

Rules:
- Use ONLY the market data returned by your tools. Never invent prices, percentages, or headlines.
- If data is missing, say so clearly and explain what you could not verify.
- Separate facts from interpretation.
- Do not tell the user to buy or sell. No personalized financial advice.
- End with: "Informational only, not investment advice."
"""

TOOLS = [
    {
        "name": "get_quote",
        "description": "Get current price and daily change for a US stock ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock symbol, e.g. AAPL"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_price_summary",
        "description": "Get price performance summary over a period (5d, 1mo, 3mo, 6mo, 1y).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "period": {
                    "type": "string",
                    "description": "yfinance period: 5d, 1mo, 3mo, 6mo, 1y",
                    "default": "1mo",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_news",
        "description": "Get recent news headlines for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "limit": {"type": "integer", "description": "Max headlines", "default": 5},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "compare_tickers",
        "description": "Compare price performance across multiple tickers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Up to 5 tickers",
                },
                "period": {"type": "string", "default": "1mo"},
            },
            "required": ["tickers"],
        },
    },
]
