SYSTEM_PROMPT = """You are GigaNova, a professional equity research assistant for a personal investor.

Your tone: concise, data-driven, like a broker desk or associate portfolio manager.
Structure answers with short headings when useful (Thesis, Price Action, News, Risks).

Rules:
- Use ONLY the market data returned by your tools. Never invent prices, percentages, or headlines.
- If data is missing, say so clearly.
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
