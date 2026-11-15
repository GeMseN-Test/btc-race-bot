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

## Final design

One position, long only, $1,000 paper start.

**Entry A — volatility breakout (25% of cash).**
Buy when the close breaks above SMA(90) + 1.75·sd(90) of closes.
Small size: breakouts in chop are only slightly positive, so this
leg exists to participate and to guarantee at least one trade on a
quiet race day, not to carry the PnL.

**Entry B — capitulation recovery (100% of cash).**
Buy when the price is more than 3% below its 6-hour high AND is
recovering right now: 15-minute return above 0.3% and close above
the last 15-minute high. Full size: a genuine V-recovery after a
deep washout is the largest move the day offers.

**Exits (per entry kind).** Trailing stop on the position's value
(0.8% for A, 1.2% for B), take-profit on the entry close (2% for A,
4% for B), close back below the breakout SMA (A only), or 240 bars
max hold. No exit is based on a prediction of the next bar — only
on the position's own mark.

**Costs are part of the design.** Breakout trades are kept small
because impact is proportional to size; the recovery trade is full
size because its expected move (several percent) dwarfs the ~40 bps
round-trip cost. `max_slippage_bps` is 150 on every order: wide
enough for normal 1-minute gaps (stdev 12 bps), tight enough to
refuse chasing a fill far above the close the decision was made on.

## Results

Dev window, local replay with the kit's exact fill model:

- Net PnL **+32.64 USDC** (3 round trips: -0.70, -5.53, +38.87;
  the last is the recovery trade, bought near the day's low and
  sold at its +4% take-profit)
- 6 trades, 1.81 USDC fees, max drawdown 1.96% (limit 25%)
- Runtime ~0.2 s for 1,440 bars

## Robustness (why these parameters, not the peak)

The dev window is a single choppy day, so the parameters sit in the
middle of a plateau, not on a spike:

- All 48 nearby combinations (k 1.5–2.0, drop 300–350 bps,
  recovery take-profit 3.5–4.5%, breakout size 25–50%) are
  positive: +14.38 to +37.18 USDC.
- Three 6-hour sub-windows: -0.70 / +16.67 / +1.40 USDC — no
  catastrophic block.
- Time-reversed window (an uptrend day): +7.22 USDC over 22 trades
  (buy-and-hold makes +37.21 there; this bot deliberately trades
  selectivity for downside protection).

Known limits, stated plainly:

- The recovery leg fired twice on the dev window; on a race day
  with no 3% washout it may not fire at all, and the bot then ends
  near breakeven on a few small breakout trades.
- The 300 bps drop threshold has a cliff just below it (250 bps
  loses on the dev window), so the threshold is a real modelling
  choice: deep washouts bounce, shallow dips keep sliding.
- On a strong straight-up race day this bot underperforms
  buy-and-hold; it is built to survive down/choppy days and to
  catch the washout bounce, not to ride a trend.

## Implementation notes

- Integer fixed-point math on raw scaled prices only (SMA by
  truncated mean, sd by integer square root). No floats, no clock,
  no environment, no randomness: two runs give byte-identical
  action logs (verified).
- `vendor/makefun_bars.py` is the kit's Python SDK shim, copied
  byte-for-byte; the strategy itself lives in `main.py`.
