# Generated from ../buy_sell_equities.ipynb for Hugging Face Spaces.
# Notebook-only exploratory cells and immediate account/API calls were intentionally omitted.

# %% Notebook cell 1
from dotenv import load_dotenv
import os
import requests

# %% Notebook cell 2
load_dotenv()

TRADING_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
DATA_BASE_URL = os.getenv("APCA_DATA_BASE_URL", "https://data.alpaca.markets").rstrip("/")

# %% Notebook cell 6
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

JsonDict = dict[str, Any]

LIVE_TRADING_BASE_URL = os.getenv("APCA_LIVE_API_BASE_URL", "https://api.alpaca.markets").rstrip("/")
LIVE_HEADERS = {
    "APCA-API-KEY-ID": os.getenv("APCA_LIVE_API_KEY_ID"),
    "APCA-API-SECRET-KEY": os.getenv("APCA_LIVE_API_SECRET_KEY"),
}


def require_env() -> None:
    missing = [key for key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY") if not os.getenv(key)]
    if missing:
        raise EnvironmentError(f"Missing required Alpaca environment variables: {', '.join(missing)}")


def alpaca_request(
    method: str,
    base_url: str,
    path: str,
    *,
    headers: dict[str, str | None] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: int = 30,
) -> JsonDict | list[JsonDict]:
    require_env()
    request_headers = headers or HEADERS
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    response = requests.request(
        method=method,
        url=url,
        headers=request_headers,
        params={k: v for k, v in (params or {}).items() if v is not None},
        json=json,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:500]
        raise requests.HTTPError(f"{exc}. Alpaca response: {detail}", response=response) from exc
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


def as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal(default)

# %% Notebook cell 8
def get_account() -> JsonDict:
    """Return paper account details, including buying power, cash, and trading status."""
    return alpaca_request("GET", TRADING_BASE_URL, "/v2/account")


def get_positions() -> list[JsonDict]:
    """Return all open positions in the paper account."""
    return alpaca_request("GET", TRADING_BASE_URL, "/v2/positions")


def get_position(symbol: str) -> JsonDict | None:
    """Return one open position, or None if the account has no open position for the symbol."""
    try:
        return alpaca_request("GET", TRADING_BASE_URL, f"/v2/positions/{symbol.upper()}")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise

# %% Notebook cell 10
def get_latest_quote(symbol: str, feed: str = "iex") -> JsonDict:
    """Return the latest bid/ask quote for a stock symbol."""
    return alpaca_request(
        "GET",
        DATA_BASE_URL,
        f"/v2/stocks/{symbol.upper()}/quotes/latest",
        params={"feed": feed},
    )


def get_historical_bars(
    symbol: str,
    start: str | datetime | date,
    end: str | datetime | date | None = None,
    timeframe: str = "1Day",
    *,
    feed: str = "iex",
    adjustment: Literal["raw", "split", "dividend", "all"] = "raw",
    limit: int = 1000,
) -> JsonDict:
    """Return historical OHLCV bars for one stock symbol."""
    params = {
        "symbols": symbol.upper(),
        "start": start.isoformat() if hasattr(start, "isoformat") else start,
        "end": end.isoformat() if hasattr(end, "isoformat") else end,
        "timeframe": timeframe,
        "feed": feed,
        "adjustment": adjustment,
        "limit": min(max(int(limit), 1), 10000),
        "sort": "asc",
    }
    return alpaca_request("GET", DATA_BASE_URL, "/v2/stocks/bars", params=params)


def get_news(
    symbol: str,
    *,
    start: str | datetime | date | None = None,
    end: str | datetime | date | None = None,
    limit: int = 10,
) -> JsonDict:
    """Return recent news articles for a stock symbol."""
    params = {
        "symbols": symbol.upper(),
        "start": start.isoformat() if hasattr(start, "isoformat") else start,
        "end": end.isoformat() if hasattr(end, "isoformat") else end,
        "limit": min(max(int(limit), 1), 50),
        "sort": "desc",
    }
    return alpaca_request("GET", DATA_BASE_URL, "/v1beta1/news", params=params)


def get_company_fundamentals(symbol: str) -> JsonDict:
    """Return Alpaca-available company context: asset metadata and recent corporate actions.

    Alpaca does not provide full income statement / balance sheet fundamentals here.
    Treat this as tradability and corporate-action context, not valuation fundamentals.
    """
    ticker = symbol.upper()
    today = date.today()
    start = today - timedelta(days=365)
    asset = alpaca_request("GET", TRADING_BASE_URL, f"/v2/assets/{ticker}")
    corporate_actions = alpaca_request(
        "GET",
        DATA_BASE_URL,
        "/v1/corporate-actions",
        params={"symbols": ticker, "start": start.isoformat(), "end": today.isoformat(), "limit": 100},
    )
    return {"symbol": ticker, "asset": asset, "corporate_actions": corporate_actions}

# %% Notebook cell 12
ALLOWED_ORDER_TYPES = {"market", "limit", "stop", "stop_limit", "trailing_stop"}
ALLOWED_TIME_IN_FORCE = {"day", "gtc", "opg", "cls", "ioc", "fok"}
MAX_PAPER_ORDER_NOTIONAL = Decimal(os.getenv("MAX_PAPER_ORDER_NOTIONAL", "1000"))


def latest_trade_price_from_quote(quote_response: JsonDict, side: str) -> Decimal:
    quote = quote_response.get("quote", {})
    ask = as_decimal(quote.get("ap"))
    bid = as_decimal(quote.get("bp"))
    fallback = ask if ask > 0 else bid
    if side == "buy":
        return ask if ask > 0 else fallback
    return bid if bid > 0 else fallback


def preview_order(
    symbol: str,
    side: Literal["buy", "sell"],
    qty: float | int | str | None = None,
    order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"] = "market",
    limit_price: float | int | str | None = None,
    *,
    notional: float | int | str | None = None,
    time_in_force: str = "day",
    feed: str = "iex",
) -> JsonDict:
    """Validate and estimate an order without submitting it to Alpaca."""
    ticker = symbol.upper().strip()
    side = side.lower().strip()
    order_type = order_type.lower().strip()
    time_in_force = time_in_force.lower().strip()

    errors: list[str] = []
    if side not in {"buy", "sell"}:
        errors.append("side must be 'buy' or 'sell'")
    if order_type not in ALLOWED_ORDER_TYPES:
        errors.append(f"order_type must be one of {sorted(ALLOWED_ORDER_TYPES)}")
    if time_in_force not in ALLOWED_TIME_IN_FORCE:
        errors.append(f"time_in_force must be one of {sorted(ALLOWED_TIME_IN_FORCE)}")
    if qty is None and notional is None:
        errors.append("provide either qty or notional")
    if qty is not None and notional is not None:
        errors.append("qty and notional are mutually exclusive")
    if order_type in {"limit", "stop_limit"} and limit_price is None:
        errors.append("limit_price is required for limit and stop_limit orders")

    quantity = as_decimal(qty) if qty is not None else None
    dollar_notional = as_decimal(notional) if notional is not None else None
    if quantity is not None and quantity <= 0:
        errors.append("qty must be greater than zero")
    if dollar_notional is not None and dollar_notional <= 0:
        errors.append("notional must be greater than zero")

    account = get_account()
    if account.get("trading_blocked"):
        errors.append("account is trading_blocked")
    if account.get("account_blocked"):
        errors.append("account is account_blocked")

    quote = get_latest_quote(ticker, feed=feed)
    estimated_price = latest_trade_price_from_quote(quote, side)
    if estimated_price <= 0:
        errors.append("could not estimate a valid price from the latest quote")

    estimated_notional = dollar_notional or ((quantity or Decimal("0")) * estimated_price)
    buying_power = as_decimal(account.get("buying_power"))
    position = get_position(ticker)
    held_qty = as_decimal(position.get("qty")) if position else Decimal("0")

    if side == "buy" and estimated_notional > buying_power:
        errors.append(f"estimated notional {estimated_notional} exceeds buying power {buying_power}")
    if side == "buy" and estimated_notional > MAX_PAPER_ORDER_NOTIONAL:
        errors.append(f"estimated notional {estimated_notional} exceeds MAX_PAPER_ORDER_NOTIONAL {MAX_PAPER_ORDER_NOTIONAL}")
    if side == "sell" and quantity is not None and quantity > held_qty:
        errors.append(f"sell quantity {quantity} exceeds held quantity {held_qty}")

    order_payload = {
        "symbol": ticker,
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }
    if quantity is not None:
        order_payload["qty"] = str(quantity)
    if dollar_notional is not None:
        order_payload["notional"] = str(dollar_notional)
    if order_type in {"limit", "stop_limit"} and limit_price is not None:
        order_payload["limit_price"] = str(as_decimal(limit_price))

    return {
        "ok_to_submit": not errors,
        "errors": errors,
        "estimated_price": str(estimated_price),
        "estimated_notional": str(estimated_notional),
        "buying_power": str(buying_power),
        "held_qty": str(held_qty),
        "order": order_payload,
        "quote": quote,
    }

# %% Notebook cell 13
def place_paper_order(order: JsonDict) -> JsonDict:
    """Submit a validated order to the Alpaca paper trading account."""
    if "paper-api.alpaca.markets" not in TRADING_BASE_URL:
        raise PermissionError(f"Refusing to submit paper order because TRADING_BASE_URL is {TRADING_BASE_URL!r}")

    preview = preview_order(
        symbol=order["symbol"],
        side=order["side"],
        qty=order.get("qty"),
        order_type=order.get("type", "market"),
        limit_price=order.get("limit_price"),
        notional=order.get("notional"),
        time_in_force=order.get("time_in_force", "day"),
    )
    if not preview["ok_to_submit"]:
        return {"submitted": False, "preview": preview}

    submitted = alpaca_request("POST", TRADING_BASE_URL, "/v2/orders", json=preview["order"])
    return {"submitted": True, "preview": preview, "alpaca_order": submitted}


def place_live_order(order: JsonDict, confirmation_token: str) -> JsonDict:
    """Submit a live order only after explicit opt-in and confirmation.

    This is intentionally disabled unless ALLOW_LIVE_TRADING=true and separate
    APCA_LIVE_API_KEY_ID / APCA_LIVE_API_SECRET_KEY credentials are configured.
    """
    if os.getenv("ALLOW_LIVE_TRADING", "false").lower() != "true":
        raise PermissionError("Live trading is disabled. Set ALLOW_LIVE_TRADING=true only when you are ready.")
    if confirmation_token != "I_UNDERSTAND_THIS_IS_LIVE_TRADING":
        raise PermissionError("Invalid live-trading confirmation token.")
    if not LIVE_HEADERS["APCA-API-KEY-ID"] or not LIVE_HEADERS["APCA-API-SECRET-KEY"]:
        raise EnvironmentError("Missing APCA_LIVE_API_KEY_ID or APCA_LIVE_API_SECRET_KEY.")

    return alpaca_request(
        "POST",
        LIVE_TRADING_BASE_URL,
        "/v2/orders",
        headers=LIVE_HEADERS,
        json=order,
    )

# %% Notebook cell 15
TOOLS = {
    "get_account": get_account,
    "get_positions": get_positions,
    "get_latest_quote": get_latest_quote,
    "get_historical_bars": get_historical_bars,
    "get_company_fundamentals": get_company_fundamentals,
    "get_news": get_news,
    "preview_order": preview_order,
    "place_paper_order": place_paper_order,
    "place_live_order": place_live_order,
}

# Start by exposing only these schemas to the model. The execution tools exist,
# but order placement should happen through your own approval flow.
SAFE_TOOL_NAMES = {
    "get_account",
    "get_positions",
    "get_latest_quote",
    "get_historical_bars",
    "get_company_fundamentals",
    "get_news",
    "preview_order",
}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_account",
        "description": "Return Alpaca paper account details including buying power and trading status.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_positions",
        "description": "Return all open Alpaca paper account positions.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "get_latest_quote",
        "description": "Return the latest bid/ask quote for a stock symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "feed": {"type": "string", "default": "iex"},
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_historical_bars",
        "description": "Return historical OHLCV bars for a stock symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "timeframe": {"type": "string", "default": "1Day"},
                "feed": {"type": "string", "default": "iex"},
                "limit": {"type": "integer", "default": 1000},
            },
            "required": ["symbol", "start"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_company_fundamentals",
        "description": "Return asset metadata and recent corporate actions available from Alpaca.",
        "parameters": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_news",
        "description": "Return recent Alpaca news articles for a stock symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "preview_order",
        "description": "Validate and estimate a buy/sell order without submitting it.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "qty": {"type": ["number", "string", "null"]},
                "notional": {"type": ["number", "string", "null"]},
                "order_type": {"type": "string", "default": "market"},
                "limit_price": {"type": ["number", "string", "null"]},
                "time_in_force": {"type": "string", "default": "day"},
            },
            "required": ["symbol", "side"],
            "additionalProperties": False,
        },
    },
]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Dispatch a model-requested tool call by name."""
    if name not in TOOLS:
        raise KeyError(f"Unknown tool: {name}")
    if name not in SAFE_TOOL_NAMES:
        raise PermissionError(f"Tool {name!r} is not exposed for direct model calls")
    return TOOLS[name](**(arguments or {}))

# %% Notebook cell 24
import gradio as gr
import pandas as pd
import plotly.graph_objects as go

# %% Notebook cell 25
DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "SPY", "QQQ", "IWM"
]

TRADING_DASHBOARD_CSS = """
.gradio-container {
  max-width: 100% !important;
  padding: 0 36px !important;
}
.metric-card {
  border: 1px solid rgba(120,120,120,.22);
  border-radius: 8px;
  padding: 10px;
  min-height: 160px;
}
.dashboard-grid {
  gap: 14px !important;
  align-items: stretch !important;
}
.dashboard-grid > .column {
  min-width: 0 !important;
}
.controls .wrap {
  gap: 10px;
  align-items: center;
}
.primary-action button {
  font-weight: 700 !important;
}
.danger-action button {
  border-color: rgba(190, 55, 55, .45) !important;
  color: rgb(190, 55, 55) !important;
  font-weight: 700 !important;
}
.agent-grid {
  align-items: flex-start !important;
}
.agent-controls {
  padding-right: 6px;
}
.agent-results {
  padding-right: 8px;
}
.agent-summary {
  min-height: 220px;
  max-height: 430px;
  overflow-y: auto;
}
.agent-json {
  max-height: 360px;
  overflow-y: auto;
}
.agent-results .gap,
.agent-controls .gap {
  gap: 12px !important;
}

