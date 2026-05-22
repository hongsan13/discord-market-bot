import json
import os
import math
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_PATH = DATA_DIR / "reports.json"
DATA_DIR.mkdir(exist_ok=True)

WATCHLIST = [
    {"ticker": "WDC", "name": "Western Digital", "theme": "memory_storage", "currency": "USD"},
    {"ticker": "SNDK", "name": "SanDisk", "theme": "memory_storage", "currency": "USD"},
    {"ticker": "285A.T", "name": "Kioxia", "theme": "memory_storage", "currency": "JPY"},
    {"ticker": "8035.T", "name": "Tokyo Electron", "theme": "semicap_equipment", "currency": "JPY"},
    {"ticker": "6857.T", "name": "Advantest", "theme": "semicap_equipment", "currency": "JPY"},
    {"ticker": "6146.T", "name": "Disco", "theme": "semicap_equipment", "currency": "JPY"},
    {"ticker": "ASML", "name": "ASML", "theme": "semicap_equipment", "currency": "USD"},
    {"ticker": "AMAT", "name": "Applied Materials", "theme": "semicap_equipment", "currency": "USD"},
    {"ticker": "MU", "name": "Micron", "theme": "memory_storage", "currency": "USD"},
    {"ticker": "NVDA", "name": "NVIDIA", "theme": "ai_compute", "currency": "USD"},
    {"ticker": "TSM", "name": "TSMC ADR", "theme": "foundry", "currency": "USD"},
    {"ticker": "VRT", "name": "Vertiv", "theme": "power_cooling", "currency": "USD"},
    {"ticker": "ETN", "name": "Eaton", "theme": "power_cooling", "currency": "USD"},
    {"ticker": "CRWD", "name": "CrowdStrike", "theme": "cybersecurity", "currency": "USD"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "theme": "cybersecurity", "currency": "USD"},
    {"ticker": "7011.T", "name": "Mitsubishi Heavy Industries", "theme": "defense_space", "currency": "JPY"},
    {"ticker": "7012.T", "name": "Kawasaki Heavy Industries", "theme": "defense_space", "currency": "JPY"},
    {"ticker": "7013.T", "name": "IHI", "theme": "defense_space", "currency": "JPY"},
]

THEME_LABELS = {
    "memory_storage": "半導体メモリ/ストレージ",
    "semicap_equipment": "半導体製造装置",
    "ai_compute": "AI計算基盤",
    "foundry": "ファウンドリ",
    "power_cooling": "データセンター電力/冷却",
    "cybersecurity": "サイバーセキュリティ",
    "defense_space": "防衛/宇宙",
}

FX_USDJPY_FALLBACK = 155.0


def now_jst() -> datetime:
    return datetime.now(JST)


def load_reports() -> List[Dict[str, Any]]:
    if not REPORTS_PATH.exists():
        return []
    try:
        return json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_reports(reports: List[Dict[str, Any]]) -> None:
    reports = sorted(reports, key=lambda r: r.get("report_date", ""))
    REPORTS_PATH.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


def get_usd_jpy() -> float:
    try:
        fx = yf.Ticker("JPY=X")
        hist = fx.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        pass
    return FX_USDJPY_FALLBACK


def fetch_prices() -> Dict[str, Dict[str, Any]]:
    tickers = [x["ticker"] for x in WATCHLIST]
    data: Dict[str, Dict[str, Any]] = {}
    for item in WATCHLIST:
        t = item["ticker"]
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period="7d", interval="1d", auto_adjust=False)
            if hist.empty or len(hist["Close"].dropna()) == 0:
                raise ValueError("empty history")
            closes = hist["Close"].dropna()
            last = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
            pct = (last / prev - 1.0) * 100 if prev else 0.0
            vol = int(hist["Volume"].dropna().iloc[-1]) if "Volume" in hist else None
            data[t] = {
                "ticker": t,
                "name": item["name"],
                "theme": item["theme"],
                "currency": item["currency"],
                "last": last,
                "prev_close": prev,
                "pct_change": pct,
                "volume": vol,
            }
        except Exception as e:
            data[t] = {
                "ticker": t,
                "name": item["name"],
                "theme": item["theme"],
                "currency": item["currency"],
                "last": None,
                "prev_close": None,
                "pct_change": None,
                "volume": None,
                "error": str(e),
            }
    return data


def fetch_news(query: str, max_items: int = 5) -> List[Dict[str, str]]:
    # Google News RSS. APIキー不要だが、検索結果は完全性を保証しない。
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        feed = feedparser.parse(url)
        items = []
        for e in feed.entries[:max_items]:
            items.append({
                "title": getattr(e, "title", ""),
                "link": getattr(e, "link", ""),
                "published": getattr(e, "published", ""),
            })
        return items
    except Exception:
        return []


