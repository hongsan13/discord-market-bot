
import json
import math
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yfinance as yf


JST = timezone(timedelta(hours=9))

STARTING_CAPITAL = 1_000_000
MAX_POSITIONS = 5
MAX_REPORTS = 240

DATA_PATH = Path("data/reports.json")
DOCS_DATA_PATH = Path("docs/data/reports.json")

STRATEGY_VERSION = "v3_buy_discipline"

ALERT_15M_DROP_PCT = -3.0
ALERT_DAY_DROP_PCT = -6.0
ALERT_COOLDOWN_MINUTES = 180

STOP_LOSS_PCT = -8.0
BREAK_EVEN_START_PCT = 10.0
BREAK_EVEN_BUFFER_PCT = 1.0
TRAILING_START_PCT = 15.0
TRAILING_DRAWDOWN_PCT = -7.0
PARTIAL_TAKE_PROFIT_PCT = 20.0

BUY_DAILY_MIN_PCT = 1.2
BUY_DAILY_MAX_PCT = 8.0
BUY_15M_MIN_PCT = -0.7
BUY_15M_MAX_PCT = 2.5

MIN_CASH_RATIO = 0.25
BUY_ALLOCATION_RATIO = 0.10
MAX_POSITION_WEIGHT = 0.22
MAX_THEME_POSITIONS = 2

# v3: 買い規律
# 通常買いは「個別銘柄が強く、かつセクター全体が崩れていない」場合だけ行う。
# セクター全体が暴落している場合は、通常買いを止め、S/A格付け銘柄だけ少額の打診買いを許可する。
BUY_COOLDOWN_HOURS = 36
PROBE_COOLDOWN_HOURS = 12
PORTFOLIO_NORMAL_BUY_STOP_DD_PCT = -3.0
PORTFOLIO_PROBE_STOP_DD_PCT = -8.0
SECTOR_WEAK_AVG_PCT = -2.0
SECTOR_CRASH_AVG_PCT = -4.0
SECTOR_WEAK_RATIO_THRESHOLD = 0.45
SECTOR_CRASH_RATIO_THRESHOLD = 0.30
PROBE_DAILY_MIN_PCT = -12.0
PROBE_DAILY_MAX_PCT = -4.0
PROBE_15M_MIN_PCT = -0.3
PROBE_15M_MAX_PCT = 1.5
PROBE_ALLOCATION_RATIO = 0.04
PROBE_MIN_CASH_RATIO = 0.55

TICKER_GRADES = {
    "NVDA": "S", "TSM": "S", "ASML": "S", "MSFT": "S",
    "AVGO": "A", "AMD": "A", "AMAT": "A", "8035.T": "A", "6857.T": "A", "6146.T": "A",
    "MU": "A", "WDC": "A", "VRT": "A", "ETN": "A", "ANET": "A", "GOOGL": "A", "AMZN": "A",
    "DELL": "B", "STX": "B", "285A.T": "B", "CRWD": "B", "PANW": "B",
    "7011.T": "B", "7012.T": "B", "7013.T": "B",
    "SMCI": "R", "SNDK": "R",
}

GRADE_SCORE = {"S": 12, "A": 8, "B": 4, "R": -4}

WATCHLIST = [
    {"ticker": "WDC", "name": "Western Digital", "currency": "USD", "theme": "メモリ・ストレージ"},
    {"ticker": "SNDK", "name": "SanDisk", "currency": "USD", "theme": "メモリ・ストレージ"},
    {"ticker": "285A.T", "name": "Kioxia", "currency": "JPY", "theme": "メモリ・ストレージ"},
    {"ticker": "MU", "name": "Micron", "currency": "USD", "theme": "メモリ・ストレージ"},
    {"ticker": "STX", "name": "Seagate", "currency": "USD", "theme": "ストレージ"},

    {"ticker": "NVDA", "name": "NVIDIA", "currency": "USD", "theme": "AI半導体"},
    {"ticker": "AMD", "name": "AMD", "currency": "USD", "theme": "AI半導体"},
    {"ticker": "AVGO", "name": "Broadcom", "currency": "USD", "theme": "AI・ネットワーク"},
    {"ticker": "SMCI", "name": "Super Micro Computer", "currency": "USD", "theme": "AIサーバー"},
    {"ticker": "DELL", "name": "Dell", "currency": "USD", "theme": "AIサーバー"},
    {"ticker": "MSFT", "name": "Microsoft", "currency": "USD", "theme": "AIクラウド"},
    {"ticker": "GOOGL", "name": "Alphabet", "currency": "USD", "theme": "AIクラウド"},
    {"ticker": "AMZN", "name": "Amazon", "currency": "USD", "theme": "AIクラウド"},

    {"ticker": "TSM", "name": "TSMC ADR", "currency": "USD", "theme": "ファウンドリ"},

    {"ticker": "8035.T", "name": "Tokyo Electron", "currency": "JPY", "theme": "半導体製造装置"},
    {"ticker": "6857.T", "name": "Advantest", "currency": "JPY", "theme": "半導体製造装置"},
    {"ticker": "6146.T", "name": "Disco", "currency": "JPY", "theme": "半導体製造装置"},
    {"ticker": "ASML", "name": "ASML", "currency": "USD", "theme": "半導体製造装置"},
    {"ticker": "AMAT", "name": "Applied Materials", "currency": "USD", "theme": "半導体製造装置"},

    {"ticker": "VRT", "name": "Vertiv", "currency": "USD", "theme": "データセンター電力・冷却"},
    {"ticker": "ETN", "name": "Eaton", "currency": "USD", "theme": "データセンター電力・冷却"},
    {"ticker": "ANET", "name": "Arista Networks", "currency": "USD", "theme": "データセンターネットワーク"},

    {"ticker": "CRWD", "name": "CrowdStrike", "currency": "USD", "theme": "サイバーセキュリティ"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "currency": "USD", "theme": "サイバーセキュリティ"},

    {"ticker": "7011.T", "name": "Mitsubishi Heavy Industries", "currency": "JPY", "theme": "防衛・宇宙"},
    {"ticker": "7012.T", "name": "Kawasaki Heavy Industries", "currency": "JPY", "theme": "防衛・宇宙"},
    {"ticker": "7013.T", "name": "IHI", "currency": "JPY", "theme": "防衛・宇宙"},
]


