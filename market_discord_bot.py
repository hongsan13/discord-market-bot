
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

STRATEGY_VERSION = "v6_risk_adjusted_execution"

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

# v4: 守りながら戻るための追加規則
# 暴落後に現金を厚く残しすぎて反発初動を逃す問題を抑える。
# ただし、一気に戻さず、S/A格付け銘柄へ小口で段階的に再エントリーする。
REENTRY_DD_TRIGGER_PCT = -5.0
REENTRY_MIN_CASH_RATIO = 0.70
REENTRY_DAILY_MIN_PCT = 3.0
REENTRY_DAILY_MAX_PCT = 10.0
REENTRY_15M_MIN_PCT = -0.5
REENTRY_15M_MAX_PCT = 2.5
REENTRY_ALLOCATION_RATIO = 0.055
REENTRY_MIN_CASH_AFTER_BUY_RATIO = 0.60
REENTRY_MIN_WAIT_HOURS_AFTER_COOLDOWN = 12
MAX_REENTRY_BUYS_PER_SLOT = 2

# 現金比率が高すぎる場合の小口分散買い。
# 強い地合いで現金が多すぎると機会損失になるため、条件を満たすS/A銘柄へ小さく戻す。
HIGH_CASH_DEPLOY_TRIGGER_RATIO = 0.85
HIGH_CASH_DEPLOY_ALLOCATION_RATIO = 0.035
HIGH_CASH_MIN_AFTER_BUY_RATIO = 0.75
HIGH_CASH_DAILY_MIN_PCT = 1.5
HIGH_CASH_DAILY_MAX_PCT = 6.5
HIGH_CASH_15M_MIN_PCT = -0.4
HIGH_CASH_15M_MAX_PCT = 2.0
MAX_HIGH_CASH_BUYS_PER_SLOT = 1

# 防衛・宇宙は逃避先になりやすい一方で、短期過熱後の反落を食らいやすい。
DEFENSE_OVERHEAT_AVG_PCT = 3.5
DEFENSE_OVERHEAT_DAILY_PCT = 5.0
DEFENSE_OVERHEAT_POSITIVE_RATIO = 0.90

# v5: 週明け高値追い禁止・短期過熱回避・売られすぎ反発の小額買い。
# 狙いは「Kioxia/SanDiskの高値掴みを避ける」と「SanDiskのような急反発を完全には逃さない」の両立。
JP_WEEK_OPEN_BUY_BLOCK_MINUTES = 90
US_WEEK_OPEN_BUY_BLOCK_MINUTES = 90

OVERHEAT_5D_PCT = 15.0
OVERHEAT_10D_PCT = 22.0
OVERHEAT_20D_PCT = 30.0
NEAR_20D_HIGH_RATIO = 0.98
MEMORY_OVERHEAT_5D_PCT = 12.0
MEMORY_OVERHEAT_20D_PCT = 25.0
MEMORY_NEAR_20D_HIGH_RATIO = 0.97

OVERSOLD_5D_PCT = -8.0
OVERSOLD_10D_PCT = -12.0
OVERSOLD_20D_PCT = -18.0
REBOUND_DAILY_MIN_PCT = 5.0
REBOUND_DAILY_MAX_PCT = 15.0
REBOUND_15M_MIN_PCT = -0.5
REBOUND_15M_MAX_PCT = 4.0
REBOUND_MIN_CASH_RATIO = 0.70
REBOUND_ALLOCATION_RATIO = 0.03
REBOUND_MIN_CASH_AFTER_BUY_RATIO = 0.65
REBOUND_MAX_SINGLE_POSITION_WEIGHT = 0.22
MAX_OVERSOLD_REBOUND_BUYS_PER_SLOT = 1
MAX_R_GRADE_REBOUND_POSITIONS = 1
REBOUND_STOP_LOSS_PCT = -5.0
REBOUND_TAKE_PROFIT_PCT = 10.0
REBOUND_TRAILING_START_PCT = 15.0
REBOUND_TRAILING_DRAWDOWN_PCT = -6.0

# v6: 実運用寄りの売買品質と資金効率を改善する。
# 1) 同一銘柄クールダウン 2) 全買いルートへのセクタークールダウン強制
# 3) 1日あたりの買付回数制限 4) 取引摩擦（スプレッド/約定ズレ/為替コスト）の反映
# 5) リスクレジーム別の現金比率・保有数・投入量 6) セクター/格付け別の保有上限
TICKER_COOLDOWN_HOURS = {
    "paper_sell_alert": 72,
    "paper_stop_loss": 48,
    "paper_rebound_stop_loss": 72,
    "paper_break_even_stop": 48,
    "paper_trailing_stop": 24,
    "paper_rebound_trailing_stop": 24,
    "paper_take_profit": 12,
    "paper_rebound_take_profit": 12,
}
SECTOR_COOLDOWN_SA_EXCEPTION_WAIT_HOURS = 12
MAX_TOTAL_BUYS_PER_DAY = 3
MAX_SAME_BUCKET_BUYS_PER_DAY = 2
MAX_REBOUND_BUYS_PER_DAY = 1

# ペーパートレードで不利な約定価格を使い、実運用の摩擦を保守的に近似する。
# 米国株は為替コストも含めた片道の概算値。
HIGH_VOL_TICKERS = {"SNDK", "SMCI", "285A.T", "6857.T", "6146.T"}
MAX_EXECUTION_FRICTION_PCT = 0.45

RISK_REGIME_MIN_CASH = {
    "risk_off": 0.75,
    "cautious": 0.60,
    "neutral": 0.45,
    "risk_on": 0.30,
    "strong_risk_on": 0.20,
}
RISK_REGIME_MAX_POSITIONS = {
    "risk_off": 3,
    "cautious": 4,
    "neutral": 5,
    "risk_on": 5,
    "strong_risk_on": 5,
}
RISK_REGIME_ALLOCATION_MULTIPLIER = {
    "risk_off": 0.50,
    "cautious": 0.70,
    "neutral": 0.90,
    "risk_on": 1.00,
    "strong_risk_on": 1.15,
}

BUCKET_MAX_WEIGHTS = {
    "メモリ・ストレージ": 0.18,
    "半導体・AIインフラ": 0.35,
    "防衛・宇宙": 0.25,
    "データセンター周辺": 0.25,
    "AIクラウド": 0.25,
    "サイバーセキュリティ": 0.15,
}
GRADE_MAX_POSITION_WEIGHTS = {"S": 0.15, "A": 0.15, "B": 0.12, "R": 0.08}

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


