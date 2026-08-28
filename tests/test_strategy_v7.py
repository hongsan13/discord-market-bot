import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import market_discord_bot as bot


NOW = datetime(2026, 8, 28, 12, tzinfo=bot.JST)


def row(ticker="NVDA", **changes):
    item = next(x for x in bot.WATCHLIST if x["ticker"] == ticker)
    result = dict(item, grade=bot.TICKER_GRADES[ticker], last_jpy=1040.0,
                  last=1040.0, pct_change=1.3, change_15m=0.3,
                  change_5d=4.0, change_10d=6.0, change_20d=8.0,
                  high_20d_ratio=0.95, distance_from_20d_high_pct=-5.0)
    result["sector"] = bot.broad_sector(result["theme"])
    result.update(changes)
    return result


def holding(ticker="NVDA", **changes):
    r = row(ticker)
    result = dict(ticker=ticker, name=r["name"], theme=r["theme"],
                  sector=r["sector"], grade=r["grade"], qty=50,
                  buy_price_jpy=1000.0, buy_market_price_jpy=998.0,
                  current_price_jpy=1040.0, peak_price_jpy=1040.0,
                  peak_pnl_pct=4.0, buy_mode="normal_momentum",
                  bought_at=(NOW - timedelta(days=3)).isoformat())
    result.update(changes)
    return result


def state(positions=None):
    s = bot.default_state()
    s["positions"] = positions if positions is not None else [holding()]
    s["cash"] = 1_000_000 - sum(int(p["qty"] * p["current_price_jpy"]) for p in s["positions"])
    return s