def now_jst() -> datetime:
    return datetime.now(JST)


def is_active_window(current: datetime) -> bool:
    return current.hour >= 9 or current.hour <= 6


def get_trade_slot(current: datetime):
    if not is_active_window(current):
        return None
    return current.strftime("%Y-%m-%d-%H")


def is_daily_report_time(current: datetime) -> bool:
    return current.hour == 21


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
                "sector": broad_sector(item["theme"]),
                "grade": TICKER_GRADES.get(ticker, "B"),
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
        "last_trade_slot": None,
        "realized_pnl_jpy": 0,
        "realized_trades": [],
        "portfolio_peak_value_jpy": STARTING_CAPITAL,
        "sector_cooldowns": {},
        "strategy_version": STRATEGY_VERSION,
    }


def infer_peaks_from_reports(state):
    peaks = {}

    for report in state.get("reports", []):
        portfolio = report.get("portfolio", {})
        for pos in portfolio.get("positions", []):
            ticker = pos.get("ticker")
            if not ticker:
                continue

            current_price = safe_float(pos.get("current_price_jpy"))
            pnl_pct = safe_float(pos.get("pnl_pct"))

            item = peaks.setdefault(
                ticker,
                {
                    "peak_price_jpy": None,
                    "peak_pnl_pct": None,
                },
            )

            if current_price is not None:
                old_price = safe_float(item.get("peak_price_jpy"))
                if old_price is None or current_price > old_price:
                    item["peak_price_jpy"] = current_price

            if pnl_pct is not None:
                old_pnl = safe_float(item.get("peak_pnl_pct"))
                if old_pnl is None or pnl_pct > old_pnl:
                    item["peak_pnl_pct"] = pnl_pct

    return peaks


def migrate_state(state):
    state.setdefault("starting_capital", STARTING_CAPITAL)
    state.setdefault("cash", STARTING_CAPITAL)
    state.setdefault("positions", [])
    state.setdefault("reports", [])
    state.setdefault("latest", None)
    state.setdefault("last_alerts", {})
    state.setdefault("last_daily_report_date", None)
    state.setdefault("last_trade_slot", None)
    state.setdefault("realized_pnl_jpy", 0)
    state.setdefault("realized_trades", [])
    state.setdefault("sector_cooldowns", {})

    peak_values = [STARTING_CAPITAL]
    for report in state.get("reports", []):
        value = safe_float(report.get("portfolio", {}).get("total_value"))
        if value is not None:
            peak_values.append(value)
    latest_value = safe_float(state.get("latest", {}).get("portfolio", {}).get("total_value"))
    if latest_value is not None:
        peak_values.append(latest_value)
    existing_peak = safe_float(state.get("portfolio_peak_value_jpy"))
    if existing_peak is not None:
        peak_values.append(existing_peak)
    state["portfolio_peak_value_jpy"] = int(max(peak_values))
    state["strategy_version"] = STRATEGY_VERSION

    peaks = infer_peaks_from_reports(state)

    for pos in state.get("positions", []):
        ticker = pos.get("ticker")
        buy_price = safe_float(pos.get("buy_price_jpy"))
        current_price = safe_float(pos.get("current_price_jpy"))
        current_pnl = safe_float(pos.get("pnl_pct"))

        inferred = peaks.get(ticker, {})
        inferred_peak_price = safe_float(inferred.get("peak_price_jpy"))
        inferred_peak_pnl = safe_float(inferred.get("peak_pnl_pct"))

        existing_peak_price = safe_float(pos.get("peak_price_jpy"))
        existing_peak_pnl = safe_float(pos.get("peak_pnl_pct"))

        peak_price_candidates = [
            value
            for value in [existing_peak_price, inferred_peak_price, current_price, buy_price]
            if value is not None
        ]
        peak_pnl_candidates = [
            value
            for value in [existing_peak_pnl, inferred_peak_pnl, current_pnl]
            if value is not None
        ]

        if peak_price_candidates:
            pos["peak_price_jpy"] = max(peak_price_candidates)
        if peak_pnl_candidates:
            pos["peak_pnl_pct"] = max(peak_pnl_candidates)

        pos.setdefault("partial_taken_20", False)
        pos.setdefault("strategy_version", STRATEGY_VERSION)

    return state