def fetch_daily_metrics(ticker: str):
    """日足から通常の前日比に加え、短期過熱・売られすぎ判定用の指標を返す。"""
    hist = yf.Ticker(ticker).history(period="3mo", interval="1d", auto_adjust=False)
    metrics = {
        "last": None,
        "pct_change": None,
        "change_5d": None,
        "change_10d": None,
        "change_20d": None,
        "high_20d": None,
        "high_20d_ratio": None,
        "distance_from_20d_high_pct": None,
    }

    if hist is None or hist.empty or "Close" not in hist.columns:
        return metrics

    closes = []
    for raw in hist["Close"].dropna().tolist():
        value = safe_float(raw)
        if value is not None and value > 0:
            closes.append(value)

    if not closes:
        return metrics

    last = closes[-1]
    metrics["last"] = last

    def change_from_n_days(n):
        if len(closes) <= n:
            return None
        base = closes[-1 - n]
        if base <= 0:
            return None
        return ((last / base) - 1.0) * 100.0

    metrics["pct_change"] = change_from_n_days(1)
    metrics["change_5d"] = change_from_n_days(5)
    metrics["change_10d"] = change_from_n_days(10)
    metrics["change_20d"] = change_from_n_days(20)

    window_20 = closes[-20:] if len(closes) >= 20 else closes
    if window_20:
        high_20d = max(window_20)
        metrics["high_20d"] = high_20d
        if high_20d > 0:
            metrics["high_20d_ratio"] = last / high_20d
            metrics["distance_from_20d_high_pct"] = ((last / high_20d) - 1.0) * 100.0

    return metrics



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
        daily_metrics = {}
        daily_last = None
        daily_change = None
        intraday_last = None
        change_15m = None
        error = None

        try:
            daily_metrics = fetch_daily_metrics(ticker)
            daily_last = daily_metrics.get("last")
            daily_change = daily_metrics.get("pct_change")
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
                "change_5d": daily_metrics.get("change_5d"),
                "change_10d": daily_metrics.get("change_10d"),
                "change_20d": daily_metrics.get("change_20d"),
                "high_20d": daily_metrics.get("high_20d"),
                "high_20d_ratio": daily_metrics.get("high_20d_ratio"),
                "distance_from_20d_high_pct": daily_metrics.get("distance_from_20d_high_pct"),
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
        "ticker_cooldowns": {},
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
    state.setdefault("ticker_cooldowns", {})

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
        pos.setdefault("partial_taken_rebound", False)
        pos.setdefault("buy_mode", pos.get("buy_mode", "legacy"))
        pos.setdefault("strategy_version", STRATEGY_VERSION)

    rebuild_ticker_cooldowns_from_history(state)
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
        new_pos.setdefault("partial_taken_rebound", False)
        new_pos.setdefault("buy_mode", pos.get("buy_mode", "legacy"))
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


def record_realized_trade(
    state,
    ticker,
    name,
    qty,
    sell_market_price_jpy,
    buy_price_jpy,
    reason,
    current,
    action,
    row=None,
):
    friction_pct = estimate_execution_friction_pct(
        ticker=ticker,
        currency=(row or {}).get("currency"),
        grade=(row or {}).get("grade") or TICKER_GRADES.get(ticker, "B"),
    )
    sell_price_jpy = apply_execution_friction(sell_market_price_jpy, "sell", friction_pct)
    proceeds = int(qty * sell_price_jpy)
    reference_proceeds = int(qty * sell_market_price_jpy)
    cost = int(qty * buy_price_jpy) if buy_price_jpy else proceeds
    pnl = proceeds - cost
    execution_cost_jpy = max(0, reference_proceeds - proceeds)

    state["realized_pnl_jpy"] = int(state.get("realized_pnl_jpy", 0)) + pnl
    trades = state.setdefault("realized_trades", [])
    trades.append(
        {
            "ticker": ticker,
            "name": name,
            "qty": qty,
            "sell_market_price_jpy": sell_market_price_jpy,
            "sell_price_jpy": sell_price_jpy,
            "buy_price_jpy": buy_price_jpy,
            "proceeds_jpy": proceeds,
            "cost_jpy": cost,
            "realized_pnl_jpy": pnl,
            "execution_friction_pct": friction_pct,
            "execution_cost_jpy": execution_cost_jpy,
            "action": action,
            "reason": reason,
            "sold_at": current.isoformat(),
        }
    )
    state["realized_trades"] = trades[-200:]

    return proceeds, cost, pnl, sell_price_jpy, execution_cost_jpy

def decide_sell_action(pos, row):
    ticker = pos["ticker"]
    daily_change = row.get("pct_change")
    change_15m = row.get("change_15m")
    pnl_pct = safe_float(pos.get("pnl_pct")) or 0.0
    peak_pnl_pct = safe_float(pos.get("peak_pnl_pct")) or pnl_pct
    drawdown = safe_float(pos.get("drawdown_from_peak_pct")) or 0.0
    current_price = safe_float(pos.get("current_price_jpy"))
    break_even_stop = safe_float(pos.get("break_even_stop_jpy"))
    is_rebound_trade = pos.get("buy_mode") == "oversold_rebound" or bool(pos.get("rebound_trade", False))

    if is_rebound_trade and pnl_pct <= REBOUND_STOP_LOSS_PCT:
        return {
            "type": "sell_all",
            "action": "paper_rebound_stop_loss",
            "reason": f"反発狙いの撤退: 損切りライン到達 {ticker} {pct(pnl_pct)}",
        }

    if is_rebound_trade and peak_pnl_pct >= REBOUND_TRAILING_START_PCT and drawdown <= REBOUND_TRAILING_DRAWDOWN_PCT:
        return {
            "type": "sell_all",
            "action": "paper_rebound_trailing_stop",
            "reason": f"反発狙いの利益保護: ピーク利益 {pct(peak_pnl_pct)} から {pct(drawdown)} 下落",
        }

    if (
        is_rebound_trade
        and pnl_pct >= REBOUND_TAKE_PROFIT_PCT
        and int(pos.get("qty", 0)) >= 2
        and not bool(pos.get("partial_taken_rebound", False))
    ):
        return {
            "type": "sell_partial",
            "action": "paper_rebound_take_profit",
            "partial_flag": "partial_taken_rebound",
            "reason": f"反発狙いの一部利確: 含み益が {pct(REBOUND_TAKE_PROFIT_PCT)} 以上",
        }

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
            "partial_flag": "partial_taken_20",
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


def get_previous_sector_summary(state):
    """直近レポートのセクター状態を取り出す。なければ空 dict。"""
    latest = state.get("latest") or {}
    summary = latest.get("sector_summary")
    if isinstance(summary, dict) and summary:
        return summary

    reports = state.get("reports", [])
    for report in reversed(reports):
        summary = report.get("sector_summary")
        if isinstance(summary, dict) and summary:
            return summary
    return {}