.yolo-row {
  align-items: center !important;
  justify-content: space-between !important;
  margin-bottom: 8px;
}
.yolo-row .wrap {
  justify-content: space-between !important;
  align-items: center !important;
}

.yolo-toggle {
  width: max-content !important;
  min-width: max-content !important;
  flex: 0 0 auto !important;
  justify-self: flex-end !important;
}
.yolo-toggle > div {
  width: max-content !important;
}
.yolo-toggle label {
  white-space: nowrap !important;
}

.yolo-toggle,
.yolo-toggle > div,
.yolo-toggle .wrap,
.yolo-toggle label {
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
}
.yolo-toggle {
  padding: 0 !important;
}

"""

# %% Notebook cell 26
def format_money(value: Any) -> str:
    amount = as_decimal(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def format_percent(value: Any) -> str:
    pct = as_decimal(value) * Decimal("100")
    return f"{pct:+,.2f}%"


def position_rows(positions: list[JsonDict]) -> pd.DataFrame:
    rows = []
    for position in positions:
        rows.append({
            "symbol": position.get("symbol"),
            "qty": position.get("qty"),
            "market_value": float(as_decimal(position.get("market_value"))),
            "avg_entry_price": float(as_decimal(position.get("avg_entry_price"))),
            "current_price": float(as_decimal(position.get("current_price"))),
            "unrealized_pl": float(as_decimal(position.get("unrealized_pl"))),
            "unrealized_plpc": float(as_decimal(position.get("unrealized_plpc")) * Decimal("100")),
            "change_today": float(as_decimal(position.get("change_today")) * Decimal("100")),
        })
    return pd.DataFrame(rows)


def account_markdown(account: JsonDict, positions: list[JsonDict]) -> str:
    equity = as_decimal(account.get("equity"))
    last_equity = as_decimal(account.get("last_equity"))
    daily_pl = equity - last_equity
    daily_pl_pct = (daily_pl / last_equity) if last_equity else Decimal("0")
    exposure = sum(abs(as_decimal(position.get("market_value"))) for position in positions)
    unrealized_pl = sum(as_decimal(position.get("unrealized_pl")) for position in positions)
    direction = "uptick" if daily_pl > 0 else "downtick" if daily_pl < 0 else "flat"

    return f"""