def load_state():
    if not DATA_PATH.exists():
        return default_state()

    try:
        state = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return default_state()

    return migrate_state(state)


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
        current_price_jpy = safe_float(row.get("last_jpy")) or safe_float(pos.get("current_price_jpy")) or buy_price_jpy

        if qty <= 0 or current_price_jpy is None:
            continue

        market_value_jpy = int(qty * current_price_jpy)
        cost_jpy = int(qty * buy_price_jpy) if buy_price_jpy else market_value_jpy
        pnl_jpy = market_value_jpy - cost_jpy
        pnl_pct = (pnl_jpy / cost_jpy * 100.0) if cost_jpy > 0 else 0.0

        previous_peak_price = safe_float(pos.get("peak_price_jpy"))
        peak_price_jpy = current_price_jpy
        if previous_peak_price is not None:
            peak_price_jpy = max(previous_peak_price, current_price_jpy)

        previous_peak_pnl = safe_float(pos.get("peak_pnl_pct"))
        peak_pnl_pct = pnl_pct
        if previous_peak_pnl is not None:
            peak_pnl_pct = max(previous_peak_pnl, pnl_pct)

        drawdown_from_peak_pct = 0.0
        if peak_price_jpy and peak_price_jpy > 0:
            drawdown_from_peak_pct = ((current_price_jpy / peak_price_jpy) - 1.0) * 100.0

        break_even_stop_jpy = None
        if buy_price_jpy is not None and peak_pnl_pct >= BREAK_EVEN_START_PCT:
            break_even_stop_jpy = buy_price_jpy * (1.0 + BREAK_EVEN_BUFFER_PCT / 100.0)

        new_pos = dict(pos)
        new_pos["current_price_jpy"] = current_price_jpy
        new_pos["market_value_jpy"] = market_value_jpy
        new_pos["pnl_jpy"] = pnl_jpy
        new_pos["pnl_pct"] = pnl_pct
        new_pos["peak_price_jpy"] = peak_price_jpy
        new_pos["peak_pnl_pct"] = peak_pnl_pct
        new_pos["drawdown_from_peak_pct"] = drawdown_from_peak_pct
        new_pos["break_even_stop_jpy"] = break_even_stop_jpy
        new_pos.setdefault("partial_taken_20", False)
        new_pos["strategy_version"] = STRATEGY_VERSION

        refreshed.append(new_pos)

    return refreshed


def build_portfolio_snapshot(state, market_data):
    market_map = {row["ticker"]: row for row in market_data}
    cash = int(state.get("cash", STARTING_CAPITAL))
    positions = refresh_positions(state.get("positions", []), market_map)

    total_position_value = sum(int(pos.get("market_value_jpy", 0)) for pos in positions)
    total_value = cash + total_position_value
    pnl_jpy = total_value - STARTING_CAPITAL
    pnl_pct = pnl_jpy / STARTING_CAPITAL * 100.0

    previous_peak = int(state.get("portfolio_peak_value_jpy", STARTING_CAPITAL))
    portfolio_peak = max(previous_peak, total_value)
    state["portfolio_peak_value_jpy"] = portfolio_peak
    portfolio_drawdown_pct = ((total_value / portfolio_peak) - 1.0) * 100.0 if portfolio_peak > 0 else 0.0

    state["positions"] = positions

    return {
        "starting_capital": STARTING_CAPITAL,
        "cash": cash,
        "position_value": total_position_value,
        "total_value": total_value,
        "pnl_jpy": pnl_jpy,
        "pnl_pct": pnl_pct,
        "realized_pnl_jpy": int(state.get("realized_pnl_jpy", 0)),
        "portfolio_peak_value_jpy": portfolio_peak,
        "portfolio_drawdown_pct": portfolio_drawdown_pct,
        "positions": positions,
    }


