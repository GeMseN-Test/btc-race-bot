# STRATEGY.md — BTC race bot

## The market

One asset, cbBTC/USDC, 1-minute bars from the Orca Whirlpool pool.
The dev window (24h, 1,440 bars) fell 4.01% with 12 bps of 1-minute
noise (stdev). A full-size round trip costs about 26–40 bps: 4 bps
fee each way, 2 bps modelled slippage each way, plus
constant-product impact against $0.4–0.9M of pool depth (about
15 bps each way at full $1,000 size, ~8 bps at $500, ~4 bps at
$250). So a trade must catch a move several times that, and
1-minute momentum is pure noise (lag-1 autocorrelation ≈ -0.02).

## What was tried (all graded on the dev window, exact fill model)

| Strategy | Best dev PnL | Verdict |
|---|---|---|
| Buy-and-hold | -44.01 USDC | Day fell 4%; holding loses |
| EMA-cross 8/21 (house-like) | -135.17 USDC, 63 trades | Whipsawed to death |
| RSI + Bollinger mean reversion | -79.48 USDC, 30 trades | Buys dips in a downtrend |
| Donchian breakout | +0.05 USDC | Breakeven |
| EMA trend-follow | +1.22 USDC | Breakeven |
| Mean-reversion bounce | -9.73 USDC | Loses in a trend |
| 15-min momentum burst | -6.90 USDC | 1-bar latency kills it |
| Volatility breakout (SMA90 + 1.75σ) | +7.29 USDC, 3 round trips | Small but real |
| Capitulation recovery (drop >3% + bounce) | +21.59 to +39.10 USDC, 1–2 round trips | Big but concentrated |

The day's money was in one place: a sharp V-recovery (+2.8% in an
hour) after a 3.5% intraday washout. Everything else is noise
trading. The final bot therefore pairs the two patterns that
individually made money, and sizes them by conviction.

## v2 (current entry) — what changed from v1

v1 (submitted first, server dev grade +32.64 USDC, PASS) used:
breakout k=1.75 with a 0.8% trail, recovery drop >3%. v2 retunes
both legs from a staged sweep (~1,000 combos on a fast prefix-sum
simulator that reproduces the exact grader to the cent):

- **Recovery drop 3% → 4% (400 bps).** On the dev window the 3%
  trigger fired one bar too early into a still-falling knife
  (hour 16, -5.76 USDC block); the 4% trigger skips that trade
  entirely. The 350–450 bps plateau is flat (+37.52 for all of
  them), so 400 sits mid-plateau, not on a spike.
- **Breakout k 1.75 → 2.00, trail 0.8% → 0.4%.** Tighter trail
  keeps more of the breakout leg's winners; k=2.00 is the peak of
  a smooth curve (1.75: +36.05, 2.00: +37.76, 2.25: +37.52).
- **Pullback and momentum-burst legs: TESTED and REJECTED.** They
  add trades (14–19 vs 6) but lose money on the dev window
  (+21 to +25 USDC) and steal the single position from the
  recovery leg, so v2 stays two-legged.

## Final design (v2)

One position, long only, $1,000 paper start.

**Entry A — volatility breakout (25% of cash).**
Buy when the close breaks above SMA(90) + 2.00·sd(90) of closes.
Small size: breakouts in chop are only slightly positive, so this
leg exists to participate and to guarantee at least one trade on a
quiet race day, not to carry the PnL.

**Entry B — capitulation recovery (100% of cash).**
Buy when the price is more than 4% below its 6-hour high AND is
recovering right now: 15-minute return above 0.3% and close above
the last 15-minute high. Full size: a genuine V-recovery after a
deep washout is the largest move the day offers.

**Exits (per entry kind).** Trailing stop on the position's value
(0.4% for A, 1.2% for B), take-profit on the entry close (2% for A,
4% for B), close back below the breakout SMA (A only), or 240 bars
max hold. No exit is based on a prediction of the next bar — only
on the position's own mark.

**Costs are part of the design.** Breakout trades are kept small
because impact is proportional to size; the recovery trade is full
size because its expected move (several percent) dwarfs the ~40 bps
round-trip cost. `max_slippage_bps` is 150 on every order: wide
enough for normal 1-minute gaps (stdev 12 bps), tight enough to
refuse chasing a fill far above the close the decision was made on.

## Results (v2)

Dev window, local replay with the kit's exact fill model (verified
through the real wire protocol, subprocess + `--twice`):

- Net PnL **+37.76 USDC** (hourly blocks: +24.37 and +14.68 from
  the recovery trade, +0.13 and -1.42 from breakout trades)
- 6 trades, 1.21 USDC fees, max drawdown 0.78% (limit 25%)
- Runtime ~1 s for 1,440 bars (subprocess incl. startup)
- Determinism: two runs give byte-identical action logs (verified)

v1 for comparison: +32.64 USDC, 6 trades, 1.81 fees, max DD 1.96%.
v2 is +5.12 USDC (+15.7%) with lower fees and lower drawdown.

## Robustness (why these parameters, not the peak)

The dev window is a single choppy day, so the parameters sit in the
middle of a plateau, not on a spike. One-param moves off the v2
params, all still positive on dev:

- Recovery drop: 300 → +26.51, 350/400/450 → +37.52, 500 → +0.51
- Recovery take-profit: 3% → +25.70, 4% → +37.52, 6%/8% → +30.96
- Recovery trail: 0.4% → +15.73, 0.6%/1.2%/2.0% → +37.52
- Breakout k: 1.5 → +31.26, 1.75 → +36.05, 2.0 → +37.76,
  2.25 → +37.52, 2.75 → +37.06
- Max hold: 60 → +28.65, 120/240/360 → +37.52
- v1's neighbourhood (48 combos) was +14.38 to +37.18 USDC.

Known limits, stated plainly:

- The recovery leg fired once on the dev window; on a race day
  with no 4% washout it may not fire at all, and the bot then ends
  near breakeven on a few small breakout trades.
- The 400 bps drop threshold has a cliff just above it (500 bps
  barely fires, +0.51), so the threshold is a real modelling
  choice: deep washouts bounce, shallow dips keep sliding.
- On a strong straight-up race day this bot underperforms
  buy-and-hold; it is built to survive down/choppy days and to
  catch the washout bounce, not to ride a trend.
- v2's edge on dev comes from avoiding one bad trade and riding
  one good one; that is a thin margin and the race day is unseen
  data. The honest expectation is a small positive edge with high
  variance, not a guaranteed profit.

## Implementation notes

- Integer fixed-point math on raw scaled prices only (SMA by
  truncated mean, sd by integer square root). No floats, no clock,
  no environment, no randomness: two runs give byte-identical
  action logs (verified).
- `vendor/makefun_bars.py` is the kit's Python SDK shim, copied
  byte-for-byte; the strategy itself lives in `main.py`.
- Sweep tooling (`grader.py`, `strategies.py`, `sweep.py`,
  `fastsweep.py`) lives outside the repo; only `main.py`,
  `vendor/makefun_bars.py`, `LICENSE`, `README.md`, `STRATEGY.md`
  and `.makefun/owner.json` are submitted.