def get_previous_sector_status(state, sector):
    previous = get_previous_sector_summary(state)
    info = previous.get(sector, {}) if isinstance(previous, dict) else {}
    status = info.get("status")
    if status in {"crash", "weak", "neutral", "strong"}:
        return status
    return None


def sector_recovered_from_weakness(state, sector, current_status):
    previous_status = get_previous_sector_status(state, sector)
    if previous_status in {"crash", "weak"} and current_status in {"neutral", "strong"}:
        return True
    return False


def is_sector_overheated(row, sector_info):
    """短期の逃避先過熱を検知。現状では防衛・宇宙だけを強く制限する。"""
    sector = sector_info.get("sector") or row.get("sector") or broad_sector(row.get("theme", ""))
    daily = safe_float(row.get("pct_change"))
    avg_daily = safe_float(sector_info.get("avg_daily_pct")) or 0.0
    positive_ratio = safe_float(sector_info.get("positive_ratio")) or 0.0

    if sector != "防衛・宇宙":
        return False

    if daily is not None and daily >= DEFENSE_OVERHEAT_DAILY_PCT:
        return True
    if avg_daily >= DEFENSE_OVERHEAT_AVG_PCT and positive_ratio >= DEFENSE_OVERHEAT_POSITIVE_RATIO:
        return True
    return False


def is_memory_storage_row(row):
    ticker = row.get("ticker")
    theme = row.get("theme", "")
    return ticker in {"SNDK", "285A.T", "MU", "WDC", "STX"} or theme in {"メモリ・ストレージ", "メモリ", "ストレージ"}


def is_week_open_risk(row, current):
    """週初の寄り付き直後を高値追い禁止時間として扱う。

    JPY銘柄: 月曜 9:00-10:30 JST
    USD銘柄: 米国月曜寄り後をJST月曜 22:30-24:00前後として近似
    """
    currency = row.get("currency")
    if currency == "JPY":
        if current.weekday() != 0:
            return False
        minutes = current.hour * 60 + current.minute
        return 9 * 60 <= minutes < 9 * 60 + JP_WEEK_OPEN_BUY_BLOCK_MINUTES

    if currency == "USD":
        # 米国夏時間の月曜寄り付き 9:30 ET = 月曜22:30 JSTを基準にする。
        # 冬時間では23:30 JST寄り付きなので、22:30-翌0:30を広めにブロックする。
        if current.weekday() == 0:
            minutes = current.hour * 60 + current.minute
            return 22 * 60 + 30 <= minutes < 24 * 60
        if current.weekday() == 1:
            minutes = current.hour * 60 + current.minute
            return 0 <= minutes < 30
    return False


def is_week_open_first_hour(row, current):
    currency = row.get("currency")
    if currency == "JPY":
        if current.weekday() != 0:
            return False
        minutes = current.hour * 60 + current.minute
        return 9 * 60 <= minutes < 10 * 60

    if currency == "USD":
        if current.weekday() == 0:
            minutes = current.hour * 60 + current.minute
            return 22 * 60 + 30 <= minutes < 23 * 60 + 30
        if current.weekday() == 1:
            minutes = current.hour * 60 + current.minute
            return 0 <= minutes < 30
    return False


def is_short_term_overheated(row):
    """高値掴みになりやすい短期過熱を検出する。"""
    c5 = safe_float(row.get("change_5d"))
    c10 = safe_float(row.get("change_10d"))
    c20 = safe_float(row.get("change_20d"))
    high_ratio = safe_float(row.get("high_20d_ratio"))
    daily = safe_float(row.get("pct_change"))
    is_memory = is_memory_storage_row(row)

    reasons = []
    if is_memory:
        if c5 is not None and c5 >= MEMORY_OVERHEAT_5D_PCT:
            reasons.append(f"メモリ系5日上昇率が高い: {pct(c5)}")
        if c20 is not None and c20 >= MEMORY_OVERHEAT_20D_PCT:
            reasons.append(f"メモリ系20日上昇率が高い: {pct(c20)}")
        if high_ratio is not None and high_ratio >= MEMORY_NEAR_20D_HIGH_RATIO and daily is not None and daily > 0:
            reasons.append(f"メモリ系20日高値圏: 高値比{pct((high_ratio - 1.0) * 100)}")
    else:
        if c5 is not None and c5 >= OVERHEAT_5D_PCT:
            reasons.append(f"5日上昇率が高い: {pct(c5)}")
        if c10 is not None and c10 >= OVERHEAT_10D_PCT:
            reasons.append(f"10日上昇率が高い: {pct(c10)}")
        if c20 is not None and c20 >= OVERHEAT_20D_PCT:
            reasons.append(f"20日上昇率が高い: {pct(c20)}")
        if high_ratio is not None and high_ratio >= NEAR_20D_HIGH_RATIO and daily is not None and daily > 0:
            reasons.append(f"20日高値圏: 高値比{pct((high_ratio - 1.0) * 100)}")

    return bool(reasons), "; ".join(reasons[:3])


def has_oversold_history(row):
    c5 = safe_float(row.get("change_5d"))
    c10 = safe_float(row.get("change_10d"))
    c20 = safe_float(row.get("change_20d"))
    return (c5 is not None and c5 <= OVERSOLD_5D_PCT) or (c10 is not None and c10 <= OVERSOLD_10D_PCT) or (c20 is not None and c20 <= OVERSOLD_20D_PCT)


def count_r_grade_rebound_positions(positions):
    count = 0
    for pos in positions:
        if pos.get("buy_mode") == "oversold_rebound" and (pos.get("grade") == "R" or TICKER_GRADES.get(pos.get("ticker"), "B") == "R"):
            count += 1
    return count


def portfolio_cash_ratio(portfolio):
    cash = int(portfolio.get("cash", 0))
    total_value = int(portfolio.get("total_value", STARTING_CAPITAL))
    if total_value <= 0:
        return 0.0
    return cash / total_value


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


def estimate_execution_friction_pct(ticker, currency=None, grade=None):
    """片道のスプレッド・約定ズレ・米国株の為替摩擦を簡易的にまとめた保守的な概算。"""
    grade = grade or TICKER_GRADES.get(ticker, "B")
    is_usd = currency == "USD" or (currency is None and not str(ticker).endswith(".T"))
    friction = 0.20 if is_usd else 0.10
    if grade == "B":
        friction += 0.05
    elif grade == "R":
        friction += 0.15
    if ticker in HIGH_VOL_TICKERS:
        friction += 0.10
    return min(MAX_EXECUTION_FRICTION_PCT, friction)


