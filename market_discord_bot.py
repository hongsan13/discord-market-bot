import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yfinance as yf


JST = timezone(timedelta(hours=9))

STARTING_CAPITAL = 1_000_000
MAX_POSITIONS = 5
MAX_REPORTS = 120

DATA_PATH = Path("data/reports.json")
DOCS_DATA_PATH = Path("docs/data/reports.json")

ALERT_15M_DROP_PCT = -3.0
ALERT_DAY_DROP_PCT = -6.0
ALERT_COOLDOWN_MINUTES = 180

WATCHLIST = [
    # memory / storage
    {"ticker": "WDC", "name": "Western Digital", "currency": "USD", "theme": "メモリ・ストレージ"},
    {"ticker": "SNDK", "name": "SanDisk", "currency": "USD", "theme": "メモリ・ストレージ"},
    {"ticker": "285A.T", "name": "Kioxia", "currency": "JPY", "theme": "メモリ・ストレージ"},
    {"ticker": "MU", "name": "Micron", "currency": "USD", "theme": "メモリ・ストレージ"},
    {"ticker": "STX", "name": "Seagate", "currency": "USD", "theme": "ストレージ"},

    # AI compute / cloud / server
    {"ticker": "NVDA", "name": "NVIDIA", "currency": "USD", "theme": "AI半導体"},
    {"ticker": "AMD", "name": "AMD", "currency": "USD", "theme": "AI半導体"},
    {"ticker": "AVGO", "name": "Broadcom", "currency": "USD", "theme": "AI・ネットワーク"},
    {"ticker": "SMCI", "name": "Super Micro Computer", "currency": "USD", "theme": "AIサーバー"},
    {"ticker": "DELL", "name": "Dell", "currency": "USD", "theme": "AIサーバー"},
    {"ticker": "MSFT", "name": "Microsoft", "currency": "USD", "theme": "AIクラウド"},
    {"ticker": "GOOGL", "name": "Alphabet", "currency": "USD", "theme": "AIクラウド"},
    {"ticker": "AMZN", "name": "Amazon", "currency": "USD", "theme": "AIクラウド"},

    # foundry
    {"ticker": "TSM", "name": "TSMC ADR", "currency": "USD", "theme": "ファウンドリ"},

    # semiconductor equipment
    {"ticker": "8035.T", "name": "Tokyo Electron", "currency": "JPY", "theme": "半導体製造装置"},
    {"ticker": "6857.T", "name": "Advantest", "currency": "JPY", "theme": "半導体製造装置"},
    {"ticker": "6146.T", "name": "Disco", "currency": "JPY", "theme": "半導体製造装置"},
    {"ticker": "ASML", "name": "ASML", "currency": "USD", "theme": "半導体製造装置"},
    {"ticker": "AMAT", "name": "Applied Materials", "currency": "USD", "theme": "半導体製造装置"},

    # data center infrastructure
    {"ticker": "VRT", "name": "Vertiv", "currency": "USD", "theme": "データセンター電源・冷却"},
    {"ticker": "ETN", "name": "Eaton", "currency": "USD", "theme": "データセンター電源・冷却"},
    {"ticker": "ANET", "name": "Arista Networks", "currency": "USD", "theme": "データセンターネットワーク"},

    # cybersecurity
    {"ticker": "CRWD", "name": "CrowdStrike", "currency": "USD", "theme": "サイバーセキュリティ"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "currency": "USD", "theme": "サイバーセキュリティ"},

    # defense / space
    {"ticker": "7011.T", "name": "Mitsubishi Heavy Industries", "currency": "JPY", "theme": "防衛・宇宙"},
    {"ticker": "7012.T", "name": "Kawasaki Heavy Industries", "currency": "JPY", "theme": "防衛・宇宙"},
    {"ticker": "7013.T", "name": "IHI", "currency": "JPY", "theme": "防衛・宇宙"},
]


def now_jst() -> datetime:
    return datetime.now(JST)


def is_active_window(current: datetime) -> bool:
    return current.hour >= 9 or current.hour <= 6


def is_hourly_trade_time(current: datetime) -> bool:
    return is_active_window(current) and current.minute < 15


def is_daily_report_time(current: datetime) -> bool:
    return current.hour == 21 and current.minute < 15


def safe_float(value):
    try:
        if value is None:
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except Exception:
        return None


def yen(value) -> str:
    if value is None:
        return "-"
    return f"{int(round(value)):,}円"


def pct(value) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def price(value, currency) -> str:
    if value is None:
        return "-"
    if currency == "JPY":
        return f"{value:,.0f}円"
    return f"{value:,.2f}ドル"


