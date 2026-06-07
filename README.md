# GigaNova

AI market desk — chat with an analyst that answers using live stock quotes and news.

## Setup

```bash
cd giganova
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your Anthropic API key
```

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Configuration

All limits and pricing live in `.env`. Copy from `.env.example` and adjust:


| Variable                 | Default | Purpose                       |
| ------------------------ | ------- | ----------------------------- |
| `MONTHLY_BUDGET_USD`     | 15.00   | App-side monthly AI spend cap |
| `CLAUDE_MODEL`           | haiku   | Lightweight default model     |
| `CLAUDE_MAX_TOKENS`      | 1400    | Max reply length              |
| `CLAUDE_MAX_TOOL_ROUNDS` | 2       | Cap tool-call loops           |
| `MAX_REQUESTS_PER_HOUR`  | 30      | Rate limit                    |
| `MAX_NEWS_ITEMS`         | 8       | Headlines per ticker          |


Also set a hard cap in the [Anthropic Console](https://console.anthropic.com/settings/limits) (you have $20/mo there as a safety net).

**Not financial advice.** For personal research only.