def apply_execution_friction(market_price_jpy, side, friction_pct):
    price_value = safe_float(market_price_jpy)
    if price_value is None:
        return None
    rate = friction_pct / 100.0
    return price_value * (1.0 + rate if side == "buy" else 1.0 - rate)


def infer_sell_action_from_reason(reason):
    reason = str(reason or "")
    if "15分変化率" in reason or "日次下落" in reason:
        return "paper_sell_alert"
    if "反発狙いの撤退" in reason:
        return "paper_rebound_stop_loss"
    if "損切りライン" in reason:
        return "paper_stop_loss"
    if "建値保護" in reason:
        return "paper_break_even_stop"
    if "反発狙いの利益保護" in reason:
        return "paper_rebound_trailing_stop"
    if "利益保護" in reason:
        return "paper_trailing_stop"
    if "反発狙いの一部利確" in reason:
        return "paper_rebound_take_profit"
    if "一部利確" in reason:
        return "paper_take_profit"
    return None


def set_ticker_cooldown(state, ticker, current, action, sell_price_jpy=None):
    hours = TICKER_COOLDOWN_HOURS.get(action)
    if not hours:
        return
    cooldowns = state.setdefault("ticker_cooldowns", {})
    until = current + timedelta(hours=hours)
    existing = cooldowns.get(ticker, {})
    existing_until = parse_dt(existing.get("until")) if isinstance(existing, dict) else parse_dt(existing)
    if existing_until is None or until > existing_until:
        cooldowns[ticker] = {
            "until": until.isoformat(),
            "action": action,
            "sell_price_jpy": sell_price_jpy,
            "set_at": current.isoformat(),
        }


def ticker_cooldown_remaining_hours(state, ticker, current):
    cooldowns = state.setdefault("ticker_cooldowns", {})
    item = cooldowns.get(ticker)
    if not item:
        return 0.0
    until = parse_dt(item.get("until")) if isinstance(item, dict) else parse_dt(item)
    if until is None or until <= current:
        cooldowns.pop(ticker, None)
        return 0.0
    return (until - current).total_seconds() / 3600.0


def rebuild_ticker_cooldowns_from_history(state, current=None):
    current = current or now_jst()
    cooldowns = state.setdefault("ticker_cooldowns", {})
    for trade in state.get("realized_trades", []):
        ticker = trade.get("ticker")
        sold_at = parse_dt(trade.get("sold_at"))
        if not ticker or sold_at is None:
            continue
        action = trade.get("action") or infer_sell_action_from_reason(trade.get("reason"))
        hours = TICKER_COOLDOWN_HOURS.get(action)
        if not hours:
            continue
        until = sold_at + timedelta(hours=hours)
        if until <= current:
            continue
        existing = cooldowns.get(ticker, {})
        existing_until = parse_dt(existing.get("until")) if isinstance(existing, dict) else parse_dt(existing)
        if existing_until is None or until > existing_until:
            cooldowns[ticker] = {
                "until": until.isoformat(),
                "action": action,
                "sell_price_jpy": trade.get("sell_price_jpy"),
                "set_at": sold_at.isoformat(),
            }


def exposure_bucket(theme):
    if theme in {"メモリ・ストレージ", "ストレージ"}:
        return "メモリ・ストレージ"
    return broad_sector(theme)


def bucket_exposure_value(positions, bucket):
    return sum(
        int(pos.get("market_value_jpy", 0))
        for pos in positions
        if exposure_bucket(pos.get("theme", "")) == bucket
    )


def get_daily_buy_stats(state, current):
    today = current.strftime("%Y-%m-%d")
    total = 0
    rebound = 0
    by_bucket = Counter()
    for report in state.get("reports", []):
        if report.get("date") != today:
            continue
        for decision in report.get("decisions", []):
            if decision.get("action") != "paper_buy":
                continue
            total += 1
            mode = decision.get("buy_mode")
            if mode in {"oversold_rebound", "rebound_probe"}:
                rebound += 1
            ticker = decision.get("ticker")
            item = next((x for x in WATCHLIST if x.get("ticker") == ticker), None)
            if item:
                by_bucket[exposure_bucket(item.get("theme", ""))] += 1
    return {"total": total, "rebound": rebound, "by_bucket": by_bucket}


def determine_risk_regime(market_data, sector_stats):
    changes = [safe_float(row.get("pct_change")) for row in market_data]
    changes = [x for x in changes if x is not None]
    avg_change = sum(changes) / len(changes) if changes else 0.0
    positive_ratio = sum(1 for x in changes if x > 0) / len(changes) if changes else 0.0
    sharp_drop_count = sum(1 for x in changes if x <= ALERT_DAY_DROP_PCT)
    statuses = [info.get("status") for info in sector_stats.values()]
    crash_count = statuses.count("crash")
    weak_count = statuses.count("weak")

    if sharp_drop_count >= 4 or crash_count >= 2 or avg_change <= -3.0:
        label = "risk_off"
    elif sharp_drop_count >= 2 or crash_count >= 1 or weak_count >= 2 or avg_change <= -1.0:
        label = "cautious"
    elif positive_ratio >= 0.72 and avg_change >= 1.5 and crash_count == 0 and weak_count == 0:
        label = "strong_risk_on"
    elif positive_ratio >= 0.58 and avg_change >= 0.5 and crash_count == 0:
        label = "risk_on"
    else:
        label = "neutral"

    return {
        "label": label,
        "avg_change_pct": avg_change,
        "positive_ratio": positive_ratio,
        "sharp_drop_count": sharp_drop_count,
        "crash_sector_count": crash_count,
        "weak_sector_count": weak_count,
        "min_cash_ratio": RISK_REGIME_MIN_CASH[label],
        "max_positions": RISK_REGIME_MAX_POSITIONS[label],
        "allocation_multiplier": RISK_REGIME_ALLOCATION_MULTIPLIER[label],
    }


def effective_min_cash_ratio(mode, regime_label):
    regime_floor = RISK_REGIME_MIN_CASH.get(regime_label, 0.45)
    mode_floor = {
        "normal_momentum": 0.20,
        "high_cash_deploy": 0.55,
        "reentry_recovery": 0.55,
        "rebound_probe": 0.60,
        "oversold_rebound": 0.65,
    }.get(mode, MIN_CASH_RATIO)
    return max(regime_floor, mode_floor)