def score_name(pct: float | None) -> str:
    if pct is None:
        return "no-data"
    if pct >= 3:
        return "buy-watch"
    if pct >= 0.5:
        return "hold-watch"
    if pct <= -3:
        return "caution"
    if pct <= -0.5:
        return "weak-watch"
    return "neutral"


def theme_scores(price_data: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    by_theme: Dict[str, List[float]] = {}
    for v in price_data.values():
        if v.get("pct_change") is None:
            continue
        by_theme.setdefault(v["theme"], []).append(float(v["pct_change"]))
    out = {}
    for theme, vals in by_theme.items():
        avg = sum(vals) / len(vals)
        out[THEME_LABELS.get(theme, theme)] = score_name(avg)
    return out


def pick_trade_universe(price_data: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    valid = [v for v in price_data.values() if v.get("last") and v.get("pct_change") is not None]
    # 急騰しすぎは避け、強さがある銘柄を優先
    valid = sorted(valid, key=lambda x: (x["pct_change"], x["last"]), reverse=True)
    return valid[:6]


def to_jpy(price: float, currency: str, usd_jpy: float) -> float:
    return price * usd_jpy if currency == "USD" else price


def simulate_paper_trade(
    reports: List[Dict[str, Any]],
    price_data: Dict[str, Dict[str, Any]],
    starting_capital: int,
    usd_jpy: float,
) -> Tuple[List[Dict[str, Any]], int, int, int, int, List[Dict[str, Any]]]:
    """
    単純ルール:
    - 前日までの最新ポジションを引き継ぐ
    - 当日強い銘柄を最大3銘柄まで仮想保有
    - 1銘柄あたり評価額の20%上限
    - 1日変動が-3%以下の保有銘柄はreduce判定
    - 実際の注文は一切行わない
    """
    last_report = reports[-1] if reports else None
    prev_positions = last_report.get("positions", []) if last_report else []
    cash = int(last_report.get("cash_jpy", starting_capital)) if last_report else starting_capital

    # 前回ポジションを現在値で再評価
    positions = []
    for p in prev_positions:
        ticker = p.get("ticker")
        d = price_data.get(ticker)
        if not d or d.get("last") is None:
            continue
        qty = int(p.get("quantity", 0))
        last_jpy = to_jpy(d["last"], d["currency"], usd_jpy)
        market_value = int(qty * last_jpy)
        avg = float(p.get("avg_price_jpy", last_jpy))
        unreal = int((last_jpy - avg) * qty)
        positions.append({
            "ticker": ticker,
            "name": d["name"],
            "quantity": qty,
            "avg_price_jpy": round(avg, 2),
            "market_value_jpy": market_value,
            "unrealized_pnl_jpy": unreal,
        })

    portfolio_value = cash + sum(p["market_value_jpy"] for p in positions)
    target_names = pick_trade_universe(price_data)

    decisions = []
    decision_times = [
    "10:00", "11:00", "12:00", "13:00", "14:00", "15:00",
    "16:00", "17:00", "18:00", "19:00", "20:00", "21:00",
    "22:00", "23:00", "00:00", "01:00", "02:00", "03:00",
    "04:00", "05:00", "06:00", "09:00"
]

for time_label in decision_times:
        action = "no trade"
        ticker = "-"
        reason = "新規材料が弱く、仮想取引は見送り。"
        if time_label == "10:00":
            if target_names:
                cand = target_names[0]
                ticker = cand["ticker"]
                if cand["pct_change"] >= 1.0:
                    action = "buy-watch"
                    reason = f"{cand['name']}が直近変動率{cand['pct_change']:.2f}%で相対的に強い。寄り後の勢い確認として仮想買い候補。"
                else:
                    action = "hold"
                    reason = "強い候補はあるが、変動率が限定的。仮想ポジションは既存中心。"
        elif time_label == "13:00":
            weak = [p for p in positions if price_data.get(p["ticker"], {}).get("pct_change", 0) <= -3]
            if weak:
                action = "reduce"
                ticker = weak[0]["ticker"]
                reason = "保有銘柄が-3%以上下落。リスク管理として仮想的に縮小候補。"
            else:
                action = "hold"
                reason = "午前時点のトレンドに大きな崩れなし。追撃買いは避け、保有継続。"
        else:
            action = "hold" if positions else "no trade"
            reason = "大引け後は米国市場・先物・為替確認待ち。翌日予想へ反映。"

        decisions.append({"time": time_label, "action": action, "ticker": ticker, "reason": reason})

    # 仮想買い: 既存が少なく、現金があれば上位候補を追加
    positions = portfolio.get("positions", [])
    held = {p["ticker"] for p in positions}
    max_positions = 3
    for cand in target_names:
        if len(positions) >= max_positions:
            break
        if cand["ticker"] in held:
            continue
        if cand["pct_change"] is None or cand["pct_change"] < 1.0:
            continue
        last_jpy = to_jpy(cand["last"], cand["currency"], usd_jpy)
        allocation = min(int(starting_capital * 0.20), int(cash * 0.35))
        qty = int(allocation // last_jpy)
        if qty <= 0:
            continue
        cost = int(qty * last_jpy)
        cash -= cost
        positions.append({
            "ticker": cand["ticker"],
            "name": cand["name"],
            "quantity": qty,
            "avg_price_jpy": round(last_jpy, 2),
            "market_value_jpy": cost,
            "unrealized_pnl_jpy": 0,
        })
        held.add(cand["ticker"])

    portfolio_value = cash + sum(p["market_value_jpy"] for p in positions)
    prev_value = int(last_report.get("portfolio_value_jpy", starting_capital)) if last_report else starting_capital
    daily_pnl = portfolio_value - prev_value
    cumulative_pnl = portfolio_value - starting_capital
    return positions, cash, portfolio_value, daily_pnl, cumulative_pnl, decisions


def build_next_day_outlook(price_data: Dict[str, Dict[str, Any]], scores: Dict[str, str]) -> Dict[str, Any]:
    valid_pcts = [v["pct_change"] for v in price_data.values() if v.get("pct_change") is not None]
    avg = sum(valid_pcts) / len(valid_pcts) if valid_pcts else 0.0

    if avg >= 1.5:
        bias = "bullish"
    elif avg <= -1.5:
        bias = "bearish"
    elif max([abs(x) for x in valid_pcts] or [0]) >= 5:
        bias = "high-volatility"
    else:
        bias = "neutral"

    return {
        "overall_bias": bias,
        "theme_bias": scores,
        "bullish_triggers": [
            "SOX指数・NASDAQの上昇継続",
            "米金利低下またはドル円の円安方向",
            "AI半導体/メモリ/データセンター投資に関する上方修正ニュース",
        ],
        "bearish_triggers": [
            "急騰後の利益確定売り",
            "米長期金利上昇",
            "半導体輸出規制・地政学リスク・決算失望",
        ],
        "watch_indicators": [
            "SOX指数",
            "NASDAQ100",
            "米10年金利",
            "ドル円",
            "NVIDIA/Micron/ASML/TSMC関連ニュース",
        ],
        "disclaimer": "不確実なシナリオであり、値動きや利益を保証しない。",
    }


def build_report(starting_capital: int) -> Dict[str, Any]:
    dt = now_jst()
    reports = load_reports()
    usd_jpy = get_usd_jpy()
    price_data = fetch_prices()
    scores = theme_scores(price_data)
    positions, cash, value, daily_pnl, cum_pnl, decisions = simulate_paper_trade(
        reports, price_data, starting_capital, usd_jpy
    )

    news_queries = [
        "AI data center semiconductor memory storage",
        "半導体 メモリ ストレージ AI データセンター",
        "semiconductor equipment AI demand",
        "data center power cooling AI",
        "cybersecurity AI market",
    ]
    key_news = []
    for q in news_queries:
        for n in fetch_news(q, max_items=2):
            if n["title"] and n["title"] not in [x.get("title") for x in key_news]:
                key_news.append(n)
        if len(key_news) >= 8:
            break

    report = {
        "report_date": dt.strftime("%Y-%m-%d"),
        "generated_at_jst": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "starting_capital_jpy": starting_capital,
        "cash_jpy": cash,
        "portfolio_value_jpy": value,
        "daily_pnl_jpy": daily_pnl,
        "cumulative_pnl_jpy": cum_pnl,
        "usd_jpy": round(usd_jpy, 3),
        "positions": positions,
        "trade_decisions": decisions,
        "theme_scores": scores,
        "next_day_outlook": build_next_day_outlook(price_data, scores),
        "price_snapshot": price_data,
        "key_news": key_news,
        "risks": [
            "本レポートは公開情報ベースの自動整理であり、投資助言ではない。",
            "実注文は行わない。売買判断は自分で行うこと。",
            "勤務先・競合・取引先銘柄は社内規程とインサイダー規制を確認すること。",
            "yfinanceやRSSの取得失敗、遅延、誤差があり得る。",
        ],
        "lessons_learned": [
            "短期の急騰銘柄は追撃買いよりも監視優先。",
            "テーマが強くても、1銘柄集中は避ける。",
            "21時時点では米国市場が通常取引前のため、米国株の当日判断は翌朝確認が必要。",
        ],
    }

    # 同じ日付は上書き
    reports = [r for r in reports if r.get("report_date") != report["report_date"]]
    reports.append(report)
    save_reports(reports)
    return report


def format_jpy(n: Any) -> str:
    try:
        return f"¥{int(n):,}"
    except Exception:
        return "-"


def format_discord(report: Dict[str, Any]) -> str:
    pnl = report["daily_pnl_jpy"]
    cum = report["cumulative_pnl_jpy"]
    pnl_icon = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
    bias = report["next_day_outlook"].get("overall_bias", "-")

    lines = []
    lines.append(f"## 📈 AI市場監視・ペーパートレードレポート {report['report_date']}")
    lines.append("")
    lines.append("### 1. 仮想ポートフォリオ")
    lines.append(f"- 元手: {format_jpy(report['starting_capital_jpy'])}")
    lines.append(f"- 評価額: **{format_jpy(report['portfolio_value_jpy'])}**")
    lines.append(f"- 現金: {format_jpy(report['cash_jpy'])}")
    lines.append(f"- 日次損益: {pnl_icon} **{format_jpy(report['daily_pnl_jpy'])}**")
    lines.append(f"- 累計損益: **{format_jpy(report['cumulative_pnl_jpy'])}**")
    lines.append(f"- USD/JPY: {report.get('usd_jpy', '-')}")
    lines.append("")
    lines.append("### 2. 保有ポジション")
    if report["positions"]:
        for p in report["positions"]:
            lines.append(f"- {p['ticker']} {p.get('name','')}: 数量 {p['quantity']} / 評価 {format_jpy(p['market_value_jpy'])} / 含み損益 {format_jpy(p['unrealized_pnl_jpy'])}")
    else:
        lines.append("- なし")
    lines.append("")
    lines.append("### 3. 10時・13時・16時の仮想判断")
    for d in report["trade_decisions"]:
        lines.append(f"- **{d['time']}** {d['action']} {d['ticker']}: {d['reason']}")
    lines.append("")
    lines.append("### 4. テーマ判定")
    for k, v in report["theme_scores"].items():
        lines.append(f"- {k}: **{v}**")
    lines.append("")
    lines.append("### 5. 翌営業日の方向感")
    lines.append(f"- 全体: **{bias}**")
    lines.append("- 上昇トリガー: " + " / ".join(report["next_day_outlook"].get("bullish_triggers", [])))
    lines.append("- 下落トリガー: " + " / ".join(report["next_day_outlook"].get("bearish_triggers", [])))
    lines.append("")
    lines.append("### 6. 主要ニュース")
    for n in report["key_news"][:5]:
        title = n.get("title", "")
        link = n.get("link", "")
        lines.append(f"- {title}\n  {link}")
    lines.append("")
    lines.append("### 7. 注意")
    lines.append("- 実売買なし。投資助言ではなく、公開情報ベースの監視レポート。")
    lines.append("- 翌日予想は不確実なシナリオ。利益保証ではない。")
    lines.append("")
    lines.append("```json")
    slim = {
        "report_date": report["report_date"],
        "starting_capital_jpy": report["starting_capital_jpy"],
        "cash_jpy": report["cash_jpy"],
        "portfolio_value_jpy": report["portfolio_value_jpy"],
        "daily_pnl_jpy": report["daily_pnl_jpy"],
        "cumulative_pnl_jpy": report["cumulative_pnl_jpy"],
        "positions": report["positions"],
        "trade_decisions": report["trade_decisions"],
        "theme_scores": report["theme_scores"],
        "next_day_outlook": report["next_day_outlook"],
        "key_news": report["key_news"][:5],
        "risks": report["risks"],
        "lessons_learned": report["lessons_learned"],
    }
    lines.append(json.dumps(slim, ensure_ascii=False, indent=2)[:1500])
    lines.append("```")
    return "\n".join(lines)


def send_discord(webhook_url: str, content: str) -> None:
    # Discordのcontent上限対策。長すぎる場合は複数投稿。
    chunks = []
    current = ""
    for line in content.splitlines():
        if len(current) + len(line) + 1 > 1800:
            chunks.append(current)
            current = line
        else:
            current += ("\n" if current else "") + line
    if current:
        chunks.append(current)

    for i, chunk in enumerate(chunks):
        payload = {"content": chunk}
        if i == 0:
            payload["username"] = "AI Market Monitor"
        r = requests.post(webhook_url, json=payload, timeout=30)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"Discord webhook failed: {r.status_code} {r.text}")


def main() -> None:
    load_dotenv()
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    starting_capital = int(os.getenv("STARTING_CAPITAL_JPY", "1000000"))
    report = build_report(starting_capital)
    content = format_discord(report)

    # GitHub Actions上でWebhook未設定の場合でもreports.jsonだけは更新できる。
    if webhook:
        send_discord(webhook, content)
        print("Discord report sent.")
    else:
        print("DISCORD_WEBHOOK_URL is empty. Report generated only.")
        print(content[:3000])


if __name__ == "__main__":
    main()