### Account

Portfolio value: **{format_money(account.get('portfolio_value'))}**  
Cash: **{format_money(account.get('cash'))}**  
Buying power: **{format_money(account.get('buying_power'))}**  
Current amount trading: **{format_money(exposure)}**  
Open-position unrealized P/L: **{format_money(unrealized_pl)}**  
Today: **{direction} {format_money(daily_pl)} ({format_percent(daily_pl_pct)})**  
Account status: **{account.get('status')}**
"""


def quote_markdown(symbol: str, quote_response: JsonDict) -> str:
    quote = quote_response.get("quote", {})
    bid = quote.get("bp")
    ask = quote.get("ap")
    bid_size = quote.get("bs")
    ask_size = quote.get("as")
    timestamp = quote.get("t")
    spread = as_decimal(ask) - as_decimal(bid)
    mid = (as_decimal(ask) + as_decimal(bid)) / Decimal("2") if as_decimal(ask) and as_decimal(bid) else Decimal("0")

    return f"""
### {symbol.upper()} Quote

Bid: **{format_money(bid)}** x {bid_size}  
Ask: **{format_money(ask)}** x {ask_size}  
Mid: **{format_money(mid)}**  
Spread: **{format_money(spread)}**  
Timestamp: `{timestamp}`
"""


def bars_dataframe(bars_response: JsonDict, symbol: str) -> pd.DataFrame:
    raw_bars = bars_response.get("bars", {}).get(symbol.upper(), [])
    rows = []
    for bar in raw_bars:
        rows.append({
            "time": pd.to_datetime(bar.get("t")),
            "open": bar.get("o"),
            "high": bar.get("h"),
            "low": bar.get("l"),
            "close": bar.get("c"),
            "volume": bar.get("v"),
            "vwap": bar.get("vw"),
        })
    return pd.DataFrame(rows)


def price_chart(bars: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure()
    if not bars.empty:
        fig.add_trace(go.Scatter(x=bars["time"], y=bars["close"], mode="lines+markers", name="Close"))
        fig.add_trace(go.Bar(x=bars["time"], y=bars["volume"], name="Volume", yaxis="y2", opacity=0.25))
    fig.update_layout(
        title=f"{symbol.upper()} price and volume",
        height=360,
        margin={"l": 40, "r": 40, "t": 50, "b": 40},
        yaxis={"title": "Price"},
        yaxis2={"title": "Volume", "overlaying": "y", "side": "right", "showgrid": False},
        legend={"orientation": "h"},
    )
    return fig


def news_markdown(news_response: JsonDict) -> str:
    articles = news_response.get("news", [])
    if not articles:
        return "### News\n\nNo recent articles returned."
    lines = ["### News"]
    for article in articles[:5]:
        headline = article.get("headline", "Untitled")
        source = article.get("source", "Unknown source")
        created_at = article.get("created_at", "")
        url = article.get("url")
        if url:
            lines.append(f"- [{headline}]({url}) - {source}, `{created_at}`")
        else:
            lines.append(f"- {headline} - {source}, `{created_at}`")
    return "\n".join(lines)


def trade_posture(symbol: str, side: str, bars: pd.DataFrame, preview: JsonDict) -> str:
    if not preview.get("ok_to_submit"):
        errors = "; ".join(preview.get("errors", []))
        return f"### Paper-trade posture\n\n**Do not submit yet.** Preview checks failed: {errors}\n\nThis is not financial advice."

    if bars.empty or len(bars) < 2:
        return "### Paper-trade posture\n\n**Watch only.** Not enough historical bars were returned to evaluate recent direction.\n\nThis is not financial advice."

    first_close = as_decimal(bars.iloc[0]["close"])
    last_close = as_decimal(bars.iloc[-1]["close"])
    change_pct = ((last_close - first_close) / first_close) if first_close else Decimal("0")
    direction = "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"

    if side == "buy" and change_pct > Decimal("0.01"):
        stance = "Candidate for a small paper-trade preview"
    elif side == "sell" and change_pct < Decimal("-0.01"):
        stance = "Candidate for a small paper-trade preview"
    else:
        stance = "Watch / hold; the simple trend check does not strongly support this side"

    return f"""
