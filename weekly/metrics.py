"""Read-only weekly statistics for the paper-trading report format.

Activity uses the half-open interval ``(as_of - period_days, as_of]``. Returns
compare the newest snapshot with the last snapshot at/before that interval.
The actual observation times and gaps are exposed; absent/stale endpoints do
not become a misleading full-week return. This module performs no I/O and
never imports or executes the trading bot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math


JST = timezone(timedelta(hours=9))
MAX_BASELINE_GAP_HOURS = 24.0
STALE_AFTER_HOURS = 36.0


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _ratio(numerator, denominator, multiplier=1.0):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    result = numerator / denominator * multiplier
    return result if math.isfinite(result) else None


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # The legacy bot's date/time fields are JST, including timezone-less dates.
    return parsed.replace(tzinfo=JST) if parsed.tzinfo is None else parsed


def _report_time(report):
    parsed = _timestamp(report.get("generated_at"))
    if parsed is None and report.get("date") and report.get("time"):
        parsed = _timestamp(f"{report['date']}T{report['time']}")
    return parsed


def _records(state, as_of, warnings):
    """Deduplicate execution timestamps; reports are authoritative over latest."""
    reports = state.get("reports", [])
    if not isinstance(reports, list):
        reports = []
        warnings.append("reports が配列ではないため、保存済み履歴を集計できません。")
    candidates = list(reports)
    if isinstance(state.get("latest"), dict):
        candidates.append(state["latest"])
    records = {}
    invalid = conflicts = naive = 0
    for report in candidates:
        if not isinstance(report, dict):
            invalid += 1
            continue
        at = _report_time(report)
        if at is None:
            invalid += 1
            continue
        raw_time = report.get("generated_at", "")
        if not raw_time or (isinstance(raw_time, str) and
                            "+" not in raw_time[10:] and
                            "-" not in raw_time[10:] and not raw_time.endswith("Z")):
            naive += 1
        if at in records:
            conflicts += records[at] != report
            continue
        records[at] = report
    if invalid:
        warnings.append(f"日時が不明なレポート {invalid} 件を集計から除外しました。")
    if conflicts:
        warnings.append("同一日時のレポートに不一致があります。reports 側を優先し、重複計上していません。")
    if naive:
        warnings.append("タイムゾーンのない旧レポート日時は、Bot の仕様に合わせて JST として扱いました。")
    future = sum(at > as_of for at in records)
    if future:
        warnings.append(f"集計時刻より未来のレポート {future} 件を除外しました。")
    return sorted((at, report) for at, report in records.items() if at <= as_of)


def _portfolio(report):
    value = report.get("portfolio", {})
    return value if isinstance(value, dict) else {}


def _sectors(report):
    groups = {}
    rows = report.get("market_data", [])
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name = row.get("sector") or row.get("theme") or "分類なし"
        name = name if isinstance(name, str) else "分類なし"
        group = groups.setdefault(name, {"name": name, "values": [], "total": 0})
        group["total"] += 1
        change = _number(row.get("change_5d"))
        if change is not None:
            group["values"].append(change)
    return [
        {"name": group["name"],
         "change_5d_pct": (sum(group["values"]) / len(group["values"])
                           if group["values"] else None),
         "coverage": len(group["values"]), "total": group["total"]}
        for group in sorted(groups.values(), key=lambda value: value["name"])
    ]


def _holdings(portfolio):
    holdings = []
    positions = portfolio.get("positions", [])
    for position in positions if isinstance(positions, list) else []:
        if not isinstance(position, dict):
            continue
        item = {key: (position.get(key) if isinstance(position.get(key), str) else None)
                for key in ("ticker", "name", "sector", "grade", "buy_mode")}
        item.update({key: _number(position.get(key))
                     for key in ("qty", "market_value_jpy", "pnl_jpy", "pnl_pct",
                                 "peak_pnl_pct", "drawdown_from_peak_pct")})
        count = _number(position.get("scale_in_count"))
        item["scale_in_count"] = max(0, int(count)) if count is not None else 0
        item["weight_pct"] = _ratio(item["market_value_jpy"],
                                     _number(portfolio.get("total_value")), 100)
        holdings.append(item)
    return holdings


def _activity(state, records, period_start, as_of, warnings):
    activity = {"buys": 0, "scale_ins": 0, "sells": 0, "holds": 0,
                "realized_pnl_jpy": None}
    for at, report in records:
        if not period_start < at <= as_of:
            continue
        decisions = report.get("decisions", [])
        for decision in decisions if isinstance(decisions, list) else []:
            if not isinstance(decision, dict):
                continue
            if decision.get("action") == "paper_buy":
                activity["buys"] += 1
                activity["scale_ins"] += decision.get("buy_mode") == "scale_in"
            elif decision.get("action") == "hold":
                activity["holds"] += 1
    trades = state.get("realized_trades")
    if not isinstance(trades, list):
        warnings.append("実現損益の約定履歴がないため、期間中の売却件数・実現損益は確認できません。")
        activity["sells"] = None
        return activity
    realized = 0
    invalid_dates = missing_pnl = 0
    for trade in trades:
        if not isinstance(trade, dict):
            invalid_dates += 1
            continue
        at = _timestamp(trade.get("sold_at"))
        if at is None:
            invalid_dates += 1
            continue
        if period_start < at <= as_of:
            activity["sells"] += 1
            pnl = _number(trade.get("realized_pnl_jpy"))
            if pnl is None:
                missing_pnl += 1
            else:
                realized += pnl
    if invalid_dates:
        warnings.append(f"売却日時が不明な約定 {invalid_dates} 件を除外したため、期間中の約定集計は不完全な可能性があります。")
    if missing_pnl:
        warnings.append("期間中の約定に損益不明の記録があり、実現損益は算出していません。")
    activity["realized_pnl_jpy"] = None if missing_pnl or invalid_dates else realized
    return activity


def build_digest(state: dict, as_of: datetime, period_days=7) -> dict:
    """Build JSON-serializable metrics without changing the supplied state.

    Cash ratio is a fraction; all ``*_pct`` values are percentages. Portfolio
    P/L is since inception, activity P/L is only for the requested interval.
    Sell counts include partial sells; buy counts include scale-ins. Holds are
    hold decisions (not calendar days). Missing amounts are null, not zero.
    Mutable top-level portfolio fields are never used to fill older snapshots.
    """
    if not isinstance(state, dict):
        raise TypeError("state must be a dictionary")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    if isinstance(period_days, bool) or not isinstance(period_days, int) or period_days <= 0:
        raise ValueError("period_days must be a positive integer")
    period_start = as_of - timedelta(days=period_days)
    warnings = []
    records = _records(state, as_of, warnings)
    latest_at, latest = records[-1] if records else (None, {})
    snapshot = _portfolio(latest)
    total = _number(snapshot.get("total_value"))
    cash = _number(snapshot.get("cash"))
    starting = _number(snapshot.get("starting_capital", state.get("starting_capital")))
    pnl = _number(snapshot.get("pnl_jpy"))
    if pnl is None and total is not None and starting is not None:
        pnl = total - starting
    pnl_pct = _number(snapshot.get("pnl_pct"))
    if pnl_pct is None:
        pnl_pct = _ratio(pnl, starting, 100)
    peak_drawdown = _number(snapshot.get("portfolio_drawdown_pct"))
    if peak_drawdown is None:
        peak_ratio = _ratio(total, _number(snapshot.get("portfolio_peak_value_jpy")))
        peak_drawdown = (peak_ratio - 1) * 100 if peak_ratio is not None else None
    stale_hours = (as_of - latest_at).total_seconds() / 3600 if latest_at else None
    if latest_at is None:
        warnings.append("集計時刻以前の有効なレポートがありません。現在の資産・保有状況は確認できません。")
    elif total is None:
        warnings.append("最新レポートの総資産が不明です。資産騰落率を算出できません。")
    if total is not None and total <= 0:
        warnings.append("総資産がゼロ以下のため、現金比率・保有比率を算出していません。")
    if stale_hours is not None and stale_hours > STALE_AFTER_HOURS:
        warnings.append(f"最新レポートは {stale_hours:.1f} 時間前です。期間末の観測が古いため、週次損益は算出していません。")

    baseline = next(((at, report) for at, report in reversed(records)
                     if at <= period_start and
                     _number(_portfolio(report).get("total_value")) is not None), None)
    baseline_at = baseline[0] if baseline else None
    baseline_gap = (period_start - baseline_at).total_seconds() / 3600 if baseline_at else None
    window_pnl = window_pct = None
    if baseline is None:
        warnings.append("期間開始以前の基準レポートがなく、全期間をカバーできません。週次損益は算出していません。")
    elif baseline_gap > MAX_BASELINE_GAP_HOURS:
        warnings.append(f"基準レポートが期間開始より {baseline_gap:.1f} 時間前と離れているため、週次損益は算出していません。")
    elif latest_at is not None and latest_at > period_start and total is not None and stale_hours <= STALE_AFTER_HOURS:
        baseline_total = _number(_portfolio(baseline[1]).get("total_value"))
        window_pnl = total - baseline_total
        window_pct = _ratio(window_pnl, baseline_total, 100)
        if baseline_total <= 0:
            warnings.append("基準レポートの総資産がゼロ以下のため、期間騰落率は算出していません。")
        if baseline_gap:
            warnings.append(f"期間損益の基準は開始時刻の {baseline_gap:.2f} 時間前の観測値です。厳密な {period_days} 日間騰落率ではありません。")

    if records:
        relevant = [at for at, _ in records if at >= period_start]
        if baseline_at is not None:
            relevant.insert(0, baseline_at)
        gaps = [(right - left).total_seconds() / 3600
                for left, right in zip(relevant, relevant[1:])]
        if gaps and max(gaps) > STALE_AFTER_HOURS:
            warnings.append(f"集計区間内に最大 {max(gaps):.1f} 時間のレポート間隔があります。売買件数は保存済み履歴の範囲です。")
        oldest_at, oldest_report = records[0]
        old_trades = state.get("realized_trades", [])
        evidence_of_earlier = any(
            (trade_at := _timestamp(trade.get("sold_at"))) is not None
            and trade_at < oldest_at
            for trade in old_trades if isinstance(trade, dict)
        ) if isinstance(old_trades, list) else False
        first_pnl = _number(_portfolio(oldest_report).get("pnl_jpy"))
        if evidence_of_earlier or (first_pnl is not None and first_pnl != 0):
            warnings.append("保存されたレポート履歴は運用開始時から揃っていない可能性があります。累計損益はスナップショットの値です。")

    def iso(value):
        return value.astimezone(as_of.tzinfo).isoformat() if value else None

    activity = _activity(state, records, period_start, as_of, warnings)
    return {
        "generated_at": as_of.isoformat(), "latest_at": iso(latest_at),
        "period_start": period_start.isoformat(), "period_end": as_of.isoformat(),
        "stale_hours": stale_hours, "warnings": warnings,
        "strategy_version": (latest.get("strategy_version")
                             if isinstance(latest.get("strategy_version"), str) else None),
        "portfolio": {
            "total_value": total, "cash": cash, "cash_ratio": _ratio(cash, total),
            "pnl_jpy": pnl, "pnl_pct": pnl_pct,
            "realized_pnl_jpy": _number(snapshot.get("realized_pnl_jpy")),
            "peak_drawdown_pct": peak_drawdown,
            "window_pnl_jpy": window_pnl, "window_pnl_pct": window_pct,
            "baseline_at": iso(baseline_at), "baseline_gap_hours": baseline_gap,
        },
        "activity": activity,
        "sectors": _sectors(latest), "holdings": _holdings(snapshot),
        "equity_curve": [
            {"at": iso(at), "total_value": _number(_portfolio(report).get("total_value"))}
            for at, report in records if period_start <= at <= as_of
            and _number(_portfolio(report).get("total_value")) is not None
        ],
    }
