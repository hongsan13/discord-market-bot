"""Offline fixtures only: no bot execution, network, or operational state writes."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest

from weekly.metrics import build_digest


AS_OF = datetime(2026, 8, 28, 12, tzinfo=timezone(timedelta(hours=9)))
START = AS_OF - timedelta(days=7)


def report(at, total=1_000_000, decisions=None, **extra):
    result = {
        "generated_at": at.isoformat(), "strategy_version": "v6_risk_adjusted_execution",
        "portfolio": {"total_value": total, "cash": 700_000,
                      "starting_capital": 1_000_000,
                      "pnl_jpy": total - 1_000_000,
                      "pnl_pct": (total - 1_000_000) / 10_000,
                      "realized_pnl_jpy": 35_000,
                      "portfolio_peak_value_jpy": 1_200_000, "positions": []},
        "decisions": decisions or [], "market_data": [],
    }
    result.update(extra)
    return result


def state_with(*reports, trades=None):
    return {"reports": list(reports), "latest": deepcopy(reports[-1]) if reports else {},
            "realized_trades": [] if trades is None else trades,
            "starting_capital": 1_000_000}


class DigestTests(unittest.TestCase):
    def test_exact_window_is_open_left_closed_right_including_trades(self):
        buy = {"action": "paper_buy", "buy_mode": "scale_in"}
        reports = [report(START, decisions=[buy]),
                   report(START + timedelta(microseconds=1), decisions=[buy]),
                   report(AS_OF, 1_100_000, [buy, {"action": "hold"}]),
                   report(AS_OF + timedelta(microseconds=1), 9_999_999, [buy])]
        trades = [{"sold_at": at.isoformat(), "realized_pnl_jpy": pnl}
                  for at, pnl in [(START, 100), (START + timedelta(microseconds=1), 5),
                                  (AS_OF, -2), (AS_OF + timedelta(microseconds=1), 900)]]
        digest = build_digest(state_with(*reports, trades=trades), AS_OF)
        self.assertEqual(digest["portfolio"]["window_pnl_jpy"], 100_000)
        self.assertEqual(digest["portfolio"]["window_pnl_pct"], 10)
        self.assertEqual(digest["activity"], {"buys": 2, "scale_ins": 2, "sells": 2,
                                               "holds": 1, "realized_pnl_jpy": 3})

    def test_missing_baseline_does_not_substitute_first_in_window(self):
        digest = build_digest(state_with(report(START + timedelta(hours=1)),
                                         report(AS_OF, 1_100_000)), AS_OF)
        self.assertIsNone(digest["portfolio"]["window_pnl_jpy"])
        self.assertIsNone(digest["portfolio"]["window_pnl_pct"])
        self.assertIsNone(digest["portfolio"]["baseline_at"])
        self.assertTrue(any("基準レポートがなく" in warning for warning in digest["warnings"]))

    def test_old_baseline_is_not_used_as_weekly_performance(self):
        digest = build_digest(state_with(report(START - timedelta(hours=24, seconds=1)),
                                         report(AS_OF, 1_100_000)), AS_OF)
        self.assertIsNone(digest["portfolio"]["window_pnl_pct"])
        self.assertGreater(digest["portfolio"]["baseline_gap_hours"], 24)

    def test_baseline_gap_is_disclosed_with_observation_time(self):
        baseline_at = START - timedelta(hours=1)
        digest = build_digest(state_with(report(baseline_at), report(AS_OF, 1_100_000)), AS_OF)
        self.assertEqual(digest["portfolio"]["baseline_at"], baseline_at.isoformat())
        self.assertEqual(digest["portfolio"]["baseline_gap_hours"], 1)
        self.assertEqual(digest["portfolio"]["window_pnl_jpy"], 100_000)
        self.assertTrue(any("厳密な" in warning for warning in digest["warnings"]))

    def test_stale_and_sparse_history_warns_and_does_not_claim_weekly_return(self):
        digest = build_digest(state_with(report(START), report(AS_OF - timedelta(days=2))), AS_OF)
        self.assertEqual(digest["stale_hours"], 48)
        self.assertIsNone(digest["portfolio"]["window_pnl_pct"])
        self.assertTrue(any("観測が古い" in warning for warning in digest["warnings"]))
        self.assertTrue(any("レポート間隔" in warning for warning in digest["warnings"]))

    def test_input_is_never_mutated_and_output_does_not_alias_it(self):
        latest = report(AS_OF, 1_100_000)
        latest["portfolio"]["positions"] = [{"ticker": "NVDA", "qty": 1,
                                            "market_value_jpy": 50_000}]
        state = state_with(report(START), latest)
        before = deepcopy(state)
        digest = build_digest(state, AS_OF)
        digest["holdings"][0]["ticker"] = "changed"
        self.assertEqual(state, before)
        self.assertEqual(digest["holdings"][0]["scale_in_count"], 0)
        json.dumps(digest, ensure_ascii=False, allow_nan=False)

    def test_zero_denominators_are_null_not_infinity(self):
        latest = report(AS_OF, 0)
        latest["portfolio"].pop("pnl_pct")
        latest["portfolio"]["starting_capital"] = 0
        latest["portfolio"]["portfolio_peak_value_jpy"] = 0
        digest = build_digest(state_with(report(START, 0), latest), AS_OF)
        self.assertEqual(digest["portfolio"]["window_pnl_jpy"], 0)
        for key in ("cash_ratio", "pnl_pct", "window_pnl_pct", "peak_drawdown_pct"):
            self.assertIsNone(digest["portfolio"][key], key)
        json.dumps(digest, allow_nan=False)

    def test_equity_curve_is_sorted_deduplicated_and_has_no_future_points(self):
        latest = report(AS_OF, 1_100_000)
        state = state_with(latest, report(START - timedelta(seconds=1)), report(START),
                           deepcopy(latest), report(AS_OF + timedelta(seconds=1), 9_999_999))
        digest = build_digest(state, AS_OF)
        self.assertEqual(digest["equity_curve"], [
            {"at": START.isoformat(), "total_value": 1_000_000},
            {"at": AS_OF.isoformat(), "total_value": 1_100_000},
        ])

    def test_gap_limits_are_inclusive_at_24_and_36_hours(self):
        digest = build_digest(state_with(report(START - timedelta(hours=24)),
                                         report(AS_OF - timedelta(hours=36), 1_100_000)), AS_OF)
        self.assertEqual(digest["portfolio"]["window_pnl_pct"], 10)
        self.assertEqual(digest["portfolio"]["baseline_gap_hours"], 24)
        self.assertEqual(digest["stale_hours"], 36)

    def test_invalid_and_future_only_reports_have_no_current_snapshot(self):
        state = state_with(report(AS_OF + timedelta(seconds=1), 9_999_999))
        state["reports"].append({"generated_at": "not-a-date", "portfolio": {"total_value": 1}})
        digest = build_digest(state, AS_OF)
        self.assertIsNone(digest["portfolio"]["total_value"])
        self.assertEqual(digest["equity_curve"], [])
        self.assertTrue(any("日時が不明" in warning for warning in digest["warnings"]))

    def test_current_zero_and_missing_legacy_scale_in_fields_are_preserved(self):
        latest = report(AS_OF)
        latest["portfolio"].update({"cash": 0, "pnl_jpy": 0, "pnl_pct": 0,
                                    "portfolio_drawdown_pct": 0})
        latest["portfolio"]["positions"] = [{"ticker": "AAA", "qty": 1, "pnl_pct": 0,
                                            "market_value_jpy": 30_000, "grade": "S"}]
        digest = build_digest(state_with(report(START), latest), AS_OF)
        self.assertEqual(digest["portfolio"]["cash_ratio"], 0)
        self.assertEqual(digest["portfolio"]["peak_drawdown_pct"], 0)
        self.assertEqual(digest["holdings"][0]["scale_in_count"], 0)
        self.assertEqual(digest["holdings"][0]["weight_pct"], 3)
        self.assertEqual(digest["holdings"][0]["pnl_pct"], 0)

    def test_latest_duplicate_is_counted_once(self):
        latest = report(AS_OF, decisions=[{"action": "paper_buy"}])
        state = state_with(report(START), latest, deepcopy(latest))
        digest = build_digest(state, AS_OF)
        self.assertEqual(digest["activity"]["buys"], 1)

    def test_newest_report_wins_over_stale_latest_in_unsorted_history(self):
        current = report(AS_OF, 1_200_000)
        current["strategy_version"] = "v7_scale_in_profit_guard"
        state = state_with(current, report(START), report(AS_OF - timedelta(hours=1), 1_100_000))
        digest = build_digest(state, AS_OF)
        self.assertEqual(digest["portfolio"]["total_value"], 1_200_000)
        self.assertEqual(digest["strategy_version"], "v7_scale_in_profit_guard")

    def test_latest_can_supply_newer_report_missing_from_history(self):
        state = state_with(report(START))
        state["latest"] = report(AS_OF, 1_300_000, [{"action": "paper_buy"}])
        digest = build_digest(state, AS_OF)
        self.assertEqual(digest["portfolio"]["total_value"], 1_300_000)
        self.assertEqual(digest["activity"]["buys"], 1)

    def test_same_time_conflict_prefers_reports_and_warns(self):
        state = state_with(report(START), report(AS_OF, 1_100_000))
        state["latest"] = report(AS_OF, 9_999_999, [{"action": "paper_buy"}])
        digest = build_digest(state, AS_OF)
        self.assertEqual(digest["portfolio"]["total_value"], 1_100_000)
        self.assertEqual(digest["activity"]["buys"], 0)
        self.assertTrue(any("不一致" in warning for warning in digest["warnings"]))

    def test_sector_coverage_excludes_missing_5d_without_using_daily_change(self):
        latest = report(AS_OF, market_data=[
            {"sector": "半導体", "change_5d": 10, "pct_change": 100},
            {"sector": "半導体", "change_5d": -2},
            {"sector": "半導体", "change_5d": None, "pct_change": 300},
            {"sector": "AIクラウド", "pct_change": 50},
            {"sector": "AIクラウド", "change_5d": float("nan")},
        ])
        digest = build_digest(state_with(report(START), latest), AS_OF)
        sectors = {item["name"]: item for item in digest["sectors"]}
        self.assertEqual(sectors["半導体"], {"name": "半導体", "change_5d_pct": 4,
                                             "coverage": 2, "total": 3})
        self.assertIsNone(sectors["AIクラウド"]["change_5d_pct"])
        self.assertEqual(sectors["AIクラウド"]["coverage"], 0)
        json.dumps(digest, allow_nan=False)

    def test_cumulative_and_period_realized_pnl_are_separate(self):
        trades = [{"sold_at": AS_OF.isoformat(), "realized_pnl_jpy": -40}]
        digest = build_digest(state_with(report(START), report(AS_OF, 1_100_000),
                                         trades=trades), AS_OF)
        self.assertEqual(digest["portfolio"]["pnl_jpy"], 100_000)
        self.assertEqual(digest["portfolio"]["realized_pnl_jpy"], 35_000)
        self.assertEqual(digest["activity"]["realized_pnl_jpy"], -40)

    def test_future_mutable_state_is_not_used_for_historical_snapshot(self):
        old = report(AS_OF)
        old["portfolio"].pop("realized_pnl_jpy")
        state = state_with(report(START), old, report(AS_OF + timedelta(days=1), 2_000_000))
        state.update({"cash": 9_999_999, "realized_pnl_jpy": 999_999,
                      "positions": [{"ticker": "FUTURE"}], "strategy_version": "future"})
        digest = build_digest(state, AS_OF)
        self.assertEqual(digest["portfolio"]["cash"], 700_000)
        self.assertIsNone(digest["portfolio"]["realized_pnl_jpy"])
        self.assertEqual(digest["holdings"], [])
        self.assertEqual(digest["strategy_version"], "v6_risk_adjusted_execution")

    def test_utc_and_jst_are_compared_as_instants(self):
        utc_latest = report(AS_OF.astimezone(timezone.utc), 1_100_000)
        digest = build_digest(state_with(report(START), utc_latest), AS_OF)
        self.assertEqual(digest["latest_at"], AS_OF.isoformat())
        self.assertEqual(digest["stale_hours"], 0)

    def test_legacy_date_time_without_timezone_is_jst(self):
        latest = report(AS_OF)
        latest.pop("generated_at")
        latest.update({"date": "2026-08-28", "time": "12:00:00"})
        digest = build_digest(state_with(report(START), latest), AS_OF)
        self.assertEqual(digest["latest_at"], AS_OF.isoformat())
        self.assertTrue(any("JST" in warning for warning in digest["warnings"]))

    def test_truncated_lifetime_history_is_disclosed(self):
        trade = {"sold_at": (START - timedelta(days=30)).isoformat(), "realized_pnl_jpy": 1}
        digest = build_digest(state_with(report(START), report(AS_OF), trades=[trade]), AS_OF)
        self.assertTrue(any("運用開始時から揃っていない" in warning for warning in digest["warnings"]))

    def test_invalid_trade_data_never_becomes_zero_known_pnl(self):
        for trade in ({"sold_at": "invalid", "realized_pnl_jpy": 10},
                      {"sold_at": AS_OF.isoformat(), "realized_pnl_jpy": None}):
            with self.subTest(trade=trade):
                digest = build_digest(state_with(report(START), report(AS_OF), trades=[trade]), AS_OF)
                self.assertIsNone(digest["activity"]["realized_pnl_jpy"])

    def test_empty_legacy_state_is_json_serializable_without_fake_current_values(self):
        digest = build_digest({"cash": 999, "positions": []}, AS_OF)
        self.assertIsNone(digest["portfolio"]["total_value"])
        self.assertIsNone(digest["activity"]["sells"])
        self.assertIsNone(digest["latest_at"])
        self.assertTrue(digest["warnings"])
        json.dumps(digest, ensure_ascii=False, allow_nan=False)

    def test_bad_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            build_digest({}, AS_OF.replace(tzinfo=None))
        for days in (0, -1, True, 0.5):
            with self.subTest(days=days), self.assertRaises(ValueError):
                build_digest({}, AS_OF, days)


if __name__ == "__main__":
    unittest.main()