### Paper-trade posture

Recent direction: **{direction} {format_percent(change_pct)}** over returned bars.  
Preview status: **OK**  
Stance: **{stance}**

This is a simple educational signal for paper trading, not financial advice.
"""

# %% Notebook cell 27
def normalize_order_inputs(size_by: str, qty: str, notional: str, order_type: str, limit_price: str) -> tuple[str | None, str | None, str | None]:
    qty_value = qty.strip() or None
    notional_value = notional.strip() or None
    limit_value = limit_price.strip() or None

    if size_by == "Shares":
        notional_value = None
    else:
        qty_value = None

    if order_type not in {"limit", "stop_limit"}:
        limit_value = None

    return qty_value, notional_value, limit_value


def refresh_dashboard(
    symbol: str,
    timeframe: str,
    lookback_days: int,
    feed: str,
    side: str,
    size_by: str,
    qty: str,
    notional: str,
    order_type: str,
    limit_price: str,
) -> tuple[str, pd.DataFrame, str, JsonDict, go.Figure, pd.DataFrame, str, str, JsonDict]:
    ticker = symbol.upper().strip()
    start = (date.today() - timedelta(days=int(lookback_days))).isoformat()

    account = get_account()
    positions = get_positions()
    quote = get_latest_quote(ticker, feed=feed)
    bars_response = get_historical_bars(ticker, start=start, timeframe=timeframe, feed=feed, limit=500)
    bars = bars_dataframe(bars_response, ticker)
    news = get_news(ticker, limit=5)

    qty_value, notional_value, limit_value = normalize_order_inputs(size_by, qty, notional, order_type, limit_price)
    preview = preview_order(
        ticker,
        side=side,
        qty=qty_value,
        notional=notional_value,
        order_type=order_type,
        limit_price=limit_value,
        feed=feed,
    )

    return (
        account_markdown(account, positions),
        position_rows(positions),
        quote_markdown(ticker, quote),
        quote,
        price_chart(bars, ticker),
        bars.tail(20),
        news_markdown(news),
        trade_posture(ticker, side, bars, preview),
        preview,
    )


def submit_paper_order_from_ui(
    symbol: str,
    side: str,
    size_by: str,
    qty: str,
    notional: str,
    order_type: str,
    limit_price: str,
    time_in_force: str,
    confirmed: bool,
) -> JsonDict:
    if not confirmed:
        return {"submitted": False, "error": "Check the confirmation box before submitting a paper order."}

    order = {
        "symbol": symbol.upper().strip(),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }
    qty_value, notional_value, limit_value = normalize_order_inputs(size_by, qty, notional, order_type, limit_price)
    if qty_value:
        order["qty"] = qty_value
    if notional_value:
        order["notional"] = notional_value
    if limit_value:
        order["limit_price"] = limit_value

    return place_paper_order(order)

DEFAULT_STRATEGY_INSTRUCTION = "Check Apple stock. If the current value is less than 800 dollars, buy 2 shares. If it is greater than 800 dollars, buy 1 share. If it is greater than 1000 dollars, buy 1000 dollars worth of stock."


def empty_price_chart() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title="Price chart",
        height=360,
        margin={"l": 40, "r": 40, "t": 50, "b": 40},
        yaxis={"title": "Price"},
        yaxis2={"title": "Volume", "overlaying": "y", "side": "right", "showgrid": False},
    )
    return fig


def reset_manual_trading_form() -> tuple[Any, ...]:
    return (
        "AAPL",        # symbol
        "1Day",        # timeframe
        30,            # lookback_days
        "iex",         # feed
        "buy",         # side
        "market",      # order_type
        "Dollars",     # size_by
        "",            # qty
        "25",          # notional
        "",            # limit_price
        "day",         # time_in_force
        False,          # confirm_paper
        "",            # account_output
        pd.DataFrame(), # positions_output
        "",            # quote_output
        {},            # quote_json
        empty_price_chart(),
        pd.DataFrame(), # bars_output
        "",            # news_output
        "",            # posture_output
        {},            # preview_output
        {},            # submit_output
    )


def reset_agentic_trading_form() -> tuple[Any, ...]:
    return (
        DEFAULT_STRATEGY_INSTRUCTION,
        OPENAI_MODELS[0],
        "iex",
        False,
        False,
        {},
        {},
        "",
        {},
        {},
    )

# %% Notebook cell 29
from openai import OpenAI
import json
import re

OPENAI_MODELS = []
for candidate in [os.getenv("OPENAI_MODEL", "gpt-5-mini"), "gpt-5-mini", "gpt-5", "gpt-5-nano"]:
    if candidate and candidate not in OPENAI_MODELS:
        OPENAI_MODELS.append(candidate)

OPENAI_CLIENT = OpenAI() if os.getenv("OPENAI_API_KEY") else None


def safe_json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def get_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "message":
            for content in getattr(item, "content", []) or []:
                content_text = getattr(content, "text", None)
                if content_text:
                    parts.append(content_text)
    return "\n".join(parts).strip()


def response_function_calls(response: Any) -> list[Any]:
    return [
        item
        for item in (getattr(response, "output", []) or [])
        if getattr(item, "type", None) == "function_call"
    ]


def parse_json_object(text: str) -> JsonDict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def latest_successful_tool_result(tool_trace: list[JsonDict], tool_name: str) -> JsonDict | None:
    for entry in reversed(tool_trace):
        if entry.get("tool") != tool_name:
            continue
        output = entry.get("output", {})
        if output.get("ok"):
            result = output.get("result")
            if isinstance(result, dict):
                return result
    return None


def recover_strategy_from_tool_trace(final_text: str, tool_trace: list[JsonDict]) -> JsonDict:
    preview = latest_successful_tool_result(tool_trace, "preview_order")
    quote = latest_successful_tool_result(tool_trace, "get_latest_quote")

    if not preview:
        return {
            "summary": final_text or "The model did not return parseable JSON and no preview_order result was available.",
            "symbol": None,
            "current_price_used": None,
            "matched_condition": None,
            "proposed_order": None,
            "preview": None,
            "recommendation": "needs_review",
            "reasons": ["Model response could not be parsed as JSON, and no successful preview_order call was found."],
            "risks": ["No trade should be submitted until the instruction is reviewed and a valid preview is available."],
            "system_warnings": ["The model did not return the required JSON shape."],
            "requires_user_confirmation": True,
        }

    order = preview.get("order") or None
    quote_payload = preview.get("quote") or quote or {}
    symbol = preview.get("order", {}).get("symbol") if isinstance(preview.get("order"), dict) else quote_payload.get("symbol")
    ok_to_submit = bool(preview.get("ok_to_submit"))
    errors = preview.get("errors", [])

    if ok_to_submit and order:
        recommendation = "submit_paper_order"
        reasons = [
            "Recovered the proposed order from a successful preview_order tool call.",
            "The preview passed local safety checks.",
        ]
    else:
        recommendation = "do_not_submit"
        reasons = [
            "Recovered the preview_order result, but the preview did not pass safety checks.",
            *(str(error) for error in errors),
        ]

    return {
        "summary": final_text or "Recovered strategy from tool calls.",
        "symbol": symbol,
        "current_price_used": preview.get("estimated_price"),
        "matched_condition": "Recovered from model prose and preview_order output.",
        "proposed_order": order if ok_to_submit else None,
        "preview": preview,
        "recommendation": recommendation,
        "reasons": reasons,
        "risks": [
            "Market orders can fill at a different price from the preview if the quote changes before execution.",
            "The IEX feed may not show the full US market, and the latest ask can be missing or zero outside active quoting conditions.",
            "This rule only checks the stated price condition; it does not evaluate fundamentals, news, volatility, or broader portfolio strategy.",
            "Paper trading fills and buying power behavior may differ from live trading.",
        ],
        "system_warnings": [
            "The model did not return the required JSON shape, so this result was reconstructed from the successful preview_order tool output.",
            "Confirm the recovered order matches your instruction before submitting.",
        ],
        "requires_user_confirmation": True,
    }


def model_tool_schemas() -> list[JsonDict]:
    # Only expose safe tools. The execution tools are deliberately omitted.
    return [schema for schema in TOOL_SCHEMAS if schema["name"] in SAFE_TOOL_NAMES]


def add_default_feed(tool_name: str, arguments: JsonDict, feed: str) -> JsonDict:
    args = dict(arguments)
    if tool_name in {"get_latest_quote", "get_historical_bars", "preview_order"}:
        args.setdefault("feed", feed)
    return args


def strategy_system_prompt(feed: str) -> str:
    return f"""
