from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_max_tokens: int = 1400
    claude_max_tool_rounds: int = 2

    monthly_budget_usd: float = 15.0
    input_price_per_million: float = 1.0
    output_price_per_million: float = 5.0
    max_requests_per_hour: int = 30

    max_news_items: int = 8
    max_tickers_per_request: int = 5
    news_summary_max_chars: int = 200

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    budget_db_path: str = "data/usage.sqlite3"

    ticker_registry_path: str = "data/ticker_registry.json"
    index_aliases_path: str = "app/market/data/index_aliases.json"
    company_overrides_path: str = "app/market/data/company_overrides.json"
    ticker_registry_max_age_hours: int = 168
    ticker_registry_refresh_on_start: bool = False
    ticker_registry_background_refresh: bool = True
    ticker_registry_include_international: bool = True
    international_listings_url: str = (
        "https://raw.githubusercontent.com/adanos-software/free-ticker-database/main/data/listings.csv"
    )
    exchange_yahoo_suffixes_path: str = "app/market/data/exchange_yahoo_suffixes.json"
    euronext_country_suffixes_path: str = "app/market/data/euronext_country_suffixes.json"
    ticker_registry_timeout_seconds: int = 60
    ticker_registry_user_agent: str = (
        "GigaNova personal research (contact: you@example.com)"
    )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        input_cost = (input_tokens / 1_000_000) * self.input_price_per_million
        output_cost = (output_tokens / 1_000_000) * self.output_price_per_million
        return round(input_cost + output_cost, 6)


settings = Settings()