def record_realized_trade(state, ticker, name, qty, sell_price_jpy, buy_price_jpy, reason, current):
    proceeds = int(qty * sell_price_jpy)
    cost = int(qty * buy_price_jpy) if buy_price_jpy else proceeds
    pnl = proceeds - cost

    state["realized_pnl_jpy"] = int(state.get("realized_pnl_jpy", 0)) + pnl
    trades = state.setdefault("realized_trades", [])
    trades.append(
        {
            "ticker": ticker,
            "name": name,
            "qty": qty,
            "sell_price_jpy": sell_price_jpy,
            "buy_price_jpy": buy_price_jpy,
            "proceeds_jpy": proceeds,
            "cost_jpy": cost,
            "realized_pnl_jpy": pnl,
            "reason": reason,
            "sold_at": current.isoformat(),
        }
    )
    state["realized_trades"] = trades[-100:]

    return proceeds, cost, pnl


def decide_sell_action(pos, row):
    ticker = pos["ticker"]
    daily_change = row.get("pct_change")
    change_15m = row.get("change_15m")
    pnl_pct = safe_float(pos.get("pnl_pct")) or 0.0
    peak_pnl_pct = safe_float(pos.get("peak_pnl_pct")) or pnl_pct
    drawdown = safe_float(pos.get("drawdown_from_peak_pct")) or 0.0
    current_price = safe_float(pos.get("current_price_jpy"))
    break_even_stop = safe_float(pos.get("break_even_stop_jpy"))

    if change_15m is not None and change_15m <= ALERT_15M_DROP_PCT:
        return {
            "type": "sell_all",
            "action": "paper_sell_alert",
            "reason": f"15分変化率が大きく下落: {pct(change_15m)}",
        }

    if daily_change is not None and daily_change <= ALERT_DAY_DROP_PCT:
        return {
            "type": "sell_all",
            "action": "paper_sell_alert",
            "reason": f"日次下落が大きい: {pct(daily_change)}",
        }

    if pnl_pct <= STOP_LOSS_PCT:
        return {
            "type": "sell_all",
            "action": "paper_stop_loss",
            "reason": f"損切りライン到達: {ticker} {pct(pnl_pct)}",
        }

    if peak_pnl_pct >= TRAILING_START_PCT and drawdown <= TRAILING_DRAWDOWN_PCT:
        return {
            "type": "sell_all",
            "action": "paper_trailing_stop",
            "reason": f"利益保護: ピーク利益 {pct(peak_pnl_pct)} から {pct(drawdown)} 下落",
        }

    if break_even_stop is not None and current_price is not None and current_price <= break_even_stop:
        return {
            "type": "sell_all",
            "action": "paper_break_even_stop",
            "reason": f"建値保護ライン割れ: 現在 {yen(current_price)} / 保護ライン {yen(break_even_stop)}",
        }

    if (
        pnl_pct >= PARTIAL_TAKE_PROFIT_PCT
        and int(pos.get("qty", 0)) >= 2
        and not bool(pos.get("partial_taken_20", False))
    ):
        return {
            "type": "sell_partial",
            "action": "paper_take_profit",
            "reason": f"一部利確: 含み益が {pct(PARTIAL_TAKE_PROFIT_PCT)} 以上",
        }

    return None


def broad_sector(theme: str) -> str:
    if theme in {
        "AI半導体",
        "AI・ネットワーク",
        "AI/ネットワーク",
        "AIサーバー",
        "メモリ・ストレージ",
        "メモリ",
        "ストレージ",
        "半導体製造装置",
        "ファウンドリ",
    }:
        return "半導体・AIインフラ"
    if theme in {"データセンター電力・冷却", "データセンター電源/冷却", "データセンターネットワーク"}:
        return "データセンター周辺"
    if theme in {"AIクラウド"}:
        return "AIクラウド"
    if theme in {"サイバーセキュリティ"}:
        return "サイバーセキュリティ"
    if theme in {"防衛・宇宙"}:
        return "防衛・宇宙"
    return theme or "その他"


def theme_counts(positions):
    return Counter(pos.get("theme", "") for pos in positions)


def sector_counts(positions):
    return Counter(broad_sector(pos.get("theme", "")) for pos in positions)


