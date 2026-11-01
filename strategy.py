"""
YOUR STRATEGY. This is the only file you need to edit to change what the scanner looks for.
Read STRATEGY_GUIDE.md for the full explanation. Ready-made alternatives are in the examples/ folder:
copy one over this file to switch.

Default strategy: EMA Trend Pullback
  Trade in the direction of the trend, buy the pullback to the moving average, enter when the bounce is confirmed.
  Swing     daily trend + pullback to the 20 EMA, entry when the 1H closes back above its 20 EMA.
  Intraday  15m trend + 5m pullback to the EMAs, entry on a close above the previous candle high (long and short).
  Options   the same idea on the Nifty 50 index, with Supertrend instead of VWAP (the index has no volume).

How a rule function works (more in STRATEGY_GUIDE.md):
  c.require(name, ok, why)               must pass, otherwise the stock is skipped
  c.check(name, ok, weight, group, why)  scored: the score out of 10 is the weight of the rules that pass
  return c.setup(status, entry, stop, targets, ...)   status is TRIGGERED, WATCH or NEAR
Write LONG rules only: for shorts the engine flips the chart upside down and runs the same rules.
"""
from indicators import *
from strategy_api import TRIGGERED, WATCH, NEAR

NAME = 'EMA Trend Pullback'
DESCRIPTION = 'Trade with the trend: wait for a pullback to the moving average, enter when the bounce is confirmed.'

# ------------------------------------------------------------------ what to scan
# main     the timeframe the rules read (c.df).       swing: '1d'.  options and intraday: '5m' or '15m'
# trigger  swing only, the entry timeframe (c.trigger): '1h' or None
# bias     options/intraday only, the higher timeframe (c.bias): '15m', '1h' or None
# sides    which directions to look for. Swing is long only by default (no overnight shorts in the cash market).
SECTIONS = {
    'swing':    dict(enabled=True, sides=['long'], main='1d', trigger='1h', sector_filter=True,
                     summary='Nifty 500 · daily uptrend, pullback to the 20 EMA, 1H bounce · long only · updates every hour'),
    'options':  dict(enabled=True, sides=['long', 'short'], main='5m', bias='15m',
                     summary='Nifty 50 index · 15m trend, 5m pullback and breakout · calls and puts · updates every 5 minutes'),
    'intraday': dict(enabled=True, sides=['long', 'short'], main='5m', bias='15m',
                     summary='Most liquid Nifty 500 stocks · 15m trend, 5m pullback and breakout with volume · long and short · every 5 minutes'),
}

# Which stocks qualify at all (applied before your rules). Turnover is the 20-day average in crores of rupees.
UNIVERSE = dict(min_price=50, min_turnover_cr=20, skip_locked_circuit=True, intraday_top=100)

# Score out of 10 -> grade. Setups under the lowest grade are dropped.
GRADES = {'A+': 8, 'A': 6, 'B': 4}

# Every number your rules use, in one place. c.settings inside a rule is the block for its section.
SETTINGS = {
    'swing': dict(fast=20, slow=50, pullback_atr=0.3, max_extension_atr=1.5, rsi_low=35, rsi_high=60, trigger_bars=3,
                  volume_x=1.3, stop_lookback=5, stop_buffer_atr=0.25, target_lookback=20, near_high_pct=15),
    'intraday': dict(fast=9, slow=20, bias_ema=20, pullback_bars=4, pullback_atr=0.2, max_extension_atr=1.5, volume_x=1.5,
                     stop_buffer_atr=0.2, skip_first_minutes=15, last_entry='14:45'),
    'options': dict(fast=9, slow=20, bias_ema=20, pullback_bars=4, pullback_atr=0.2, max_extension_atr=1.5,
                    stop_buffer_atr=0.2, skip_first_minutes=15, last_entry='14:30'),
}

# Your risk rules: shown on every trade page under "How to trail".
RULES = {
    'swing': ['Never widen the stop.', 'Risk the same rupee amount on every trade (the page sizes it for you).', 'Exit or cut size before results.'],
    'intraday': ['Never widen the stop.', 'Stop for the day after two losses.', 'Square off by 15:10.'],
    'options': ['Never widen the stop and never average down an option.', 'Expiry day: no new buys after lunch.', 'Stop for the day after two losses.'],
}