You are a cautious paper-trading assistant for an educational Alpaca paper trading notebook.

Your job:
1. Interpret the user's natural-language trading instruction.
2. Use tools to inspect market/account data and preview any proposed order.
3. Never submit an order. You only produce a proposed order for human approval.
4. If conditions overlap, apply the most specific condition first. Example: if the user gives > 800 and > 1000, evaluate > 1000 before > 800.
5. If the user names a common company, map it to its ticker when clear: Apple=AAPL, Microsoft=MSFT, Nvidia=NVDA, Amazon=AMZN, Google/Alphabet=GOOGL, Meta=META, Tesla=TSLA.
6. Use the market data feed `{feed}` unless the user explicitly asks otherwise.
7. Prefer market orders with time_in_force day unless the user explicitly asks for a limit order.
8. Before proposing submission, call preview_order for the exact order you want the user to approve.
9. This is not financial advice. Give a practical paper-trading recommendation and risks.

Return JSON only, with this shape:
{{
  "summary": "short plain-English summary",
  "symbol": "ticker or null",
  "current_price_used": "number as string or null",
  "matched_condition": "condition that fired or null",
  "proposed_order": {{"symbol": "...", "side": "buy/sell", "type": "market/limit", "time_in_force": "day", "qty": "..."}} or null,
  "preview": {{}} or null,
  "recommendation": "submit_paper_order | do_not_submit | needs_review",
  "reasons": ["..."],
  "risks": ["..."],
  "requires_user_confirmation": true
}}
""".strip()


def run_strategy_agent(user_instruction: str, model: str, feed: str = "iex", max_tool_rounds: int = 6) -> JsonDict:
    if OPENAI_CLIENT is None:
        return {
            "error": "OPENAI_API_KEY is not set. Add it to .env and rerun the setup cells.",
            "proposed_order": None,
            "requires_user_confirmation": True,
        }
    if not user_instruction.strip():
        return {
            "error": "Enter a natural-language trading instruction first.",
            "proposed_order": None,
            "requires_user_confirmation": True,
        }

    tools = model_tool_schemas()
    response = OPENAI_CLIENT.responses.create(
        model=model,
        instructions=strategy_system_prompt(feed),
        input=user_instruction,
        tools=tools,
        tool_choice="auto",
    )

    tool_trace: list[JsonDict] = []
    for _ in range(max_tool_rounds):
        calls = response_function_calls(response)
        if not calls:
            break

        tool_outputs = []
        for call in calls:
            name = getattr(call, "name", "")
            call_id = getattr(call, "call_id", "")
            raw_arguments = getattr(call, "arguments", "{}") or "{}"
            trace_arguments: Any = raw_arguments
            try:
                arguments = json.loads(raw_arguments)
                arguments = add_default_feed(name, arguments, feed)
                trace_arguments = arguments
                result = call_tool(name, arguments)
                output = {"ok": True, "result": result}
            except Exception as exc:
                output = {"ok": False, "error": str(exc)}

            tool_trace.append({"tool": name, "arguments": trace_arguments, "output": output})
            tool_outputs.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": safe_json_dumps(output),
            })

        response = OPENAI_CLIENT.responses.create(
            model=model,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=tools,
        )

    final_text = get_response_text(response)
    try:
        final = parse_json_object(final_text)
    except Exception:
        final = recover_strategy_from_tool_trace(final_text, tool_trace)

    final["tool_trace"] = tool_trace
    final["raw_model_text"] = final_text
    return final


def strategy_markdown(result: JsonDict) -> str:
    if result.get("error"):
        return f"### Strategy assistant\n\n**Error:** {result['error']}"

    reasons = "\n".join(f"- {reason}" for reason in result.get("reasons", [])) or "- No reasons returned."
    risks = "\n".join(f"- {risk}" for risk in result.get("risks", [])) or "- No risks returned."
    system_warnings = "\n".join(f"- {warning}" for warning in result.get("system_warnings", []))
    proposed_order = result.get("proposed_order")
    order_text = f"```json\n{safe_json_dumps(proposed_order)}\n```" if proposed_order else "No order proposed."
    submission_note = (
        "YOLO mode handled submission automatically; check the model-proposed paper order result."
        if result.get("requires_user_confirmation") is False
        else "Final submission still requires your checkbox confirmation."
    )

    return f"""