def analyze_sectors(market_data):
    grouped = {}
    for row in market_data:
        sector = row.get("sector") or broad_sector(row.get("theme", ""))
        daily = safe_float(row.get("pct_change"))
        if daily is None:
            continue
        grouped.setdefault(sector, []).append(daily)

    result = {}
    for sector, values in grouped.items():
        count = len(values)
        avg_daily = sum(values) / count if count else 0.0
        weak_ratio = sum(1 for value in values if value <= -3.0) / count if count else 0.0
        crash_ratio = sum(1 for value in values if value <= -6.0) / count if count else 0.0
        positive_ratio = sum(1 for value in values if value > 0.0) / count if count else 0.0

        if avg_daily <= SECTOR_CRASH_AVG_PCT or crash_ratio >= SECTOR_CRASH_RATIO_THRESHOLD:
            status = "crash"
        elif avg_daily <= SECTOR_WEAK_AVG_PCT or weak_ratio >= SECTOR_WEAK_RATIO_THRESHOLD:
            status = "weak"
        elif avg_daily >= 1.0 and positive_ratio >= 0.5:
            status = "strong"
        else:
            status = "neutral"

        result[sector] = {
            "sector": sector,
            "count": count,
            "avg_daily_pct": avg_daily,
            "weak_ratio": weak_ratio,
            "crash_ratio": crash_ratio,
            "positive_ratio": positive_ratio,
            "status": status,
        }

    return result


def get_sector_status(row, sector_stats):
    sector = row.get("sector") or broad_sector(row.get("theme", ""))
    return sector_stats.get(sector, {"sector": sector, "status": "neutral", "avg_daily_pct": 0.0, "weak_ratio": 0.0, "crash_ratio": 0.0})


