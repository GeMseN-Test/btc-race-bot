# BTC Race Bot — make.fun bounty `btc-race-24h-20261115-0828`

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/GeMseN-Test/btc-race-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/GeMseN-Test/btc-race-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

Entry for the [make.fun "Race a BTC trading bot live for 24 hours" bounty](https://make.fun/bounty/btc-race-24h-20261115-0828) ($250 in USDC).

A long-only trading bot for 1-minute cbBTC/USDC bars (Orca Whirlpool),
written for the make.fun "Race a BTC trading bot live for 24 hours"
competition. Python 3.13, standard library only, no network at runtime.

## Run

The entrypoint is `main.py` at the repository root. The grader runs it as:

```sh
python3 -P -s /bot/main.py
```

with `PYTHONHASHSEED=0`. It speaks `agent-fun/bars-replay/v1` on
stdin/stdout (newline-delimited JSON) via the vendored shim in
`vendor/makefun_bars.py` (a byte-for-byte copy of the kit's
`sdk/makefun_bars.py`).

## Strategy (see STRATEGY.md for the full write-up)

Two complementary entries, one shared position:

1. **Volatility breakout** — buy when the close breaks above
   SMA(90) + 1.75·sd(90). Small size (25% of cash): breakouts in a
   choppy market are only slightly positive, so the leg is sized to
   participate (and to guarantee at least one trade) without dragging
   the account.
2. **Capitulation recovery** — buy when the price sits more than 3%
   below its 6-hour high *and* is recovering now (15-minute return
   above 0.3%, close above the last 15-minute high). Full size:
   sharp V-recoveries after a deep intraday washout are the day's
   biggest moves.

Exits per entry kind: trailing stop (0.8% breakout / 1.2% recovery),
take-profit (2% / 4% on the entry close), close back below the
breakout SMA (breakout leg), or 240 bars max hold.

## Dev-window results (local replay, exact fill model)

| | |
|---|---|
| Net PnL | **+32.64 USDC** on $1,000 start |
| Trades | 6 (3 round trips) |
| Fees | 1.81 USDC |
| Max drawdown | 1.96% (guardrail: 25%) |
| Runtime | ~0.2 s for 1,440 bars |

The local grader (`../grader.py`, not part of the entry) mirrors the
kit's fill model in exact integer arithmetic (fee 4 bps, slippage
2 bps, constant-product impact against each bar's open depth,
1-bar fill latency, final liquidation at the last close). It was
cross-checked against the kit's own `grade-local --driver process`:
buy-and-hold reproduces the official score exactly
(-44.009846 USDC), and EMA-cross matches to 0.2 USDC over 63 trades.

## Robustness

The dev window is one choppy -4% day, so the parameters were picked
for a plateau, not a peak: all 48 nearby parameter combinations
(volatility k 1.5–2.0, drop threshold 300–350 bps, recovery
take-profit 3.5–4.5%, breakout size 25–50%) end positive on the dev
window (+14.38 to +37.18 USDC). Sub-window checks (three 6-hour
slices) give -0.70 / +16.67 / +1.40 USDC, and the time-reversed
(uptrend) window gives +7.22 USDC. See STRATEGY.md.

## Determinism

All indicator math is integer fixed-point on the raw scaled prices:
no floats, no wall clock, no environment reads, no randomness. Two
runs produce byte-identical action logs (verified).

## Layout

```
main.py                  entrypoint
vendor/makefun_bars.py   kit SDK shim, byte-for-byte (excluded from authorship)
LICENSE                  MIT
README.md                this file
STRATEGY.md              strategy write-up
```