# ================================================================== SWING (daily rules, 1H trigger)
def swing(c):
    s = c.settings; df = c.df; close = df.Close
    fast, slow = ema(close, s['fast']), ema(close, s['slow']); a = last(atr(df, 14)); px = last(close)

    # Trend
    c.require('Uptrend', px > last(slow) and last(fast) > last(slow),
              f"price above the {s['slow']} EMA and the {s['fast']} EMA above the {s['slow']} EMA", group='Trend', weight=2)
    c.check(f"{s['slow']} EMA rising", rising(slow, 10), 1, 'Trend', f"the {s['slow']} EMA is higher than 10 days ago")

    # Setup: a pullback to the fast EMA that held above the slow one
    ext = (px - last(fast)) / a
    if ext > s['max_extension_atr']: c.skip(f"Extended: price is {ext:.1f} ATR above the {s['fast']} EMA, wait for a pullback")
    pull_low = last(lowest(df.Low, 3))
    if pull_low < last(slow) - 0.5 * a: c.skip(f"The pullback broke below the {s['slow']} EMA")
    touched = pull_low <= last(fast) + s['pullback_atr'] * a
    c.check(f"Pullback to the {s['fast']} EMA", touched, 2, 'Setup', f"a low in the last 3 days came within {s['pullback_atr']} ATR of the {s['fast']} EMA")
    r_min = last(lowest(rsi(close, 14), 5))
    c.check('RSI cooled off', s['rsi_low'] <= r_min <= s['rsi_high'], 1, 'Setup', f"RSI dipped to {r_min:.0f} (wanted {s['rsi_low']} to {s['rsi_high']}): a pause, not a breakdown")

    # Trigger on the 1H chart (c.trigger is None on the first pass, so these simply fail there)
    t = c.trigger; bounce, rv = False, float('nan')
    if t is not None and len(t) >= 30:
        tf = ema(t.Close, s['fast'])
        bounce = crossed_above(t.Close, tf, within=s['trigger_bars']) and last(t.Close) > last(tf)
        rv = relative_volume(t, 20, same_time=True)
    c.check(f"1H close back above the {s['fast']} EMA", bounce, 2, 'Trigger', f"within the last {s['trigger_bars']} hourly candles")
    c.check(f"Volume {s['volume_x']}x normal", bounce and rv >= s['volume_x'], 1, 'Trigger',
            f"trigger candle volume {rv:.1f}x the same hour on earlier days" if rv == rv else 'no trigger candle yet')

    # Context
    w = weekly(df)
    c.check('Weekly trend up', len(w) >= 12 and last(w.Close) > last(ema(w.Close, 10)), 1, 'Context', 'weekly close above the 10-week EMA')
    if c.nifty is not None and len(c.nifty) > 60:
        c.check('Nifty above its 50 EMA', last(c.nifty.Close) > last(ema(c.nifty.Close, 50)), 1, 'Context', 'the broad market is not working against you')
    hi, now = c.real(df.High.tail(250).max()), c.real(px)
    away = abs(hi - now) / now * 100
    c.check(f"Within {s['near_high_pct']}% of the 52-week high", away <= s['near_high_pct'], 1, 'Context', f'{away:.1f}% below the 52-week high: leaders pull back and go on')
    rs, ni = c.pct_change(20), c.nifty_pct_change(20)
    c.check('Stronger than Nifty (20 days)', rs is not None and ni is not None and rs > ni, 1, 'Context',
            f'{rs:+.1f}% vs Nifty {ni:+.1f}% over 20 days' if rs is not None and ni is not None else 'not enough data')

    # Levels
    status = TRIGGERED if touched and bounce else WATCH if touched else NEAR
    note = {TRIGGERED: '', WATCH: 'waiting for the 1H bounce', NEAR: f"alert at the {s['fast']} EMA"}[status]
    entry = last(t.Close) if status == TRIGGERED else last(fast)
    low = last(lowest(df.Low, s['stop_lookback']))
    if status == TRIGGERED: low = min(low, float(t.Low.tail(10).min()))
    stop = min(low, entry - 0.5 * a) - s['stop_buffer_atr'] * a
    risk = entry - stop; t1 = last(highest(df.High, s['target_lookback']))
    if t1 < entry + risk: t1 = entry + 1.5 * risk
    return c.setup(status, entry, stop, [t1], note=note,
                   zone=(last(fast) - s['pullback_atr'] * a, last(fast) + s['pullback_atr'] * a),
                   lines={f"{s['fast']} EMA": fast, f"{s['slow']} EMA": slow},
                   stop_why=f"Below the lowest low of the last {s['stop_lookback']} days with a {s['stop_buffer_atr']} ATR buffer: if it breaks, the pullback has turned into a reversal.",
                   target_why=f"T1 is the highest high of the last {s['target_lookback']} days (at least 1.5R). T2 and T3 are 2R and 3R.")