def candidate_score_v6(row, sector_stats=None):
    base = candidate_score(row, sector_stats)
    if base <= -9000:
        return base
    change_5d = safe_float(row.get("change_5d")) or 0.0
    change_10d = safe_float(row.get("change_10d")) or 0.0
    distance_high = safe_float(row.get("distance_from_20d_high_pct"))
    base += max(-10.0, min(10.0, change_5d)) * 0.15
    base += max(-15.0, min(15.0, change_10d)) * 0.08
    if distance_high is not None and -12.0 <= distance_high <= -3.0:
        base += 1.5
    overheated, _ = is_short_term_overheated(row)
    if overheated:
        base -= 6.0
    if has_oversold_history(row) and (safe_float(row.get("pct_change")) or 0) > 0:
        base += 2.0
    return base


def classify_buy_candidate(row, sector_stats, state, current, portfolio, held_sectors, risk_regime=None):
    """v5の判定を利用しつつ、v6のグローバルな安全弁を全買いルートへ強制する。"""
    ticker = row.get("ticker")
    grade = row.get("grade") or TICKER_GRADES.get(ticker, "B")
    sector = (get_sector_status(row, sector_stats) or {}).get("sector") or broad_sector(row.get("theme", ""))
    sector_status = (get_sector_status(row, sector_stats) or {}).get("status") or "neutral"
    ticker_cd = ticker_cooldown_remaining_hours(state, ticker, current)
    if ticker_cd > 0:
        return {"ok": False, "reason": f"同一銘柄クールダウン中: 残り{ticker_cd:.1f}時間"}

    sector_cd = cooldown_remaining_hours(state, sector, current)
    if sector_cd > 0:
        elapsed = max(0.0, BUY_COOLDOWN_HOURS - sector_cd)
        if grade not in {"S", "A"}:
            return {"ok": False, "reason": f"セクター冷却中はB/R格付けを全面禁止: 残り{sector_cd:.1f}時間"}
        if elapsed < SECTOR_COOLDOWN_SA_EXCEPTION_WAIT_HOURS:
            return {"ok": False, "reason": f"セクター冷却開始から12時間未満: 残り{sector_cd:.1f}時間"}
        if sector_status == "crash":
            return {"ok": False, "reason": "セクター冷却中かつcrash継続のため買い禁止"}

    decision = classify_buy_candidate_v5(row, sector_stats, state, current, portfolio, held_sectors)
    if not decision.get("ok"):
        return decision

    mode = decision.get("mode")
    # セクター冷却中の例外はS/Aの打診・売られすぎ反発だけ。通常/再エントリー/高現金買いは全面禁止。
    if sector_cd > 0 and mode not in {"rebound_probe", "oversold_rebound"}:
        return {"ok": False, "reason": f"セクター冷却中は{mode}を禁止: 残り{sector_cd:.1f}時間"}

    regime = (risk_regime or {}).get("label", "neutral")
    if regime == "risk_off":
        if mode not in {"rebound_probe", "oversold_rebound"} or grade not in {"S", "A"}:
            return {"ok": False, "reason": "Risk-off中はS/Aの小額打診・反発買い以外を禁止"}
    if regime == "cautious" and mode == "high_cash_deploy":
        return {"ok": False, "reason": "Cautious中は高現金モードの機械的な買い増しを停止"}

    multiplier = RISK_REGIME_ALLOCATION_MULTIPLIER.get(regime, 0.90)
    if sector_cd > 0:
        multiplier *= 0.50
    decision["allocation_ratio"] = decision.get("allocation_ratio", BUY_ALLOCATION_RATIO) * multiplier
    decision["min_cash_ratio"] = effective_min_cash_ratio(mode, regime)
    decision["risk_regime"] = regime
    decision["candidate_score"] = candidate_score_v6(row, sector_stats)
    decision["reason"] = f"{decision.get('reason', '')} / v6 regime={regime}"
    return decision


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