class StrategyTests(unittest.TestCase):
    def setUp(self):
        # All tests are offline. Any accidental live entry point fails immediately.
        for target in ("requests.sessions.Session.request", "yfinance.Ticker",
                       "market_discord_bot.send_discord_content", "market_discord_bot.write_state"):
            p = patch(target, side_effect=AssertionError("Live I/O forbidden"))
            p.start()
            self.addCleanup(p.stop)

    def run_portfolio(self, s=None, r=None, regime="risk_on", current=NOW):
        s = s if s is not None else state()
        rows = r if isinstance(r, list) else [r or row()]
        real = bot.determine_risk_regime(rows, bot.analyze_sectors(rows))
        real.update(label=regime, min_cash_ratio=bot.RISK_REGIME_MIN_CASH[regime],
                    max_positions=bot.RISK_REGIME_MAX_POSITIONS[regime])
        with patch.object(bot, "determine_risk_regime", return_value=real):
            portfolio, decisions = bot.update_paper_portfolio(s, rows, current)
        return s, portfolio, decisions

    def buys(self, result):
        return [d for d in result[2] if d["action"] == "paper_buy"]

    def test_scale_in_at_five_positions_s_and_a(self):
        for ticker in ("NVDA", "ANET"):
            with self.subTest(ticker=ticker):
                others = [holding(t, qty=1) for t in ("DELL", "STX", "7011.T", "7012.T")]
                s = state([holding(ticker)] + others)
                result = self.run_portfolio(s, row(ticker))
                buys = self.buys(result)
                self.assertEqual([d["buy_mode"] for d in buys], ["scale_in"])
                self.assertEqual(len(result[1]["positions"]), 5)
                p = result[1]["positions"][0]
                self.assertGreater(p["qty"], 50)
                self.assertEqual(p["scale_in_count"], 1)
                self.assertGreater(buys[0]["execution_cost_jpy"], 0)
                self.assertAlmostEqual(p["buy_price_jpy"],
                                       (50 * 1000 + buys[0]["amount_jpy"]) / p["qty"])
                self.assertEqual(bot.get_daily_buy_stats(
                    dict(s, reports=[{"date": NOW.strftime("%Y-%m-%d"), "decisions": buys}]), NOW)["total"], 1)

    def test_no_scale_in_in_defensive_regimes(self):
        for regime in ("neutral", "cautious", "risk_off"):
            with self.subTest(regime=regime):
                self.assertFalse(self.buys(self.run_portfolio(regime=regime)))

    def test_no_scale_in_b_or_r(self):
        for grade in ("B", "R"):
            with self.subTest(grade=grade):
                self.assertFalse(self.buys(self.run_portfolio(
                    state([holding(grade=grade)]), row(grade=grade))))

    def test_ticker_and_sector_cooldowns(self):
        for kind in ("ticker", "sector"):
            with self.subTest(kind=kind):
                s = state()
                if kind == "ticker":
                    bot.set_ticker_cooldown(s, "NVDA", NOW, "paper_take_profit")
                else:
                    # Even the S/A rebound exception after 12h cannot enable scale-in.
                    bot.set_sector_cooldown(s, row()["sector"], NOW, hours=1)
                self.assertFalse(self.buys(self.run_portfolio(s)))

    def test_daily_total_and_bucket_limits(self):
        for tickers in (["NVDA", "ANET", "MSFT"], ["NVDA", "TSM"]):
            with self.subTest(tickers=tickers):
                s = state()
                s["reports"] = [{"date": NOW.strftime("%Y-%m-%d"), "decisions": [
                    {"action": "paper_buy", "ticker": t, "buy_mode": "scale_in"} for t in tickers
                ]}]
                self.assertFalse(self.buys(self.run_portfolio(s)))

    def test_sector_and_position_caps(self):
        cases = [
            [holding(qty=144, current_price_jpy=1040)],
            [holding(), holding("TSM", qty=285, current_price_jpy=1040)],
        ]
        for positions in cases:
            with self.subTest(positions=len(positions)):
                self.assertFalse(self.buys(self.run_portfolio(state(positions))))

    def test_cash_floor_and_insufficient_single_share_budget(self):
        s = state()
        s["cash"] = 22000  # cash ratio is below risk_on floor
        self.assertFalse(self.buys(self.run_portfolio(s)))
        s = state([holding(qty=1, buy_price_jpy=40000, current_price_jpy=42000,
                                 peak_price_jpy=42000)])
        self.assertFalse(self.buys(self.run_portfolio(s, row(last_jpy=42000))))

    def test_success_respects_post_friction_caps_and_cash(self):
        s, p, decisions = self.run_portfolio()
        pos = p["positions"][0]
        self.assertGreaterEqual(p["cash"] / p["total_value"], 0.30)
        self.assertLessEqual(pos["market_value_jpy"] / p["total_value"], 0.15)
        self.assertLessEqual(bot.bucket_exposure_value(p["positions"], row()["sector"]) / p["total_value"], 0.35)
        self.assertEqual(s["cash"], 948000 - self.buys((s, p, decisions))[0]["amount_jpy"])

    def test_pnl_threshold_and_stage_boundaries(self):
        for pnl, allowed in ((1.99, False), (2.0, True)):
            pos = holding(pnl_pct=pnl)
            info = bot.analyze_sectors([row()])
            self.assertEqual(bot.classify_scale_in(pos, row(), info, state(), NOW,
                                                  {"label": "risk_on"})["ok"], allowed)
        for count, pnl, regime, allowed in (
            (1, 3.99, "risk_on", False), (1, 4.0, "risk_on", True),
            (2, 6.0, "risk_on", False), (2, 6.0, "strong_risk_on", True),
            (2, 5.99, "strong_risk_on", False), (3, 9.0, "strong_risk_on", False),
        ):
            with self.subTest(count=count, pnl=pnl, regime=regime):
                pos = holding(scale_in_count=count, pnl_pct=pnl)
                self.assertEqual(bot.classify_scale_in(pos, row(), bot.analyze_sectors([row()]),
                                                      state(), NOW, {"label": regime})["ok"], allowed)

    def test_interval_missing_timestamp_overheat_week_open_and_sector(self):
        for hours, allowed in ((23.99, False), (24, True)):
            pos = holding(last_scale_in_at=(NOW - timedelta(hours=hours)).isoformat(), pnl_pct=4)
            self.assertEqual(bot.classify_scale_in(pos, row(), bot.analyze_sectors([row()]),
                                                  state(), NOW, {"label": "risk_on"})["ok"], allowed)
        self.assertFalse(self.buys(self.run_portfolio(state([holding(bought_at=None)]))))
        for r in (row(change_5d=15), row(high_20d_ratio=0.98),
                  row(change_10d=None), row(pct_change=0), row(change_15m=3)):
            with self.subTest(row=r):
                self.assertFalse(self.buys(self.run_portfolio(r=r)))
        monday = datetime(2026, 8, 31, 23, tzinfo=bot.JST)
        self.assertFalse(self.buys(self.run_portfolio(current=monday)))

    def test_no_second_tranche_in_same_run_or_before_24h(self):
        s, _, _ = self.run_portfolio()
        self.assertFalse(self.buys(self.run_portfolio(s)))
        self.assertFalse(self.buys(self.run_portfolio(s, current=NOW + timedelta(hours=23))))

    def test_intermediate_b_partial_once_and_single_share_exit(self):
        for qty in (10, 1):
            s = state([holding("7011.T", qty=qty, peak_price_jpy=1060, peak_pnl_pct=6)])
            result = self.run_portfolio(s, row("7011.T", last_jpy=1007))
            action = result[2][0]
            self.assertEqual(action["action"], "paper_intermediate_take_profit" if qty > 1 else "paper_intermediate_profit_stop")
            self.assertEqual(action["qty"], qty // 2 if qty > 1 else 1)
            self.assertGreater(action["execution_cost_jpy"], 0)
            self.assertFalse(self.buys(result))
            self.assertGreater(bot.ticker_cooldown_remaining_hours(s, "7011.T", NOW), 0)
            if qty > 1:
                self.assertTrue(result[1]["positions"][0]["partial_taken_intermediate"])
                again = self.run_portfolio(s, row("7011.T", last_jpy=1007))
                self.assertEqual(again[2][0]["action"], "hold")

    def test_sa_early_protection_suppressed_and_guard_boundary(self):
        for grade in ("S", "A"):
            for peak, drawdown, triggers in ((6, -5, False), (7.99, -6, False),
                                              (8, -5.99, False), (8, -6, True)):
                p = holding(grade=grade, pnl_pct=1.5, peak_pnl_pct=peak,
                            drawdown_from_peak_pct=drawdown)
                action = bot.decide_sell_action(p, row())
                self.assertEqual(action is not None, triggers)

    def test_v6_sell_priority_and_rebound_exclusion(self):
        cases = [
            (dict(pnl_pct=-8), {}, "paper_stop_loss"),
            (dict(pnl_pct=5, peak_pnl_pct=15, drawdown_from_peak_pct=-7), {}, "paper_trailing_stop"),
            (dict(pnl_pct=0, break_even_stop_jpy=1050), {}, "paper_break_even_stop"),
            (dict(pnl_pct=20), {}, "paper_take_profit"),
            (dict(pnl_pct=3), {"change_15m": -3}, "paper_sell_alert"),
        ]
        for overrides, market, expected in cases:
            with self.subTest(expected=expected):
                p = holding(peak_pnl_pct=8, drawdown_from_peak_pct=-6)
                p.update(overrides)
                self.assertEqual(bot.decide_sell_action(p, row(**market))["action"], expected)
        p = holding(buy_mode="oversold_rebound", pnl_pct=1, peak_pnl_pct=8,
                    drawdown_from_peak_pct=-6)
        self.assertIsNone(bot.decide_sell_action(p, row()))
        self.assertFalse(self.buys(self.run_portfolio(state([p]))))

    def test_same_run_partial_sale_never_scales_in_even_without_cooldown(self):
        p = holding(peak_price_jpy=1120, peak_pnl_pct=12)
        with patch.object(bot, "set_ticker_cooldown"):
            result = self.run_portfolio(state([p]), row(last_jpy=1050))
        self.assertEqual(result[2][0]["action"], "paper_intermediate_take_profit")
        self.assertFalse(self.buys(result))

    def test_sales_independent_of_buy_limits(self):
        s = state([holding()])
        s["reports"] = [{"date": NOW.strftime("%Y-%m-%d"), "decisions": [
            {"action": "paper_buy", "ticker": "NVDA"} for _ in range(3)]}]
        result = self.run_portfolio(s, row(change_15m=-3), regime="risk_off")
        self.assertEqual(result[2][0]["action"], "paper_sell_alert")
        self.assertFalse(result[1]["positions"])

    def test_rebase_survives_reload_and_preserves_partial_flags(self):
        p = holding(peak_price_jpy=1080, peak_pnl_pct=8,
                    partial_taken_intermediate=True, partial_taken_20=True)
        s, portfolio, _ = self.run_portfolio(state([p]))
        scaled = portfolio["positions"][0]
        self.assertEqual(scaled["scale_in_count"], 1)
        expected = (1080 / scaled["buy_price_jpy"] - 1) * 100
        self.assertAlmostEqual(scaled["peak_pnl_pct"], expected)
        s["reports"] = [{"generated_at": (NOW - timedelta(days=1)).isoformat(),
                         "portfolio": {"positions": [holding(current_price_jpy=2000, pnl_pct=100)]}}]
        loaded = bot.migrate_state(json.loads(json.dumps(s)))
        self.assertAlmostEqual(loaded["positions"][0]["peak_pnl_pct"], expected)
        self.assertTrue(loaded["positions"][0]["partial_taken_intermediate"])
        self.assertTrue(loaded["positions"][0]["partial_taken_20"])

    def test_new_holding_does_not_inherit_prior_holding_peak(self):
        s = state()
        s["reports"] = [{"generated_at": (NOW - timedelta(days=10)).isoformat(),
                        "portfolio": {"positions": [holding(current_price_jpy=2000, pnl_pct=100)]}}]
        self.assertEqual(bot.migrate_state(s)["positions"][0]["peak_price_jpy"], 1040)

    def test_all_five_legacy_buy_routes_execute(self):
        cases = [
            ("normal_momentum", row(), 1_000_000),
            ("reentry_recovery", row(pct_change=4), 1_100_000),
            ("rebound_probe", row(pct_change=-5, change_5d=0), 1_000_000),
            ("oversold_rebound", row(pct_change=6, change_5d=-9), 1_000_000),
            ("high_cash_deploy", row(pct_change=2), 1_100_000),
        ]
        for mode, r, peak in cases:
            with self.subTest(mode=mode):
                s = state([])
                s["portfolio_peak_value_jpy"] = peak
                result = self.run_portfolio(s, r)
                self.assertEqual([b["buy_mode"] for b in self.buys(result)], [mode])

    def test_legacy_routes_keep_cooldown_and_rebound_daily_limit(self):
        for r in (row(), row(pct_change=4), row(pct_change=-5),
                  row(pct_change=6, change_5d=-9), row(pct_change=2)):
            s = state([])
            bot.set_sector_cooldown(s, r["sector"], NOW)
            self.assertFalse(self.buys(self.run_portfolio(s, r)))
        s = state([])
        s["reports"] = [{"date": NOW.strftime("%Y-%m-%d"), "decisions": [
            {"action": "paper_buy", "ticker": "ANET", "buy_mode": "oversold_rebound"}]}]
        self.assertFalse(self.buys(self.run_portfolio(s, row(pct_change=6, change_5d=-9))))

    def test_legacy_json_load_and_corrupt_json_fail_closed(self):
        s = state()
        original = copy.deepcopy(s)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reports.json"
            path.write_text(json.dumps(s), encoding="utf-8")
            with patch.object(bot, "DATA_PATH", path):
                loaded = bot.load_state()
                self.assertEqual(loaded["positions"][0]["scale_in_count"], 0)
                self.assertEqual(loaded["cash"], original["cash"])
                self.assertEqual(loaded["reports"], original["reports"])
                path.write_text("broken", encoding="utf-8")
                with self.assertRaises(json.JSONDecodeError):
                    bot.load_state()
                self.assertEqual(path.read_text(), "broken")

    def test_history_is_never_trimmed(self):
        s = state([])
        s["reports"] = [{"date": str(i)} for i in range(300)]
        previous = copy.deepcopy(s["reports"])
        with patch.object(bot, "write_state") as write:
            bot.save_state(s, {"date": "new"})
            write.assert_called_once_with(s)
        self.assertEqual(s["reports"][:-1], previous)
        s["realized_trades"] = [{"old": i} for i in range(250)]
        previous = copy.deepcopy(s["realized_trades"])
        bot.record_realized_trade(s, "NVDA", "NVIDIA", 1, 1040, 1000, "test", NOW, "paper_take_profit", row())
        self.assertEqual(s["realized_trades"][:-1], previous)

    def test_user_or_repository_state_compatibility_read_only(self):
        path = Path(os.environ.get("STATE_FIXTURE", "data/reports.json"))
        if not path.exists():
            self.skipTest("Set STATE_FIXTURE to an existing operational JSON")
        raw = path.read_bytes()
        old = json.loads(raw)
        with patch.object(bot, "DATA_PATH", path):
            loaded = bot.load_state()
        for key in ("cash", "reports", "latest", "realized_trades", "realized_pnl_jpy"):
            self.assertEqual(loaded[key], old[key])
        self.assertEqual([p["qty"] for p in loaded["positions"]], [p["qty"] for p in old["positions"]])
        self.assertEqual([p["scale_in_count"] for p in loaded["positions"]],
                         [p.get("scale_in_count", 0) for p in old["positions"]])
        report = bot.build_report(loaded, old["latest"]["market_data"], old["latest"]["usd_jpy"],
                                  old["latest"]["portfolio"], old["latest"]["decisions"], NOW)
        self.assertIn("Daily Discord Market Report", bot.make_discord_message(report))
        self.assertFalse(report["real_trade"])
        self.assertEqual(path.read_bytes(), raw)

    def test_three_tranches_with_real_regime_and_no_fourth(self):
        s = state([holding(qty=20)])
        for stage, market_price in enumerate((1040, 1100, 1180), 1):
            current = NOW + timedelta(days=stage - 1)
            r = row(last_jpy=market_price, pct_change=2)
            p, decisions = bot.update_paper_portfolio(s, [r], current)
            buys = [d for d in decisions if d["action"] == "paper_buy"]
            self.assertEqual(len(buys), 1)
            self.assertEqual(p["positions"][0]["scale_in_count"], stage)
            self.assertEqual(p["risk_regime"]["label"], "strong_risk_on")
            self.assertLessEqual(buys[0]["amount_jpy"], 1_020_000 * bot.SCALE_IN_RATIOS[stage - 1])
        p, decisions = bot.update_paper_portfolio(s, [row(last_jpy=1180, pct_change=2)],
                                                NOW + timedelta(days=3))
        self.assertFalse([d for d in decisions if d["action"] == "paper_buy"])

    def test_partial_sale_refreshes_exposure_before_other_candidate(self):
        s = state([holding("TSM", qty=100, peak_price_jpy=1120, peak_pnl_pct=12),
                   holding(qty=50)])
        p, decisions = bot.update_paper_portfolio(
            s, [row("TSM", last_jpy=1050), row()], NOW)
        self.assertEqual(next(x for x in p["positions"] if x["ticker"] == "TSM")["market_value_jpy"], 52500)
        self.assertEqual([d["ticker"] for d in decisions if d["action"] == "paper_buy"], ["NVDA"])

    def test_scale_in_preserves_armed_break_even_floor(self):
        p = holding(qty=20, peak_price_jpy=1120, peak_pnl_pct=12, break_even_stop_jpy=1010)
        s, portfolio, _ = self.run_portfolio(state([p]), row(last_jpy=1080))
        self.assertEqual(portfolio["positions"][0]["scale_in_count"], 1)
        self.assertGreaterEqual(portfolio["positions"][0]["break_even_stop_jpy"], 1010)
        self.assertGreaterEqual(bot.migrate_state(s)["positions"][0]["break_even_stop_jpy"], 1010)

    def test_same_run_complete_sale_cannot_rebuy_without_cooldown(self):
        with patch.object(bot, "set_ticker_cooldown"), patch.object(bot, "set_sector_cooldown"):
            result = self.run_portfolio(state([holding(qty=1, peak_price_jpy=1120, peak_pnl_pct=12)]),
                                        row(last_jpy=1050))
        self.assertEqual(result[2][0]["action"], "paper_intermediate_profit_stop")
        self.assertFalse(self.buys(result))

    def test_post_friction_boundary_rejected_even_if_pre_trade_cap_fits(self):
        s = state([holding(qty=115, buy_price_jpy=1000, current_price_jpy=1040)])
        # Set cap to the pre-trade exposure plus this tranche. Friction makes it too high.
        cost = int(int(30000 // 1042.08) * 1042.08)
        cap = (119600 + cost + 1) / 1_000_000
        with patch.dict(bot.GRADE_MAX_POSITION_WEIGHTS, {"S": cap}):
            self.assertFalse(self.buys(self.run_portfolio(s)))

    def test_daily_capacity_shared_between_scale_in_and_new_buy(self):
        s = state()
        s["reports"] = [{"date": NOW.strftime("%Y-%m-%d"), "decisions": [
            {"action": "paper_buy", "ticker": t} for t in ("ANET", "MSFT")]}]
        result = self.run_portfolio(s, [row(), row("TSM", pct_change=1.2)])
        self.assertEqual(len(self.buys(result)), 1)
        self.assertEqual(self.buys(result)[0]["buy_mode"], "scale_in")


if __name__ == "__main__":
    unittest.main()
