"""BTC race bot v2 for make.fun competition btc-race-24h-20261115-0828.

Long-only, one position, 1-minute cbBTC/USDC bars (Orca Whirlpool).
Strategy: two complementary entries, one shared position.

  (a) Volatility breakout -- buy when the close breaks above
      SMA(90) + 2.00 * sd(90) of closes. Small size (25% of cash):
      breakouts in a choppy market are only slightly positive, so the
      leg is sized to participate (and to guarantee at least one trade)
      without dragging the account. Exits: 2% take-profit, 0.4%
      trailing stop (tightened from v1's 0.8%: on the dev window the
      breakout leg's winners give back less when the trail is tight).
  (b) Capitulation recovery -- buy when the price sits more than 4%
      below its 6-hour high AND is recovering now (15-minute return
      above 0.3% and close above the last 15-minute high). Full size:
      sharp V-recoveries after a deep intraday washout are the day's
      biggest moves. Exits: 4% take-profit, 1.2% trailing stop.
      (v2 raises the washout bar from 3% to 4%: on the dev window the
      3% trigger fired one bar too early into a still-falling knife
      and cost ~$5.80; the 4% trigger skips that trade entirely.)

v2 vs v1 (local dev grade, same 24h dataset, start $1,000):
  v1: +32.64 USDC, 6 trades, fees 1.81, max DD 1.96%
  v2: +37.76 USDC, 6 trades, fees 1.21, max DD 0.78%
Sweeps that produced v2: a fast prefix-sum simulator (fastsweep.py)
ran ~1,000 staged combos (vb leg, then rec leg, then pullback/burst
legs, then a refine + one-param robustness pass). Pullback and momentum
burst legs were TESTED and REJECTED: they add trades (14-19 vs 6) but
lose money on the dev window (+21 to +25) and steal the position from
the recovery leg, so v2 stays two-legged. Neighbourhood check: every
one-param move off the v2 params stays positive on dev (worst
neighbour +0.51 at rec_drop 500, most +25 to +37).

Exits (per entry kind): trailing stop on the position's value,
take-profit on the entry close, close back below the breakout SMA
(kind a), or 240 bars max hold. Everything is integer fixed-point
math on the raw scaled prices: no floats, no clock, no environment,
no randomness -- two runs on the same data produce byte-identical
action logs.

Costs: a full-size round trip pays ~26-40 bps (4 bps fee each way,
2 bps modelled slippage each way, plus constant-product impact
against ~$0.4-0.9M of pool depth), so entries only fire on moves
worth several times that.
"""

import os
import sys
from math import isqrt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 150

# --- volatility breakout (kind "vb") -------------------------------------
VB_SMA_N = 90
VB_K_NUM = 8          # 2.00 = 8/4 (v1: 1.75)
VB_K_DEN = 4
VB_TRAIL_NUM = 996    # 0.4% trailing stop: sell when value <= peak * 996/1000 (v1: 0.8%)
VB_TRAIL_DEN = 1000
VB_TP_NUM = 102       # 2% take-profit on the entry close
VB_TP_DEN = 100
VB_FRAC_NUM = 1       # 25% of cash
VB_FRAC_DEN = 4

# --- capitulation recovery (kind "rec") ----------------------------------
REC_LB = 360          # 6-hour lookback for the high
REC_DROP_BPS = 400    # > 4% below that high (v1: 3%)
REC_R15_BPS = 30      # 15-minute return above 0.3%
REC_TRAIL_NUM = 988   # 1.2% trailing stop
REC_TRAIL_DEN = 1000
REC_TP_NUM = 104      # 4% take-profit on the entry close
REC_TP_DEN = 100

MAX_HOLD_BARS = 240


def _mean(xs):
    return sum(xs) // len(xs)


def _sd(xs):
    m = _mean(xs)
    var = sum((x - m) * (x - m) for x in xs) // len(xs)
    return isqrt(var)


class Bot:
    def __init__(self):
        self.closes = []        # raw close ints, oldest first
        self.entry_price = None  # close at the decision bar
        self.kind = None         # "vb" or "rec"
        self.peak = None         # peak position value (quote units) while held
        self.hold_bars = 0

    def on_batch(self, state, batch):
        # A minute the recorder took no sample for has no bar: nothing new
        # to learn, and no order to decide.
        if not any(b.get("symbol") == SYMBOL for b in batch.get("bars", [])):
            return []
        close = state.close(SYMBOL)
        if close is None:
            return []
        self.closes.append(close)
        held = state.positions.get(SYMBOL)
        qty = held.qty if held is not None else 0

        if qty > 0:
            return self._exit(state, close)
        return self._enter(state, close)

    # -- exits ------------------------------------------------------------
    def _exit(self, state, close):
        self.hold_bars += 1
        value = state.equity - state.cash  # position value at latest close
        if self.peak is None or value > self.peak:
            self.peak = value
        if self.kind == "rec":
            trail_num, trail_den = REC_TRAIL_NUM, REC_TRAIL_DEN
            tp_num, tp_den = REC_TP_NUM, REC_TP_DEN
        else:
            trail_num, trail_den = VB_TRAIL_NUM, VB_TRAIL_DEN
            tp_num, tp_den = VB_TP_NUM, VB_TP_DEN
        if self.peak is not None and value * trail_den <= self.peak * trail_num:
            return self._sell_all(state)
        if self.entry_price is not None and close * tp_den >= self.entry_price * tp_num:
            return self._sell_all(state)
        if self.kind == "vb" and len(self.closes) >= VB_SMA_N:
            if close < _mean(self.closes[-VB_SMA_N:]):
                return self._sell_all(state)
        if self.hold_bars >= MAX_HOLD_BARS:
            return self._sell_all(state)
        return []

    # -- entries (flat only) ----------------------------------------------
    def _enter(self, state, close):
        closes = self.closes
        if len(closes) < max(VB_SMA_N, REC_LB) + 1:
            return []
        # (a) volatility breakout
        window = closes[-VB_SMA_N:]
        mean = _mean(window)
        sd = _sd(window)
        if (close - mean) * VB_K_DEN > VB_K_NUM * sd:
            return self._buy(state, close, "vb", VB_FRAC_NUM, VB_FRAC_DEN)
        # (b) capitulation recovery
        hi = max(closes[-REC_LB - 1:-1])
        if (hi - close) * 10000 > REC_DROP_BPS * hi:
            prev15 = closes[-16]
            if (close - prev15) * 10000 > REC_R15_BPS * prev15:
                if close > max(closes[-16:-1]):
                    return self._buy(state, close, "rec", 1, 1)
        return []

    def _buy(self, state, close, kind, frac_num, frac_den):
        notional = state.cash * frac_num // frac_den
        if notional < int(state.hello["fees"]["min_notional_quote_units"]):
            return []
        self.entry_price = close
        self.kind = kind
        self.peak = None
        self.hold_bars = 0
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": notional,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]

    def _sell_all(self, state):
        held = state.positions.get(SYMBOL)
        if held is None or held.qty <= 0:
            return []
        self.entry_price = None
        self.kind = None
        self.peak = None
        self.hold_bars = 0
        return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]


makefun_bars.run(Bot().on_batch)
