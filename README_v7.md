# v7: scale-in and intermediate profit protection

Strategy version: `v7_scale_in_profit_guard`. Paper trading only.

## Flow and compatibility

The v6 flow is retained: refresh positions, execute exits, then rank buy candidates.
The state retains cash, positions, reports/latest, realized trades/P&L, portfolio peak,
trade/report slots and ticker/sector cooldowns. Discord formatting, Pages, dependencies,
and the scheduled workflow are unchanged. No operational JSON is included in this change.

## Scale-in

Held S/A winners can compete with new entries in the existing candidate ranking,
including when all five holding slots are occupied. The five-name limit still applies
to new names. Scale-in is excluded for dedicated oversold-rebound holdings.

| Stage | Maximum allocation / current equity | Minimum unrealized P/L | Regime |
| --- | --- | --- | --- |
| 1 | 3% | 2% | risk_on / strong_risk_on |
| 2 | 3% | 4% | risk_on / strong_risk_on |
| 3 | 4% | 6% | strong_risk_on only |

Wait at least 24 hours after the initial buy and between additions. Missing purchase
timestamps block additions. Three additions maximum per holding; partial sales do not
reset the counter. The stage thresholds use the current average cost, including friction.

The sector must be strong. Ticker/sector cooldowns, week-open blocks, short-term and
sector overheating, and normal daily/intraday momentum bounds all apply. Missing
short-term metrics block additions. There is no sector cooldown exception for scale-in.

The shared buy loop applies the daily total 3 / bucket 2 / rebound 1 limits. Scale-in
is recorded as `paper_buy` with `buy_mode=scale_in`, so existing report-based daily
counting includes it. A sale of any quantity blocks that ticker for the whole run.
Partial-sale cooldowns are set immediately (12h); intermediate full exits use 24h.
All existing v6 sell cooldown durations are retained.

The S/A 15% holding cap, bucket caps, regime cash floors and execution friction remain.
Scale-in caps additionally use post-friction equity. Sizing may shrink to available
cash/holding headroom; a bucket or post-friction cap violation skips the candidate.
No fractional shares or forced one-share exceptions are added. Consequently, a high
share price or the other guards can still leave substantial cash uninvested.

## Loss-exit recovery confirmation (2026-09-14)

Before any of the five fresh-entry buy modes, the latest sale of that ticker is read
from `realized_trades`, ordered by `sold_at`. When that sale is `paper_stop_loss`,
`paper_rebound_stop_loss`, or `paper_sell_alert`, both the unchanged time cooldown
and the following extra conditions must pass. This supplements the existing route
rules; it does not create a new buy route or guarantee execution.

| Grade / regime | Recovery from sell market price | Sector | Extra sizing factor |
| --- | --- | --- | --- |
| S/A (R rebound route also uses this baseline) | >= 3% | neutral / strong | 1.0 |
| B, risk_on / strong_risk_on | >= 5% | strong only | 1.0 |
| B, neutral | >= 6% | strong only | 0.5 |
| B, cautious / risk_off | prohibited | — | — |

Both `change_5d` and `change_15m` must be strictly positive and finite. Sector data
must be present. Short-term overheat inputs must be present, and existing short-term
overheat, sector overheat and week-open blocks must pass. No sector cooldown exception
is allowed for these loss reentries. Other regime restrictions, sizing, daily limits,
cash floors, concentration limits and execution friction remain in the shared loop.
The B neutral factor multiplies the existing regime-adjusted allocation, not equity.

Thresholds are `REENTRY_RECOVERY_MIN_PCT`, `B_REENTRY_RECOVERY_MIN_PCT`,
`B_NEUTRAL_REENTRY_RECOVERY_MIN_PCT`, and `B_NEUTRAL_REENTRY_ALLOCATION_MULTIPLIER`.
Their values are included in each new report's `risk_rules`. They are conservative
initial choices, not fitted to recent losses; profitability has not been established.

No duplicate `last_exit_info` or root state key is added. Existing realized trades
already retain timestamp, action, gross market price, friction-adjusted fill and P/L.
If market price is absent, it is reconstructed only from a valid fill and recorded
friction; a net fill is never silently used as market price. A known risky exit with
missing price/time blocks that ticker rather than guessing. Legacy missing actions
use the existing reason inference; an otherwise unidentified negative realized trade
is conservatively treated as a normal stop loss. Naive historical dates are interpreted
as JST by this helper. Missing history means no additional gate. A later profit exit
supersedes an earlier loss exit; adding to a current holding continues through the
unchanged scale-in rules. Existing JSON/history is neither rewritten nor reset.

## Scale-in diagnostics

New trade-evaluation reports contain `portfolio.scale_in_diagnostics`:

```json
{
  "candidate_count": 4,
  "executed_count": 0,
  "blocked_counts": {"sector_not_strong": 2, "pnl_below_threshold": 1, "minimum_cash": 1},
  "by_ticker": {"NVDA": "sector_not_strong", "ANET": "sector_not_strong",
                "ETN": "pnl_below_threshold", "VRT": "minimum_cash"}
}
```

This counts **all holdings at the start of the run**, including B/R and holdings sold
during that run, not just eligible S/A candidates. Each ticker has exactly one first
blocking reason or `executed`. Consequently, blocked counts plus executions equal
candidate count; these are not counts of all simultaneously failing conditions.
Newly opened positions do not enter this denominator. Missing market rows are counted
as `market_data_missing`; same-run sales as `same_run_sale`. After daily capacity is
exhausted, remaining holdings receive `daily_buy_limit` without executing any buys.

Other reason codes: `grade`, `risk_regime`, `stage_limit`, `rebound_holding`,
`pnl_below_threshold`, `third_stage_regime`, `interval_or_timestamp`,
`sector_not_strong`, `ticker_cooldown`, `sector_cooldown`, `overheat_or_week_open`,
`daily_momentum`, `intraday_momentum`, `daily_bucket_limit`, `execution_price_missing`,
`minimum_cash`, `position_weight_limit`, `bucket_weight_limit`, `tranche_below_one_share`.
The last reason distinguishes whole-share rounding from insufficient cash or holding
headroom. Sizing, including the existing 3%/3%/4% tranches, is unchanged.

Details persist through the existing reports/latest path. Monitor-only snapshots and
old reports omit the diagnostics: absence means **not evaluated/unknown**, not zero
executions. Discord output remains unchanged in length; use the JSON for aggregation.
PR #5's proposed single-share exception is not included in this change.

Verification for this enhancement: `python scripts/check_dev.py` passes 108 tests
(96 existing, 12 added, with additional boundary subcases), including Python 3.11
syntax validation and protected-file hashes. Tests cover cooldown plus price recovery,
B regime/sector/sizing, all five fresh-buy routes, legacy/real sale records, diagnostic
persistence, shared execution guards, and unchanged intermediate protection.
Local runtime: Python 3.12 on Windows; CI results are tracked separately in the PR.

## Intermediate protection (unchanged)

| Grade | Peak P/L activation | Drawdown from peak price |
| --- | --- | --- |
| B | 6% | -5% |
| S/A | 8% | -6% |

Existing rebound exits, acute alerts, stop losses, +15% trailing, +10% break-even
protection and +20% partial profit-taking retain their existing order and take
priority. Intermediate protection is checked afterward; R and dedicated oversold
rebound holdings are excluded.

With at least two shares, sell floor(qty/2) once per holding. With one share, exit
fully. The remaining shares retain existing v6 exits; intermediate partial protection
does not repeat. A gap below cost can produce a loss despite the protection label.

Scale-in merges friction-adjusted cash cost into the average acquisition price,
retains peak price, recalculates peak P/L on that basis, and preserves any already
armed absolute break-even floor. Partial-profit flags are never rearmed by additions.
After cost averaging, percentage-based activation thresholds use the new cost basis.

## State safety

Missing `scale_in_count`, `last_scale_in_at`, and `partial_taken_intermediate`
default to 0, null and false. `peak_basis_at` marks an addition, preventing reload
from importing pre-addition P/L. Peak inference also excludes reports before the
current holding's purchase.

Existing malformed JSON now raises instead of silently creating a new portfolio.
Report and realized-trade count trimming is removed to retain all existing and future
history. JSON size and loading time will grow; archival needs a separate explicit
design. No history is rewritten or reset as part of deployment.

## Offline verification

Install the existing requirements, then run from the repository root:

```sh
python -m py_compile market_discord_bot.py tests/test_strategy_v7.py
python -m unittest discover -s tests -v
```

Tests block network/Discord/state writes except isolated temporary JSON handling.
The compatibility test reads `data/reports.json`, or a path supplied through the
`STATE_FIXTURE` environment variable, without modifying it.

Validated locally: 29 tests, Python 3.12; Python 3.11 grammar check also passed.
The Actions Python 3.11 runtime was not executed. No live workflow or Bot main was run.

The supplied 2026-08-28 10:06:51 JST JSON matched both repository JSON blobs exactly
(`d0abadc4a2d6718cba3a41169d870d2b2208eb72`). A read-only in-memory replay
produced a 21-share intermediate partial sale of 7012.T (119 JPY realized profit,
83 JPY friction), with no scale-in. This is a fixture result, not a live trade or
an expected return. Strategy profitability and drawdown improvements are unproven;
observe paper results after manual review/merge. Do not reset the state or run the
production workflow merely to test this PR.
