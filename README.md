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

On startup, GigaNova loads a cached ticker registry from `data/ticker_registry.json` (no network delay). A background job refreshes it at most once per week from public sources:

- US: SEC + NASDAQ symbol lists
- International: [Adanos free ticker database](https://github.com/adanos-software/free-ticker-database) (`listings.csv`), mapped to Yahoo Finance symbols (e.g. `7203.T`, `SAP.DE`, `SHEL.L`)

Index phrase mappings: `app/market/data/index_aliases.json`. Nickname overrides: `app/market/data/company_overrides.json`.

Manual refresh (or weekly cron):

```bash
python -m app.market.ticker_registry --force
```

## Login

GigaNova has an internal login. Accounts live in a small SQLite database
(`data/users.sqlite3`) with passwords stored as a **bcrypt hash**, never in plaintext.

- **First run:** open the app and you'll be sent to `/setup` to create your account
  (username + password). No password is needed in `.env`.
- **Change password:** click the orange account button (top right) → *Change password*.
- **Session:** a signed cookie that lasts 14 days.

Minimal `.env`:

```env
AUTH_ENABLED=true
AUTH_SECRET_KEY=<long-random-string>  # signs the session cookie
```

Set `AUTH_ENABLED=false` to disable login for local dev.

### Optional recovery admin

If you ever lock yourself out, you can define a fallback admin in `.env`. It only
works when **both** a username and a password (or hash) are set:

```bash
python -m app.hash_password      # → prints a bcrypt hash
```

```env
AUTH_USERNAME=admin
AUTH_PASSWORD_HASH=$2b$12$....    # from the command above
```

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