def fetch_last_and_change(ticker: str):
    hist = yf.Ticker(ticker).history(period="7d", interval="1d", auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None, None

    closes = []
    for raw in hist["Close"].dropna().tolist():
        value = safe_float(raw)
        if value is not None and value > 0:
            closes.append(value)

    if not closes:
        return None, None

    last = closes[-1]

    if len(closes) < 2:
        return last, None

    previous = closes[-2]
    if previous <= 0:
        return last, None

    change = ((last / previous) - 1.0) * 100.0
    return last, change


def fetch_intraday_change(ticker: str):
    hist = yf.Ticker(ticker).history(
        period="2d",
        interval="15m",
        prepost=True,
        auto_adjust=False,
    )

    if hist is None or hist.empty or "Close" not in hist.columns:
        return None, None

    closes = []
    for raw in hist["Close"].dropna().tolist():
        value = safe_float(raw)
        if value is not None and value > 0:
            closes.append(value)

    if not closes:
        return None, None

    last = closes[-1]

    if len(closes) < 2:
        return last, None

    previous = closes[-2]
    if previous <= 0:
        return last, None

    change_15m = ((last / previous) - 1.0) * 100.0
    return last, change_15m


def fetch_usd_jpy() -> float:
    last, _ = fetch_last_and_change("JPY=X")
    if last is None:
        return 155.0
    return last


def to_jpy(value, currency: str, usd_jpy: float):
    if value is None:
        return None
    if currency == "USD":
        return value * usd_jpy
    return value


def fetch_market_data():
    usd_jpy = fetch_usd_jpy()
    rows = []

    for item in WATCHLIST:
        ticker = item["ticker"]
        daily_last = None
        daily_change = None
        intraday_last = None
        change_15m = None
        error = None

        try:
            daily_last, daily_change = fetch_last_and_change(ticker)
            intraday_last, change_15m = fetch_intraday_change(ticker)
        except Exception as exc:
            error = str(exc)[:120]

        last = intraday_last if intraday_last is not None else daily_last
        last_jpy = to_jpy(last, item["currency"], usd_jpy)

        rows.append(
            {
                "ticker": ticker,
                "name": item["name"],
                "theme": item["theme"],
                "currency": item["currency"],
                "last": last,
                "last_jpy": last_jpy,
                "pct_change": daily_change,
                "change_15m": change_15m,
                "error": error,
            }
        )

    rows.sort(
        key=lambda row: row["pct_change"] if row["pct_change"] is not None else -9999,
        reverse=True,
    )
    return rows, usd_jpy


def default_state():
    return {
        "starting_capital": STARTING_CAPITAL,
        "cash": STARTING_CAPITAL,
        "positions": [],
        "reports": [],
        "latest": None,
        "last_alerts": {},
        "last_daily_report_date": None,
    }


def load_state():
    if not DATA_PATH.exists():
        return default_state()

    try:
        state = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return default_state()

    state.setdefault("starting_capital", STARTING_CAPITAL)
    state.setdefault("cash", STARTING_CAPITAL)
    state.setdefault("positions", [])
    state.setdefault("reports", [])
    state.setdefault("latest", None)
    state.setdefault("last_alerts", {})
    state.setdefault("last_daily_report_date", None)
    return state


def write_state(state):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    text = json.dumps(state, ensure_ascii=False, indent=2)
    DATA_PATH.write_text(text, encoding="utf-8")
    DOCS_DATA_PATH.write_text(text, encoding="utf-8")


def refresh_positions(positions, market_map):
    refreshed = []

    for pos in positions:
        ticker = pos.get("ticker")
        qty = int(pos.get("qty", 0))
        buy_price_jpy = safe_float(pos.get("buy_price_jpy"))
        row = market_map.get(ticker, {})
        current_price_jpy = safe_float(row.get("last_jpy")) or buy_price_jpy

        if qty <= 0 or current_price_jpy is None:
            continue

        market_value_jpy = int(qty * current_price_jpy)
        cost_jpy = int(qty * buy_price_jpy) if buy_price_jpy else market_value_jpy
        pnl_jpy = market_value_jpy - cost_jpy
        pnl_pct = (pnl_jpy / cost_jpy * 100.0) if cost_jpy > 0 else 0.0

        new_pos = dict(pos)
        new_pos["current_price_jpy"] = current_price_jpy
        new_pos["market_value_jpy"] = market_value_jpy
        new_pos["pnl_jpy"] = pnl_jpy
        new_pos["pnl_pct"] = pnl_pct
        refreshed.append(new_pos)

    return refreshed


def update_paper_portfolio(state, market_data, current):
    market_map = {row["ticker"]: row for row in market_data}
    cash = int(state.get("cash", STARTING_CAPITAL))
    positions = refresh_positions(state.get("positions", []), market_map)
    decisions = []

    kept_positions = []

    for pos in positions:
        ticker = pos["ticker"]
        row = market_map.get(ticker, {})
        daily_change = row.get("pct_change")
        change_15m = row.get("change_15m")
        pnl_pct = pos.get("pnl_pct", 0.0)

        should_sell = False
        reason = None

        if change_15m is not None and change_15m <= ALERT_15M_DROP_PCT:
            should_sell = True
            reason = f"15分変化率が大きく下落: {pct(change_15m)}"
        elif daily_change is not None and daily_change <= ALERT_DAY_DROP_PCT:
            should_sell = True
            reason = f"日次下落が大きい: {pct(daily_change)}"
        elif pnl_pct <= -12.0:
            should_sell = True
            reason = f"含み損が大きい: {pct(pnl_pct)}"

        if should_sell:
            proceeds = int(pos["market_value_jpy"])
            cash += proceeds
            decisions.append(
                {
                    "action": "paper_sell",
                    "ticker": ticker,
                    "qty": pos["qty"],
                    "amount_jpy": proceeds,
                    "reason": reason,
                }
            )
        else:
            kept_positions.append(pos)

    positions = kept_positions
    held = {pos["ticker"] for pos in positions}

    for cand in market_data:
        if len(positions) >= MAX_POSITIONS:
            break

        if cand["ticker"] in held:
            continue

        if cand["pct_change"] is None or cand["pct_change"] < 1.5:
            continue

        if cand["last_jpy"] is None or cand["last_jpy"] <= 0:
            continue

        allocation = min(int(STARTING_CAPITAL * 0.20), int(cash * 0.35))
        qty = int(allocation // cand["last_jpy"])

        if qty <= 0:
            continue

        cost = int(qty * cand["last_jpy"])

        if cost > cash:
            continue

        cash -= cost
        position = {
            "ticker": cand["ticker"],
            "name": cand["name"],
            "qty": qty,
            "buy_price_jpy": cand["last_jpy"],
            "current_price_jpy": cand["last_jpy"],
            "market_value_jpy": cost,
            "pnl_jpy": 0,
            "pnl_pct": 0.0,
            "bought_at": current.isoformat(),
        }
        positions.append(position)
        held.add(cand["ticker"])

        decisions.append(
            {
                "action": "paper_buy",
                "ticker": cand["ticker"],
                "qty": qty,
                "amount_jpy": cost,
                "reason": f"監視銘柄内で上昇率が高い: {pct(cand['pct_change'])}",
            }
        )

    positions = refresh_positions(positions, market_map)
    total_position_value = sum(int(pos.get("market_value_jpy", 0)) for pos in positions)
    total_value = cash + total_position_value
    pnl_jpy = total_value - STARTING_CAPITAL
    pnl_pct = pnl_jpy / STARTING_CAPITAL * 100.0

    state["cash"] = cash
    state["positions"] = positions

    portfolio = {
        "starting_capital": STARTING_CAPITAL,
        "cash": cash,
        "position_value": total_position_value,
        "total_value": total_value,
        "pnl_jpy": pnl_jpy,
        "pnl_pct": pnl_pct,
        "positions": positions,
    }

    if not decisions:
        decisions.append(
            {
                "action": "hold",
                "ticker": "-",
                "qty": 0,
                "amount_jpy": 0,
                "reason": "新規売買条件を満たす銘柄なし。ペーパートレードは保有継続。",
            }
        )

    return portfolio, decisions


def detect_alerts(state, market_data, current):
    last_alerts = state.setdefault("last_alerts", {})
    alerts = []

    for row in market_data:
        ticker = row["ticker"]
        reasons = []

        change_15m = row.get("change_15m")
        daily_change = row.get("pct_change")

        if change_15m is not None and change_15m <= ALERT_15M_DROP_PCT:
            reasons.append(f"15分変化率 {pct(change_15m)}")

        if daily_change is not None and daily_change <= ALERT_DAY_DROP_PCT:
            reasons.append(f"日次変化率 {pct(daily_change)}")

        if not reasons:
            continue

        last_sent_raw = last_alerts.get(ticker)
        if last_sent_raw:
            try:
                last_sent = datetime.fromisoformat(last_sent_raw)
                elapsed = current - last_sent
                if elapsed < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
                    continue
            except Exception:
                pass

        alerts.append(
            {
                "ticker": ticker,
                "name": row["name"],
                "price": row["last"],
                "currency": row["currency"],
                "pct_change": daily_change,
                "change_15m": change_15m,
                "reasons": reasons,
            }
        )
        last_alerts[ticker] = current.isoformat()

    return alerts


def build_report(state, market_data, usd_jpy, portfolio, decisions, current):
    return {
        "date": current.strftime("%Y-%m-%d"),
        "time": current.strftime("%H:%M:%S"),
        "generated_at": current.isoformat(),
        "title": "Daily Discord Market Report",
        "universe": "AI/半導体インフラ",
        "paper_trade": True,
        "real_trade": False,
        "usd_jpy": usd_jpy,
        "market_data": market_data,
        "portfolio": portfolio,
        "decisions": decisions,
    }


def save_state(state, report):
    state["latest"] = report
    reports = state.get("reports", [])
    reports.append(report)
    state["reports"] = reports[-MAX_REPORTS:]
    write_state(state)


def make_discord_message(report):
    market = report["market_data"]
    portfolio = report["portfolio"]
    decisions = report["decisions"]

    top = market[:7]
    lines = []
    lines.append("**Daily Discord Market Report**")
    lines.append(f"{report['date']} {report['time']} JST")
    lines.append("")
    lines.append("**AI/半導体インフラ監視 上位銘柄**")

    for row in top:
        lines.append(
            f"- {row['ticker']} {row['name']}: {price(row['last'], row['currency'])} / 日次 {pct(row['pct_change'])} / 15分 {pct(row.get('change_15m'))} / {row['theme']}"
        )

    lines.append("")
    lines.append("**100万円ペーパートレード**")
    lines.append(f"- 総資産: {yen(portfolio['total_value'])}")
    lines.append(f"- 現金: {yen(portfolio['cash'])}")
    lines.append(f"- 評価額: {yen(portfolio['position_value'])}")
    lines.append(f"- 損益: {yen(portfolio['pnl_jpy'])} ({pct(portfolio['pnl_pct'])})")
    lines.append("")

    if portfolio["positions"]:
        lines.append("**保有中**")
        for pos in portfolio["positions"]:
            lines.append(
                f"- {pos['ticker']}: {pos['qty']}株 / 評価 {yen(pos['market_value_jpy'])} / 損益 {yen(pos['pnl_jpy'])} ({pct(pos['pnl_pct'])})"
            )
        lines.append("")

    lines.append("**判断**")
    for item in decisions:
        lines.append(f"- {item['action']}: {item['ticker']} - {item['reason']}")

    lines.append("")
    lines.append("※実売買なし。GitHub Actions上のペーパートレード記録のみ。")

    message = "\n".join(lines)
    return message[:1900]


def make_alert_message(alerts, current):
    lines = []
    lines.append("**Market Alert**")
    lines.append(f"{current.strftime('%Y-%m-%d %H:%M:%S')} JST")
    lines.append("")
    lines.append("急落条件に該当する銘柄を検知。")
    lines.append("")

    for alert in alerts:
        lines.append(
            f"- {alert['ticker']} {alert['name']}: {price(alert['price'], alert['currency'])} / 日次 {pct(alert['pct_change'])} / 15分 {pct(alert['change_15m'])}"
        )
        lines.append(f"  - 理由: {', '.join(alert['reasons'])}")

    lines.append("")
    lines.append("※実売買なし。監視アラートのみ。")

    return "\n".join(lines)[:1900]


def send_discord_content(content):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set.")

    payload = {"content": content}
    response = requests.post(webhook_url, json=payload, timeout=20)

    if response.status_code >= 300:
        raise RuntimeError(f"Discord webhook failed: {response.status_code} {response.text[:200]}")


def send_discord_report(report):
    send_discord_content(make_discord_message(report))


def main():
    current = now_jst()

    if not is_active_window(current):
        print(f"Outside active window: {current.isoformat()}")
        return

    state = load_state()
    market_data, usd_jpy = fetch_market_data()

    alerts = detect_alerts(state, market_data, current)
    if alerts:
        send_discord_content(make_alert_message(alerts, current))
        write_state(state)
        print(f"Sent {len(alerts)} alert(s).")

    if not is_hourly_trade_time(current):
        print(f"Monitor only: {current.isoformat()}")
        return

    portfolio, decisions = update_paper_portfolio(state, market_data, current)
    report = build_report(state, market_data, usd_jpy, portfolio, decisions, current)

    today = current.strftime("%Y-%m-%d")
    should_send_daily_report = (
        is_daily_report_time(current)
        and state.get("last_daily_report_date") != today
    )

    if should_send_daily_report:
        send_discord_report(report)
        state["last_daily_report_date"] = today
        print("Sent daily Discord report.")

    save_state(state, report)
    print("Paper trade report updated.")


if __name__ == "__main__":
    main()