def classify_buy_candidate_v5(row, sector_stats, state, current, portfolio, held_sectors):
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
    cash_ratio = portfolio_cash_ratio(portfolio)
    recovered = sector_recovered_from_weakness(state, sector, sector_status)
    overheated = is_sector_overheated(row, sector_info)
    short_overheated, short_overheat_reason = is_short_term_overheated(row)
    week_open_risk = is_week_open_risk(row, current)
    week_open_first_hour = is_week_open_first_hour(row, current)

    if last_jpy is None or last_jpy <= 0:
        return {"ok": False, "reason": "価格データなし"}
    if daily is None:
        return {"ok": False, "reason": "日次変化率なし"}

    # 1) v5: 売られすぎ反発の小額買い。
    # SanDiskのようなR格付け・高ボラ銘柄でも、暴落後の反発初動だけ小さく拾う。
    rebound_allowed = True
    rebound_reason = []

    if grade not in {"S", "A", "B", "R"}:
        rebound_allowed = False
        rebound_reason.append(f"反発買い対象外格付け: {grade}")
    if not has_oversold_history(row):
        rebound_allowed = False
        rebound_reason.append("直近で十分に売られていない")
    if daily < REBOUND_DAILY_MIN_PCT or daily > REBOUND_DAILY_MAX_PCT:
        rebound_allowed = False
        rebound_reason.append(f"反発買いの日次範囲外: {pct(daily)}")
    if intraday is not None and intraday < REBOUND_15M_MIN_PCT:
        rebound_allowed = False
        rebound_reason.append(f"短期下落が止まっていない: 15分{pct(intraday)}")
    if intraday is not None and intraday > REBOUND_15M_MAX_PCT:
        rebound_allowed = False
        rebound_reason.append(f"短期急騰しすぎ: 15分{pct(intraday)}")
    if sector_status == "crash":
        rebound_allowed = False
        rebound_reason.append("セクターcrash中は反発買いしない")
    if cash_ratio < REBOUND_MIN_CASH_RATIO:
        rebound_allowed = False
        rebound_reason.append(f"反発買いには現金不足: 現金比率{pct(cash_ratio * 100)}")
    if week_open_first_hour:
        rebound_allowed = False
        rebound_reason.append("週明け寄り付き直後は反発買いも禁止")
    if cooldown_hours > BUY_COOLDOWN_HOURS - PROBE_COOLDOWN_HOURS and grade == "R":
        rebound_allowed = False
        rebound_reason.append(f"R格付けは損切り直後の冷却中に買わない: 残り{cooldown_hours:.1f}時間")

    if rebound_allowed:
        return {
            "ok": True,
            "mode": "oversold_rebound",
            "allocation_ratio": REBOUND_ALLOCATION_RATIO,
            "min_cash_ratio": REBOUND_MIN_CASH_AFTER_BUY_RATIO,
            "reason": f"v5売られすぎ反発買い: {grade}格付け / 日次{pct(daily)} / 5日{pct(row.get('change_5d'))} / 10日{pct(row.get('change_10d'))} / セクター{sector_status}",
        }

    # 2) v4: 反発初動の再エントリー
    # ポートフォリオDDが深く、現金が厚く、セクターがweak/crashからneutral/strongへ回復した場合だけ小口で戻る。
    reentry_allowed = True
    reentry_reason = []

    if grade not in {"S", "A"}:
        reentry_allowed = False
        reentry_reason.append(f"再エントリー対象外格付け: {grade}")
    if portfolio_dd > REENTRY_DD_TRIGGER_PCT:
        reentry_allowed = False
        reentry_reason.append(f"再エントリーを使うほどDDが深くない: {pct(portfolio_dd)}")
    if cash_ratio < REENTRY_MIN_CASH_RATIO:
        reentry_allowed = False
        reentry_reason.append(f"再エントリーには現金不足: 現金比率{pct(cash_ratio * 100)}")
    if not (recovered or sector_status == "strong"):
        reentry_allowed = False
        reentry_reason.append(f"セクター回復確認なし: {sector_status}")
    if sector_status == "crash":
        reentry_allowed = False
        reentry_reason.append("セクターcrash中は再エントリーしない")
    if daily < REENTRY_DAILY_MIN_PCT or daily > REENTRY_DAILY_MAX_PCT:
        reentry_allowed = False
        reentry_reason.append(f"再エントリー日次範囲外: {pct(daily)}")
    if intraday is not None and intraday < REENTRY_15M_MIN_PCT:
        reentry_allowed = False
        reentry_reason.append(f"短期下落中: 15分{pct(intraday)}")
    if intraday is not None and intraday > REENTRY_15M_MAX_PCT:
        reentry_allowed = False
        reentry_reason.append(f"短期急騰しすぎ: 15分{pct(intraday)}")
    if cooldown_hours > BUY_COOLDOWN_HOURS - REENTRY_MIN_WAIT_HOURS_AFTER_COOLDOWN:
        reentry_allowed = False
        reentry_reason.append(f"損切り直後の冷却中: 残り{cooldown_hours:.1f}時間")
    if week_open_risk:
        reentry_allowed = False
        reentry_reason.append("週明け高値追い禁止時間")
    if short_overheated:
        reentry_allowed = False
        reentry_reason.append(f"短期過熱: {short_overheat_reason}")
    if overheated:
        reentry_allowed = False
        reentry_reason.append("逃避先の短期過熱を検知")

    if reentry_allowed:
        return {
            "ok": True,
            "mode": "reentry_recovery",
            "allocation_ratio": REENTRY_ALLOCATION_RATIO,
            "min_cash_ratio": REENTRY_MIN_CASH_AFTER_BUY_RATIO,
            "reason": f"v4再エントリー: {grade}格付け / DD{pct(portfolio_dd)} / 現金比率{pct(cash_ratio * 100)} / 日次{pct(daily)} / セクター{sector_status}",
        }

    # 2) 通常買い: セクターが崩れていないことを必須にする。
    normal_allowed = True
    normal_reason = []

    if grade == "R":
        normal_allowed = False
        normal_reason.append("R格付けは通常買い禁止")
    if week_open_risk:
        normal_allowed = False
        normal_reason.append("週明け高値追い禁止時間")
    if short_overheated:
        normal_allowed = False
        normal_reason.append(f"短期過熱: {short_overheat_reason}")
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
    if overheated:
        normal_allowed = False
        normal_reason.append("防衛・宇宙の短期過熱を検知")

    if normal_allowed:
        return {
            "ok": True,
            "mode": "normal_momentum",
            "allocation_ratio": BUY_ALLOCATION_RATIO,
            "min_cash_ratio": MIN_CASH_RATIO,
            "reason": f"通常買い: {grade}格付け / 日次{pct(daily)} / 15分{pct(intraday)} / セクター{sector_status}",
        }

    # 3) 打診買い: セクター暴落時に、底値を完全に逃さないための小額枠。
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
    if week_open_first_hour:
        probe_allowed = False
        probe_reason.append("週明け寄り付き直後は打診買いしない")
    if overheated:
        probe_allowed = False
        probe_reason.append("短期過熱セクターは打診買いしない")

    if probe_allowed:
        return {
            "ok": True,
            "mode": "rebound_probe",
            "allocation_ratio": PROBE_ALLOCATION_RATIO,
            "min_cash_ratio": PROBE_MIN_CASH_RATIO,
            "reason": f"暴落後の打診買い: {grade}格付け / 日次{pct(daily)} / 15分{pct(intraday)} / セクター平均{pct(sector_avg)}",
        }

    # 4) v4: 高現金時の小口分散買い。
    # 大半が現金で、地合いが崩れていないときに限り、S/A銘柄へ小さく戻す。
    high_cash_allowed = True
    high_cash_reason = []

    if cash_ratio < HIGH_CASH_DEPLOY_TRIGGER_RATIO:
        high_cash_allowed = False
        high_cash_reason.append(f"現金比率が高現金モード未満: {pct(cash_ratio * 100)}")
    if week_open_risk:
        high_cash_allowed = False
        high_cash_reason.append("週明け高値追い禁止時間")
    if short_overheated:
        high_cash_allowed = False
        high_cash_reason.append(f"短期過熱: {short_overheat_reason}")
    if grade not in {"S", "A"}:
        high_cash_allowed = False
        high_cash_reason.append(f"高現金時の分散買い対象外格付け: {grade}")
    if sector_status not in {"neutral", "strong"}:
        high_cash_allowed = False
        high_cash_reason.append(f"セクター地合いが弱い: {sector_status}")
    if daily < HIGH_CASH_DAILY_MIN_PCT or daily > HIGH_CASH_DAILY_MAX_PCT:
        high_cash_allowed = False
        high_cash_reason.append(f"高現金買いの日次範囲外: {pct(daily)}")
    if intraday is not None and intraday < HIGH_CASH_15M_MIN_PCT:
        high_cash_allowed = False
        high_cash_reason.append(f"短期下落中: 15分{pct(intraday)}")
    if intraday is not None and intraday > HIGH_CASH_15M_MAX_PCT:
        high_cash_allowed = False
        high_cash_reason.append(f"短期急騰しすぎ: 15分{pct(intraday)}")
    if cooldown_hours > 0:
        high_cash_allowed = False
        high_cash_reason.append(f"セクター冷却中: 残り{cooldown_hours:.1f}時間")
    if overheated:
        high_cash_allowed = False
        high_cash_reason.append("逃避先の短期過熱を検知")

    if high_cash_allowed:
        return {
            "ok": True,
            "mode": "high_cash_deploy",
            "allocation_ratio": HIGH_CASH_DEPLOY_ALLOCATION_RATIO,
            "min_cash_ratio": HIGH_CASH_MIN_AFTER_BUY_RATIO,
            "reason": f"v4高現金小口分散買い: {grade}格付け / 現金比率{pct(cash_ratio * 100)} / 日次{pct(daily)} / セクター{sector_status}",
        }

    return {
        "ok": False,
        "reason": "通常買い不可: " + "; ".join(normal_reason[:3])
        + " / 再エントリー不可: " + "; ".join(reentry_reason[:3])
        + " / 打診買い不可: " + "; ".join(probe_reason[:2])
        + " / 高現金買い不可: " + "; ".join(high_cash_reason[:2])
        + " / 反発買い不可: " + "; ".join(rebound_reason[:2]),
    }