# ================================================================== INTRADAY and OPTIONS (5m rules, 15m bias)
def _minutes(hhmm):
    h, m = (int(x) for x in hhmm.split(':')); return h * 60 + m - (9 * 60 + 15)

def _intraday_rules(c, use_volume):
    s = c.settings; df = c.df; close = df.Close; a = last(atr(df, 14)); px = last(close)
    m = c.minutes_into_session()
    if m < s['skip_first_minutes']: c.skip(f"Too early: the first {s['skip_first_minutes']} minutes are skipped")
    if m > _minutes(s['last_entry']): c.skip(f"No new entries after {s['last_entry']}")

    # Bias and trend
    b = c.bias
    if b is not None and len(b) >= 30:
        be = ema(b.Close, s['bias_ema'])
        c.require('15m trend', last(b.Close) > last(be) and rising(be, 3), f"15m close above a rising {s['bias_ema']} EMA", group='Bias', weight=2)
    fast, slow = ema(close, s['fast']), ema(close, s['slow'])
    c.require('5m trend', last(fast) > last(slow) and px > last(slow), f"{s['fast']} EMA above the {s['slow']} EMA, price above both", group='Trend', weight=1)
    if use_volume:
        c.check('Price above VWAP', px > last(vwap(df)), 1, 'Trend', 'buyers are in control of the session')
    else:
        c.check('Supertrend agrees', last(supertrend(df, 10, 3.0)[1]) > 0, 1, 'Trend', 'Supertrend (10, 3) points the same way')

    # Setup: a pullback into the EMAs
    ext = (px - last(fast)) / a
    if ext > s['max_extension_atr']: c.skip(f"Extended: {ext:.1f} ATR from the {s['fast']} EMA, wait for a pullback")
    pull_low = last(lowest(df.Low, s['pullback_bars']))
    touched = pull_low <= last(fast) + s['pullback_atr'] * a
    c.check('Pullback to the EMAs', touched, 2, 'Setup', f"a low in the last {s['pullback_bars']} candles came back to the {s['fast']} EMA")

    # Trigger
    breakout = px > float(df.High.iloc[-2]) and close_position(df) >= 0.5
    c.check('Close above the previous candle high', breakout, 2, 'Trigger', 'the pullback is over')
    c.check('RSI above 50', last(rsi(close, 14)) > 50, 1, 'Trigger', 'momentum is on your side')
    if use_volume:
        rv = relative_volume(df, 20)
        c.check(f"Volume {s['volume_x']}x normal", rv >= s['volume_x'], 1, 'Trigger', f'{rv:.1f}x the last 20 candles' if rv == rv else 'no volume data')

    # Context
    pdl = c.prev_day()
    if pdl: c.check('Above the previous day high', px > pdl['high'], 1, 'Context', 'no level from yesterday in the way')
    orr = c.opening_range(15)
    if orr: c.check('Above the opening range high', px > orr['high'], 1, 'Context', 'outside the first 15-minute range')

    # Levels
    status = TRIGGERED if touched and breakout else WATCH if touched else NEAR
    note = {TRIGGERED: '', WATCH: 'waiting for the breakout candle', NEAR: 'waiting for a pullback'}[status]
    entry = px if status == TRIGGERED else last(fast)
    stop = min(pull_low, entry - 0.3 * a) - s['stop_buffer_atr'] * a
    risk = entry - stop; t1 = float(c.today().High.max())
    if t1 < entry + risk: t1 = entry + 1.5 * risk
    return c.setup(status, entry, stop, [t1], note=note, zone=(last(slow), last(fast) + s['pullback_atr'] * a),
                   lines={f"{s['fast']} EMA": fast, f"{s['slow']} EMA": slow},
                   stop_why=f"Beyond the pullback extreme of the last {s['pullback_bars']} candles with a {s['stop_buffer_atr']} ATR buffer.",
                   target_why="T1 is today's extreme in the trade direction (at least 1.5R). T2 and T3 are 2R and 3R.")


def intraday(c):
    return _intraday_rules(c, use_volume=c.has_volume)


def options(c):
    return _intraday_rules(c, use_volume=False)      # the Nifty index has no volume feed