def parse_dt(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def cooldown_remaining_hours(state, sector, current):
    raw = state.setdefault("sector_cooldowns", {}).get(sector)
    if not raw:
        return 0.0
    until = parse_dt(raw)
    if until is None:
        return 0.0
    remaining = until - current
    if remaining.total_seconds() <= 0:
        return 0.0
    return remaining.total_seconds() / 3600.0


def set_sector_cooldown(state, sector, current, hours=BUY_COOLDOWN_HOURS):
    state.setdefault("sector_cooldowns", {})[sector] = (current + timedelta(hours=hours)).isoformat()


def candidate_score(row, sector_stats=None):
    daily = safe_float(row.get("pct_change"))
    intraday = safe_float(row.get("change_15m"))
    grade = row.get("grade") or TICKER_GRADES.get(row.get("ticker"), "B")

    if daily is None:
        return -9999

    score = daily * 2.0 + GRADE_SCORE.get(grade, 0)

    if intraday is not None:
        score += intraday * 0.5
        if intraday < 0:
            score += intraday * 0.5

    if sector_stats:
        status = get_sector_status(row, sector_stats).get("status")
        if status == "strong":
            score += 4
        elif status == "neutral":
            score += 0
        elif status == "weak":
            score -= 8
        elif status == "crash":
            score -= 16

    return score


def classify_buy_candidate(row, sector_stats, state, current, portfolio, held_sectors):
    ticker = row.get("ticker")
    grade = row.get("grade") or TICKER_GRADES.get(ticker, "B")
    daily = safe_float(row.get("pct_change"))
    intraday = safe_float(row.get("change_15m"))
    last_jpy = safe_float(row.get("last_jpy"))
    sector_info = get_sector_status(row, sector_stats)
    sector = sector_info.get("sector")
    sector_status = sector_info.get("status")
    sector_avg = safe_float(sector_info.get("avg_daily_pct")) or 0.0
    cooldown_hours = cooldown_remaining_hours(state, sector, current)
    portfolio_dd = safe_float(portfolio.get("portfolio_drawdown_pct")) or 0.0
    cash = int(portfolio.get("cash", 0))
    total_value = int(portfolio.get("total_value", STARTING_CAPITAL))
    cash_ratio = cash / total_value if total_value > 0 else 0.0

    if last_jpy is None or last_jpy <= 0:
        return {"ok": False, "reason": "価格データなし"}
    if daily is None:
        return {"ok": False, "reason": "日次変化率なし"}

    # 通常買い: セクターが崩れていないことを必須にする。
    normal_allowed = True
    normal_reason = []

    if grade == "R":
        normal_allowed = False
        normal_reason.append("R格付けは通常買い禁止")
    if sector_status in {"weak", "crash"}:
        normal_allowed = False
        normal_reason.append(f"セクター地合いが弱い: {sector_status} 平均{pct(sector_avg)}")
    if cooldown_hours > 0:
        normal_allowed = False
        normal_reason.append(f"セクター冷却中: 残り{cooldown_hours:.1f}時間")
    if portfolio_dd <= PORTFOLIO_NORMAL_BUY_STOP_DD_PCT and sector != "防衛・宇宙":
        normal_allowed = False
        normal_reason.append(f"総資産ドローダウン中: {pct(portfolio_dd)}")
    if daily < BUY_DAILY_MIN_PCT:
        normal_allowed = False
        normal_reason.append(f"日次上昇率が不足: {pct(daily)}")
    if daily > BUY_DAILY_MAX_PCT:
        normal_allowed = False
        normal_reason.append(f"急騰しすぎで追いかけ回避: {pct(daily)}")
    if intraday is not None and intraday < BUY_15M_MIN_PCT:
        normal_allowed = False
        normal_reason.append(f"短期下落中: 15分{pct(intraday)}")
    if intraday is not None and intraday > BUY_15M_MAX_PCT:
        normal_allowed = False
        normal_reason.append(f"短期急騰しすぎ: 15分{pct(intraday)}")

    if normal_allowed:
        return {
            "ok": True,
            "mode": "normal_momentum",
            "allocation_ratio": BUY_ALLOCATION_RATIO,
            "min_cash_ratio": MIN_CASH_RATIO,
            "reason": f"通常買い: {grade}格付け / 日次{pct(daily)} / 15分{pct(intraday)} / セクター{sector_status}",
        }

    # 打診買い: セクター暴落時に、底値を完全に逃さないための小額枠。
    # ただし、現金が厚い・S/A格付け・短期下落が止まりかけ、という条件を満たす場合だけ。
    probe_allowed = True
    probe_reason = []

    if sector_status not in {"weak", "crash"}:
        probe_allowed = False
        probe_reason.append("セクター暴落局面ではない")
    if grade not in {"S", "A"}:
        probe_allowed = False
        probe_reason.append(f"打診買い対象外格付け: {grade}")
    if daily < PROBE_DAILY_MIN_PCT or daily > PROBE_DAILY_MAX_PCT:
        probe_allowed = False
        probe_reason.append(f"打診買いの日次範囲外: {pct(daily)}")
    if intraday is not None and intraday < PROBE_15M_MIN_PCT:
        probe_allowed = False
        probe_reason.append(f"短期下落が止まっていない: 15分{pct(intraday)}")
    if intraday is not None and intraday > PROBE_15M_MAX_PCT:
        probe_allowed = False
        probe_reason.append(f"反発が急すぎる: 15分{pct(intraday)}")
    if cooldown_hours > BUY_COOLDOWN_HOURS - PROBE_COOLDOWN_HOURS:
        probe_allowed = False
        probe_reason.append(f"損切り直後のため打診買い禁止: 残り{cooldown_hours:.1f}時間")
    if portfolio_dd <= PORTFOLIO_PROBE_STOP_DD_PCT:
        probe_allowed = False
        probe_reason.append(f"総資産ドローダウンが深すぎる: {pct(portfolio_dd)}")
    if cash_ratio < PROBE_MIN_CASH_RATIO:
        probe_allowed = False
        probe_reason.append(f"打診買いには現金不足: 現金比率{pct(cash_ratio * 100)}")
    if sector in held_sectors:
        probe_allowed = False
        probe_reason.append("同一セクターを既に保有中のため打診買いしない")

    if probe_allowed:
        return {
            "ok": True,
            "mode": "rebound_probe",
            "allocation_ratio": PROBE_ALLOCATION_RATIO,
            "min_cash_ratio": PROBE_MIN_CASH_RATIO,
            "reason": f"暴落後の打診買い: {grade}格付け / 日次{pct(daily)} / 15分{pct(intraday)} / セクター平均{pct(sector_avg)}",
        }

    return {"ok": False, "reason": "通常買い不可: " + "; ".join(normal_reason[:3]) + " / 打診買い不可: " + "; ".join(probe_reason[:3])}

def update_paper_portfolio(state, market_data, current):
    market_map = {row["ticker"]: row for row in market_data}
    cash = int(state.get("cash", STARTING_CAPITAL))
    positions = refresh_positions(state.get("positions", []), market_map)
    decisions = []

    kept_positions = []

    for pos in positions:
        ticker = pos["ticker"]
        row = market_map.get(ticker, {})
        current_price = safe_float(pos.get("current_price_jpy"))
        buy_price = safe_float(pos.get("buy_price_jpy"))
        qty = int(pos.get("qty", 0))

        action = decide_sell_action(pos, row)

        if action is None:
            kept_positions.append(pos)
            continue

        if current_price is None or buy_price is None or qty <= 0:
            kept_positions.append(pos)
            continue

        if action["type"] == "sell_all":
            sell_qty = qty
        else:
            sell_qty = max(1, qty // 2)

        proceeds, _, realized_pnl = record_realized_trade(
            state=state,
            ticker=ticker,
            name=pos.get("name", ticker),
            qty=sell_qty,
            sell_price_jpy=current_price,
            buy_price_jpy=buy_price,
            reason=action["reason"],
            current=current,
        )
        cash += proceeds

        decisions.append(
            {
                "action": action["action"],
                "ticker": ticker,
                "qty": sell_qty,
                "amount_jpy": proceeds,
                "realized_pnl_jpy": realized_pnl,
                "reason": action["reason"],
            }
        )

        if action["action"] in {"paper_sell_alert", "paper_stop_loss"}:
            set_sector_cooldown(state, broad_sector(pos.get("theme", "")), current)

        remaining_qty = qty - sell_qty
        if remaining_qty > 0:
            new_pos = dict(pos)
            new_pos["qty"] = remaining_qty
            if action["type"] == "sell_partial":
                new_pos["partial_taken_20"] = True
            kept_positions.append(new_pos)

    positions = kept_positions
    state["cash"] = cash
    state["positions"] = positions
    portfolio_before_buy = build_portfolio_snapshot(state, market_data)

    held = {pos["ticker"] for pos in positions}
    counts = theme_counts(positions)
    total_value = portfolio_before_buy["total_value"]
    min_cash = int(total_value * MIN_CASH_RATIO)

    sector_stats = analyze_sectors(market_data)
    held_sectors = sector_counts(positions)
    candidates = sorted(market_data, key=lambda row: candidate_score(row, sector_stats), reverse=True)

    for cand in candidates:
        if len(positions) >= MAX_POSITIONS:
            break

        ticker = cand["ticker"]
        if ticker in held:
            continue

        buy_decision = classify_buy_candidate(cand, sector_stats, state, current, portfolio_before_buy, held_sectors)
        if not buy_decision.get("ok"):
            continue

        theme = cand.get("theme", "")
        sector = cand.get("sector") or broad_sector(theme)
        if counts[theme] >= MAX_THEME_POSITIONS:
            continue

        last_jpy = safe_float(cand.get("last_jpy"))
        if last_jpy is None or last_jpy <= 0:
            continue

        min_cash_for_buy = int(total_value * buy_decision.get("min_cash_ratio", MIN_CASH_RATIO))
        available_cash = cash - min_cash_for_buy
        if available_cash <= 0:
            break

        allocation_ratio = buy_decision.get("allocation_ratio", BUY_ALLOCATION_RATIO)
        allocation = min(
            int(total_value * allocation_ratio),
            int(STARTING_CAPITAL * 0.15),
            int(available_cash),
        )

        max_position_value = int(total_value * MAX_POSITION_WEIGHT)
        allocation = min(allocation, max_position_value)

        qty = int(allocation // last_jpy)
        if qty <= 0:
            continue

        cost = int(qty * last_jpy)
        if cost > cash or cash - cost < min_cash_for_buy:
            continue

        cash -= cost
        position = {
            "ticker": ticker,
            "name": cand["name"],
            "theme": cand.get("theme", ""),
            "sector": sector,
            "grade": cand.get("grade") or TICKER_GRADES.get(ticker, "B"),
            "qty": qty,
            "buy_price_jpy": last_jpy,
            "current_price_jpy": last_jpy,
            "market_value_jpy": cost,
            "pnl_jpy": 0,
            "pnl_pct": 0.0,
            "peak_price_jpy": last_jpy,
            "peak_pnl_pct": 0.0,
            "drawdown_from_peak_pct": 0.0,
            "break_even_stop_jpy": None,
            "partial_taken_20": False,
            "strategy_version": STRATEGY_VERSION,
            "bought_at": current.isoformat(),
        }
        positions.append(position)
        held.add(ticker)
        counts[theme] += 1
        held_sectors[sector] += 1

        decisions.append(
            {
                "action": "paper_buy",
                "ticker": ticker,
                "qty": qty,
                "amount_jpy": cost,
                "buy_mode": buy_decision.get("mode"),
                "reason": buy_decision.get("reason"),
            }
        )

    state["cash"] = cash
    state["positions"] = positions

    portfolio = build_portfolio_snapshot(state, market_data)

    if not decisions:
        decisions.append(
            {
                "action": "hold",
                "ticker": "-",
                "qty": 0,
                "amount_jpy": 0,
                "reason": "売買条件を満たす銘柄なし。利益保護ルールを維持して保有継続。",
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


def build_outlook(market_data):
    valid = [row for row in market_data if row.get("pct_change") is not None]
    if not valid:
        return {
            "label": "中立",
            "reason": "有効な変化率データが不足",
        }

    changes = [float(row["pct_change"]) for row in valid]
    avg_change = sum(changes) / len(changes)
    positive_ratio = len([v for v in changes if v > 0]) / len(changes)
    sharp_drop_count = len([v for v in changes if v <= ALERT_DAY_DROP_PCT])
    strong_gain_count = len([v for v in changes if v >= 3.0])

    if sharp_drop_count >= 2:
        label = "高ボラ警戒"
        reason = f"日次 {pct(ALERT_DAY_DROP_PCT)} 以下が {sharp_drop_count} 銘柄"
    elif avg_change >= 1.0 and positive_ratio >= 0.6:
        label = "強気"
        reason = f"平均変化率 {pct(avg_change)}、上昇銘柄比率 {positive_ratio:.0%}"
    elif avg_change <= -1.0 and positive_ratio <= 0.4:
        label = "弱気"
        reason = f"平均変化率 {pct(avg_change)}、上昇銘柄比率 {positive_ratio:.0%}"
    elif strong_gain_count >= 4:
        label = "強気寄り"
        reason = f"+3%以上の銘柄が {strong_gain_count} 銘柄"
    else:
        label = "中立"
        reason = f"平均変化率 {pct(avg_change)}、上昇銘柄比率 {positive_ratio:.0%}"

    return {
        "label": label,
        "reason": reason,
        "avg_change_pct": avg_change,
        "positive_ratio": positive_ratio,
        "sharp_drop_count": sharp_drop_count,
        "strong_gain_count": strong_gain_count,
    }


def build_report(state, market_data, usd_jpy, portfolio, decisions, current):
    return {
        "date": current.strftime("%Y-%m-%d"),
        "time": current.strftime("%H:%M:%S"),
        "generated_at": current.isoformat(),
        "title": "Daily Discord Market Report",
        "universe": "AI/半導体インフラ",
        "paper_trade": True,
        "real_trade": False,
        "strategy_version": STRATEGY_VERSION,
        "risk_rules": {
            "stop_loss_pct": STOP_LOSS_PCT,
            "break_even_start_pct": BREAK_EVEN_START_PCT,
            "break_even_buffer_pct": BREAK_EVEN_BUFFER_PCT,
            "trailing_start_pct": TRAILING_START_PCT,
            "trailing_drawdown_pct": TRAILING_DRAWDOWN_PCT,
            "partial_take_profit_pct": PARTIAL_TAKE_PROFIT_PCT,
            "min_cash_ratio": MIN_CASH_RATIO,
            "max_position_weight": MAX_POSITION_WEIGHT,
        },
        "outlook": build_outlook(market_data),
        "usd_jpy": usd_jpy,
        "market_data": market_data,
        "sector_summary": analyze_sectors(market_data),
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
    outlook = report.get("outlook", {})

    top = market[:7]
    lines = []
    lines.append("**Daily Discord Market Report**")
    lines.append(f"{report['date']} {report['time']} JST")
    lines.append(f"Strategy: {report.get('strategy_version', '-')}")
    lines.append("")
    lines.append(f"**翌営業日方向感**: {outlook.get('label', '-')}")
    lines.append(f"- 理由: {outlook.get('reason', '-')}")
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
    lines.append(f"- 確定損益累計: {yen(portfolio.get('realized_pnl_jpy', 0))}")
    lines.append("")

    if portfolio["positions"]:
        lines.append("**保有中**")
        for pos in portfolio["positions"]:
            lines.append(
                f"- {pos['ticker']}: {pos['qty']}株 / 評価 {yen(pos['market_value_jpy'])} / 損益 {yen(pos['pnl_jpy'])} ({pct(pos['pnl_pct'])}) / 高値比 {pct(pos.get('drawdown_from_peak_pct'))}"
            )
        lines.append("")

    lines.append("**判断**")
    for item in decisions:
        realized = item.get("realized_pnl_jpy")
        realized_text = f" / 確定損益 {yen(realized)}" if realized is not None else ""
        lines.append(f"- {item['action']}: {item['ticker']} {item.get('qty', 0)}株 - {item['reason']}{realized_text}")

    lines.append("")
    lines.append("※実売買なし。GitHub Actions上のペーパートレード記録のみ。")

    return "\n".join(lines)[:1900]


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

    trade_slot = get_trade_slot(current)
    last_trade_slot = state.get("last_trade_slot")
    today = current.strftime("%Y-%m-%d")

    should_trade = trade_slot != last_trade_slot
    should_send_daily_report = (
        is_daily_report_time(current)
        and state.get("last_daily_report_date") != today
    )

    report = None

    if should_trade:
        portfolio, decisions = update_paper_portfolio(state, market_data, current)
        report = build_report(state, market_data, usd_jpy, portfolio, decisions, current)
        state["last_trade_slot"] = trade_slot
        print(f"Paper trade executed for slot: {trade_slot}")
    else:
        print(f"Monitor only. Already traded in this hour: {trade_slot}")

        if should_send_daily_report:
            portfolio = build_portfolio_snapshot(state, market_data)
            decisions = [
                {
                    "action": "report_only",
                    "ticker": "-",
                    "qty": 0,
                    "amount_jpy": 0,
                    "reason": "この時間帯のペーパートレードは実行済み。21時通常レポートのみ送信。",
                }
            ]
            report = build_report(state, market_data, usd_jpy, portfolio, decisions, current)

    if should_send_daily_report and report is not None:
        send_discord_report(report)
        state["last_daily_report_date"] = today
        print("Sent daily Discord report.")

    if report is not None:
        save_state(state, report)
        print("Report data updated.")
    else:
        write_state(state)
        print("Monitoring completed.")


if __name__ == "__main__":
    main()