def update_paper_portfolio(state, market_data, current):
    market_map = {row["ticker"]: row for row in market_data}
    cash = int(state.get("cash", STARTING_CAPITAL))
    positions = refresh_positions(state.get("positions", []), market_map)
    decisions = []
    sold_tickers = set()

    # 売却フェーズ。売った銘柄は同一実行内で絶対に買い戻さない。
    kept_positions = []
    for pos in positions:
        ticker = pos["ticker"]
        row = market_map.get(ticker, {})
        current_price = safe_float(pos.get("current_price_jpy"))
        buy_price = safe_float(pos.get("buy_price_jpy"))
        qty = int(pos.get("qty", 0))
        action = decide_sell_action(pos, row)

        if action is None or current_price is None or buy_price is None or qty <= 0:
            kept_positions.append(pos)
            continue

        sell_qty = qty if action["type"] == "sell_all" else max(1, qty // 2)
        proceeds, _, realized_pnl, execution_sell_price, execution_cost_jpy = record_realized_trade(
            state=state,
            ticker=ticker,
            name=pos.get("name", ticker),
            qty=sell_qty,
            sell_market_price_jpy=current_price,
            buy_price_jpy=buy_price,
            reason=action["reason"],
            current=current,
            action=action["action"],
            row=row,
        )
        cash += proceeds

        decisions.append(
            {
                "action": action["action"],
                "ticker": ticker,
                "qty": sell_qty,
                "amount_jpy": proceeds,
                "realized_pnl_jpy": realized_pnl,
                "execution_sell_price_jpy": execution_sell_price,
                "execution_cost_jpy": execution_cost_jpy,
                "reason": action["reason"],
            }
        )

        if action["type"] == "sell_all":
            sold_tickers.add(ticker)
            set_ticker_cooldown(state, ticker, current, action["action"], execution_sell_price)

        if action["action"] in {"paper_sell_alert", "paper_stop_loss", "paper_rebound_stop_loss"}:
            set_sector_cooldown(state, broad_sector(pos.get("theme", "")), current)

        remaining_qty = qty - sell_qty
        if remaining_qty > 0:
            new_pos = dict(pos)
            new_pos["qty"] = remaining_qty
            if action["type"] == "sell_partial":
                new_pos[action.get("partial_flag", "partial_taken_20")] = True
            kept_positions.append(new_pos)

    positions = kept_positions
    state["cash"] = cash
    state["positions"] = positions
    portfolio_before_buy = build_portfolio_snapshot(state, market_data)

    held = {pos["ticker"] for pos in positions}
    counts = theme_counts(positions)
    sector_stats = analyze_sectors(market_data)
    held_sectors = sector_counts(positions)
    risk_regime = determine_risk_regime(market_data, sector_stats)
    total_value = portfolio_before_buy["total_value"]

    daily_stats = get_daily_buy_stats(state, current)
    total_buys_today = daily_stats["total"]
    rebound_buys_today = daily_stats["rebound"]
    bucket_buys_today = Counter(daily_stats["by_bucket"])

    candidates = sorted(market_data, key=lambda row: candidate_score_v6(row, sector_stats), reverse=True)
    slot_reentry_buys = 0
    slot_high_cash_buys = 0
    slot_oversold_rebound_buys = 0

    for cand in candidates:
        max_positions_for_regime = risk_regime.get("max_positions", MAX_POSITIONS)
        if len(positions) >= min(MAX_POSITIONS, max_positions_for_regime):
            break
        if total_buys_today >= MAX_TOTAL_BUYS_PER_DAY:
            break

        ticker = cand["ticker"]
        if ticker in held or ticker in sold_tickers:
            continue
        if ticker_cooldown_remaining_hours(state, ticker, current) > 0:
            continue

        buy_decision = classify_buy_candidate(
            cand, sector_stats, state, current, portfolio_before_buy, held_sectors, risk_regime=risk_regime
        )
        if not buy_decision.get("ok"):
            continue

        buy_mode = buy_decision.get("mode")
        is_rebound_mode = buy_mode in {"oversold_rebound", "rebound_probe"}
        if buy_mode == "reentry_recovery" and slot_reentry_buys >= MAX_REENTRY_BUYS_PER_SLOT:
            continue
        if buy_mode == "high_cash_deploy" and slot_high_cash_buys >= MAX_HIGH_CASH_BUYS_PER_SLOT:
            continue
        if buy_mode == "oversold_rebound" and slot_oversold_rebound_buys >= MAX_OVERSOLD_REBOUND_BUYS_PER_SLOT:
            continue
        if is_rebound_mode and rebound_buys_today >= MAX_REBOUND_BUYS_PER_DAY:
            continue
        if buy_mode == "oversold_rebound" and (cand.get("grade") == "R" or TICKER_GRADES.get(ticker, "B") == "R"):
            if count_r_grade_rebound_positions(positions) >= MAX_R_GRADE_REBOUND_POSITIONS:
                continue

        theme = cand.get("theme", "")
        sector = cand.get("sector") or broad_sector(theme)
        bucket = exposure_bucket(theme)
        if counts[theme] >= MAX_THEME_POSITIONS:
            continue
        if bucket_buys_today[bucket] >= MAX_SAME_BUCKET_BUYS_PER_DAY:
            continue

        market_price = safe_float(cand.get("last_jpy"))
        if market_price is None or market_price <= 0:
            continue

        friction_pct = estimate_execution_friction_pct(
            ticker=ticker,
            currency=cand.get("currency"),
            grade=cand.get("grade") or TICKER_GRADES.get(ticker, "B"),
        )
        execution_buy_price = apply_execution_friction(market_price, "buy", friction_pct)
        if execution_buy_price is None:
            continue

        min_cash_ratio = buy_decision.get("min_cash_ratio", MIN_CASH_RATIO)
        min_cash_for_buy = int(total_value * min_cash_ratio)
        available_cash = cash - min_cash_for_buy
        if available_cash <= 0:
            continue

        allocation_ratio = buy_decision.get("allocation_ratio", BUY_ALLOCATION_RATIO)
        allocation = min(
            int(total_value * allocation_ratio),
            int(STARTING_CAPITAL * 0.15),
            int(available_cash),
        )

        grade = cand.get("grade") or TICKER_GRADES.get(ticker, "B")
        grade_cap = GRADE_MAX_POSITION_WEIGHTS.get(grade, MAX_POSITION_WEIGHT)
        allocation = min(allocation, int(total_value * min(MAX_POSITION_WEIGHT, grade_cap)))

        qty = int(allocation // execution_buy_price)
        if qty <= 0:
            # 1株単価が高すぎて格付け別上限を超える銘柄は、実運用リスクが大きいため見送る。
            continue

        cost = int(qty * execution_buy_price)
        if cost > cash or cash - cost < min_cash_for_buy:
            continue

        # セクター/テーマの集中を新規買い時点で制限する。
        bucket_cap = BUCKET_MAX_WEIGHTS.get(bucket, 0.25)
        current_bucket_value = bucket_exposure_value(positions, bucket)
        if current_bucket_value + cost > int(total_value * bucket_cap):
            continue

        cash -= cost
        position = {
            "ticker": ticker,
            "name": cand["name"],
            "theme": theme,
            "sector": sector,
            "grade": grade,
            "qty": qty,
            "buy_market_price_jpy": market_price,
            "buy_price_jpy": execution_buy_price,
            "current_price_jpy": market_price,
            "market_value_jpy": int(qty * market_price),
            "pnl_jpy": int(qty * market_price) - cost,
            "pnl_pct": ((market_price / execution_buy_price) - 1.0) * 100.0,
            "execution_friction_pct": friction_pct,
            "peak_price_jpy": market_price,
            "peak_pnl_pct": 0.0,
            "drawdown_from_peak_pct": 0.0,
            "break_even_stop_jpy": None,
            "partial_taken_20": False,
            "partial_taken_rebound": False,
            "buy_mode": buy_mode,
            "rebound_trade": buy_mode == "oversold_rebound",
            "strategy_version": STRATEGY_VERSION,
            "bought_at": current.isoformat(),
        }
        positions.append(position)
        held.add(ticker)
        counts[theme] += 1
        held_sectors[sector] += 1

        execution_cost_jpy = max(0, cost - int(qty * market_price))
        decisions.append(
            {
                "action": "paper_buy",
                "ticker": ticker,
                "qty": qty,
                "amount_jpy": cost,
                "market_amount_jpy": int(qty * market_price),
                "execution_cost_jpy": execution_cost_jpy,
                "execution_friction_pct": friction_pct,
                "buy_mode": buy_mode,
                "candidate_score": buy_decision.get("candidate_score"),
                "risk_regime": risk_regime.get("label"),
                "reason": buy_decision.get("reason"),
            }
        )

        total_buys_today += 1
        bucket_buys_today[bucket] += 1
        if is_rebound_mode:
            rebound_buys_today += 1
        if buy_mode == "reentry_recovery":
            slot_reentry_buys += 1
        elif buy_mode == "high_cash_deploy":
            slot_high_cash_buys += 1
        elif buy_mode == "oversold_rebound":
            slot_oversold_rebound_buys += 1

        # 同一スロット内でも最新の現金比率・保有比率を次候補に反映する。
        state["cash"] = cash
        state["positions"] = positions
        portfolio_before_buy = build_portfolio_snapshot(state, market_data)

    state["cash"] = cash
    state["positions"] = positions
    portfolio = build_portfolio_snapshot(state, market_data)
    portfolio["risk_regime"] = risk_regime

    if not decisions:
        decisions.append(
            {
                "action": "hold",
                "ticker": "-",
                "qty": 0,
                "amount_jpy": 0,
                "risk_regime": risk_regime.get("label"),
                "reason": "売買条件を満たす銘柄なし。v6のクールダウン・集中制限・資金配分規則を維持して保有継続。",
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
    sector_summary = analyze_sectors(market_data)
    risk_regime = determine_risk_regime(market_data, sector_summary)
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
            "reentry_dd_trigger_pct": REENTRY_DD_TRIGGER_PCT,
            "reentry_min_cash_ratio": REENTRY_MIN_CASH_RATIO,
            "reentry_allocation_ratio": REENTRY_ALLOCATION_RATIO,
            "high_cash_deploy_trigger_ratio": HIGH_CASH_DEPLOY_TRIGGER_RATIO,
            "high_cash_deploy_allocation_ratio": HIGH_CASH_DEPLOY_ALLOCATION_RATIO,
            "defense_overheat_avg_pct": DEFENSE_OVERHEAT_AVG_PCT,
            "jp_week_open_buy_block_minutes": JP_WEEK_OPEN_BUY_BLOCK_MINUTES,
            "overheat_5d_pct": OVERHEAT_5D_PCT,
            "memory_overheat_5d_pct": MEMORY_OVERHEAT_5D_PCT,
            "oversold_rebound_daily_range": [REBOUND_DAILY_MIN_PCT, REBOUND_DAILY_MAX_PCT],
            "rebound_allocation_ratio": REBOUND_ALLOCATION_RATIO,
            "rebound_stop_loss_pct": REBOUND_STOP_LOSS_PCT,
            "ticker_cooldown_hours": TICKER_COOLDOWN_HOURS,
            "max_total_buys_per_day": MAX_TOTAL_BUYS_PER_DAY,
            "max_same_bucket_buys_per_day": MAX_SAME_BUCKET_BUYS_PER_DAY,
            "max_rebound_buys_per_day": MAX_REBOUND_BUYS_PER_DAY,
            "risk_regime_min_cash": RISK_REGIME_MIN_CASH,
            "bucket_max_weights": BUCKET_MAX_WEIGHTS,
        },
        "outlook": build_outlook(market_data),
        "risk_regime": risk_regime,
        "usd_jpy": usd_jpy,
        "market_data": market_data,
        "sector_summary": sector_summary,
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
    lines.append(f"Risk regime: {report.get('risk_regime', {}).get('label', '-')}")
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
                f"- {pos['ticker']}: {pos['qty']}株 / 評価 {yen(pos['market_value_jpy'])} / 損益 {yen(pos['pnl_jpy'])} ({pct(pos['pnl_pct'])}) / 高値比 {pct(pos.get('drawdown_from_peak_pct'))} / mode {pos.get('buy_mode', '-')}"
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