### Strategy assistant

{result.get('summary', 'No summary returned.')}

Recommendation: **{result.get('recommendation', 'needs_review')}**  
Symbol: **{result.get('symbol', 'n/a')}**  
Current price used: **{result.get('current_price_used', 'n/a')}**  
Matched condition: **{result.get('matched_condition', 'n/a')}**

Proposed paper order:
{order_text}

Reasons:
{reasons}

Risks:
{risks}

System warnings:
{system_warnings or "- None"}

{submission_note}
"""


def analyze_natural_language_strategy(user_instruction: str, model: str, feed: str) -> tuple[str, JsonDict, JsonDict, JsonDict]:
    result = run_strategy_agent(user_instruction, model=model, feed=feed)
    proposed_order = result.get("proposed_order") or {}
    return strategy_markdown(result), result, proposed_order, proposed_order


def yolo_submission_allowed(result: JsonDict, proposed_order: JsonDict) -> tuple[bool, str | None]:
    if not proposed_order:
        return False, "No proposed order is available."
    if result.get("recommendation") != "submit_paper_order":
        return False, f"Recommendation is {result.get('recommendation')!r}, not 'submit_paper_order'."
    preview = result.get("preview") or {}
    if not preview.get("ok_to_submit"):
        return False, "Preview did not pass safety checks."
    if preview.get("order") != proposed_order:
        return False, "Proposed order does not exactly match the previewed order."
    return True, None


def analyze_natural_language_strategy_with_yolo(
    user_instruction: str,
    model: str,
    feed: str,
    yolo_enabled: bool,
) -> tuple[str, JsonDict, JsonDict, JsonDict, JsonDict]:
    result = run_strategy_agent(user_instruction, model=model, feed=feed)
    proposed_order = result.get("proposed_order") or {}
    submit_result: JsonDict = {"submitted": False, "mode": "manual_confirmation_required"}

    if yolo_enabled:
        allowed, reason = yolo_submission_allowed(result, proposed_order)
        warnings = result.setdefault("system_warnings", [])
        if allowed:
            submit_result = place_paper_order(proposed_order)
            submit_result["mode"] = "yolo_auto_submitted_paper_order"
            result["requires_user_confirmation"] = False
            warnings.append("YOLO was enabled, so the previewed paper order was submitted automatically.")
        else:
            submit_result = {"submitted": False, "mode": "yolo_blocked", "reason": reason}
            warnings.append(f"YOLO was enabled, but auto-submit was blocked: {reason}")

    return strategy_markdown(result), result, proposed_order, proposed_order, submit_result


def submit_model_proposed_order(proposed_order: JsonDict, confirmed: bool) -> JsonDict:
    if not confirmed:
        return {"submitted": False, "error": "Review the model recommendation and check the confirmation box first."}
    if not proposed_order:
        return {"submitted": False, "error": "No proposed order is available to submit."}
    return place_paper_order(proposed_order)

# %% Notebook cell 30
with gr.Blocks(css=TRADING_DASHBOARD_CSS, theme=gr.themes.Monochrome(), title="Paper Equity Trading Dashboard") as trading_ui:
    gr.Markdown("# Paper Equity Trading Dashboard")

    with gr.Tabs():
        with gr.Tab("Manual Trading"):
            with gr.Row(equal_height=True, elem_classes=["dashboard-grid"]):
                with gr.Column(scale=4, min_width=320):
                    symbol = gr.Dropdown(DEFAULT_SYMBOLS, value="AAPL", allow_custom_value=True, label="Symbol")
                    timeframe = gr.Dropdown(["1Min", "5Min", "15Min", "1Hour", "1Day"], value="1Day", label="Timeframe")
                    lookback_days = gr.Slider(5, 180, value=30, step=1, label="Lookback days")
                    feed = gr.Dropdown(["iex", "sip"], value="iex", label="Market data feed")

                    with gr.Row(elem_classes=["controls"]):
                        side = gr.Radio(["buy", "sell"], value="buy", label="Side")
                        order_type = gr.Dropdown(["market", "limit"], value="market", label="Order type")

                    size_by = gr.Radio(["Dollars", "Shares"], value="Dollars", label="Size by")
                    with gr.Row(equal_height=True):
                        qty = gr.Textbox(label="Quantity", placeholder="Used when Size by = Shares")
                        notional = gr.Textbox(label="Dollar amount", value="25", placeholder="Used when Size by = Dollars")

                    with gr.Row(equal_height=True):
                        limit_price = gr.Textbox(label="Limit price", placeholder="Required for limit orders")
                        time_in_force = gr.Dropdown(["day", "gtc", "ioc", "fok"], value="day", label="Time in force")

                    refresh = gr.Button("Refresh quote and preview", elem_classes=["primary-action"])
                    confirm_paper = gr.Checkbox(label="I understand this submits a paper order, not a live order")
                    submit_paper = gr.Button("Submit manual paper order", elem_classes=["danger-action"])
                    reset_manual = gr.Button("Reset manual form")

                    account_output = gr.Markdown(label="Account", elem_classes=["metric-card"])
                    positions_output = gr.DataFrame(label="Open positions", interactive=False, wrap=True)

                with gr.Column(scale=8, min_width=620):
                    with gr.Row(equal_height=True, elem_classes=["dashboard-grid"]):
                        with gr.Column(scale=5):
                            quote_output = gr.Markdown(label="Quote", elem_classes=["metric-card"])
                            posture_output = gr.Markdown(label="Paper-trade posture", elem_classes=["metric-card"])
                        with gr.Column(scale=7):
                            chart_output = gr.Plot(label="Price chart")

                    with gr.Row(equal_height=True, elem_classes=["dashboard-grid"]):
                        with gr.Column(scale=6):
                            quote_json = gr.JSON(label="Raw quote", height=240)
                            preview_output = gr.JSON(label="Order preview", height=300)
                            submit_output = gr.JSON(label="Manual paper order result", height=240)
                        with gr.Column(scale=6):
                            bars_output = gr.DataFrame(label="Recent bars", interactive=False, wrap=True)
                            news_output = gr.Markdown(label="News", elem_classes=["metric-card"])

        with gr.Tab("Agentic Trading"):
            with gr.Row(equal_height=True, elem_classes=["dashboard-grid", "yolo-row"]):
                gr.Markdown("### Agentic Trading")
                yolo_enabled = gr.Checkbox(label="YOLO auto-submit paper order", value=False, elem_classes=["yolo-toggle"])

            with gr.Row(equal_height=False, elem_classes=["dashboard-grid", "agent-grid"]):
                with gr.Column(scale=4, min_width=360, elem_classes=["agent-controls"]):
                    strategy_instruction = gr.Textbox(
                        label="Instruction",
                        lines=8,
                        value=DEFAULT_STRATEGY_INSTRUCTION,
                    )
                    strategy_model = gr.Dropdown(OPENAI_MODELS, value=OPENAI_MODELS[0], label="Model")
                    agent_feed = gr.Dropdown(["iex", "sip"], value="iex", label="Market data feed")
                    analyze_strategy = gr.Button("Analyze instruction", elem_classes=["primary-action"])
                    reset_agentic = gr.Button("Reset agentic form")

                    gr.Markdown("### Final approval")
                    confirm_model_order = gr.Checkbox(label="I reviewed and approve the model-proposed paper order")
                    submit_model_order = gr.Button("Submit model-proposed paper order", elem_classes=["danger-action"])
                    proposed_order_state = gr.State({})
                    model_submit_output = gr.JSON(label="Model-proposed paper order result", height=220, elem_classes=["agent-json"])

                with gr.Column(scale=8, min_width=620, elem_classes=["agent-results"]):
                    strategy_output = gr.Markdown(label="Model recommendation", elem_classes=["metric-card", "agent-summary"])

                    gr.Markdown("### Raw results")
                    with gr.Row(equal_height=True, elem_classes=["dashboard-grid"]):
                        with gr.Column(scale=5):
                            proposed_order_output = gr.JSON(label="Model proposed order", height=220, elem_classes=["agent-json"])
                        with gr.Column(scale=7):
                            strategy_json = gr.JSON(label="Model strategy details", height=520, elem_classes=["agent-json"])

    refresh.click(
        fn=refresh_dashboard,
        inputs=[symbol, timeframe, lookback_days, feed, side, size_by, qty, notional, order_type, limit_price],
        outputs=[account_output, positions_output, quote_output, quote_json, chart_output, bars_output, news_output, posture_output, preview_output],
    )
    submit_paper.click(
        fn=submit_paper_order_from_ui,
        inputs=[symbol, side, size_by, qty, notional, order_type, limit_price, time_in_force, confirm_paper],
        outputs=[submit_output],
    )
    reset_manual.click(
        fn=reset_manual_trading_form,
        inputs=[],
        outputs=[
            symbol, timeframe, lookback_days, feed, side, order_type, size_by, qty, notional,
            limit_price, time_in_force, confirm_paper, account_output, positions_output, quote_output,
            quote_json, chart_output, bars_output, news_output, posture_output, preview_output, submit_output,
        ],
    )
    analyze_strategy.click(
        fn=analyze_natural_language_strategy_with_yolo,
        inputs=[strategy_instruction, strategy_model, agent_feed, yolo_enabled],
        outputs=[strategy_output, strategy_json, proposed_order_state, proposed_order_output, model_submit_output],
    )
    submit_model_order.click(
        fn=submit_model_proposed_order,
        inputs=[proposed_order_state, confirm_model_order],
        outputs=[model_submit_output],
    )
    reset_agentic.click(
        fn=reset_agentic_trading_form,
        inputs=[],
        outputs=[
            strategy_instruction, strategy_model, agent_feed, yolo_enabled, confirm_model_order, proposed_order_state,
            model_submit_output, strategy_output, strategy_json, proposed_order_output,
        ],
    )

if __name__ == "__main__":
    auth = None
    if os.getenv("APP_USERNAME") and os.getenv("APP_PASSWORD"):
        auth = (os.getenv("APP_USERNAME"), os.getenv("APP_PASSWORD"))
    trading_ui.launch(auth=auth)
