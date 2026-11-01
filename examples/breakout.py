"""
Example strategy: Breakouts. To use it, copy this whole file over strategy.py (or set the repo variable STRATEGY_FILE
to examples/breakout.py).

  Swing     a close above the 20-day high out of a tight base, with volume. Daily only (no 1H trigger).
  Intraday  opening-range breakout: a close beyond the first 15 minutes' range, with volume and VWAP on side.
  Options   the same opening-range breakout on the Nifty 50 index, with Supertrend instead of volume.
Write long rules only: shorts are found automatically by flipping the chart.
"""
from indicators import *
from strategy_api import TRIGGERED, WATCH, NEAR

NAME = 'Breakouts'
DESCRIPTION = 'Buy strength: a close beyond a well-defined range (20-day high or the opening range) with volume.'

SECTIONS = {
    'swing':    dict(enabled=True, sides=['long'], main='1d', trigger=None, sector_filter=True,
                     summary='Nifty 500 · close above the 20-day high out of a tight base, with volume · long only · updates every hour'),
    'options':  dict(enabled=True, sides=['long', 'short'], main='5m', bias='15m',
                     summary='Nifty 50 index · 15-minute opening-range breakout · calls and puts · updates every 5 minutes'),
    'intraday': dict(enabled=True, sides=['long', 'short'], main='5m', bias='15m',
                     summary='Most liquid Nifty 500 stocks · opening-range breakout with volume and VWAP · long and short · every 5 minutes'),
}
UNIVERSE = dict(min_price=50, min_turnover_cr=20, skip_locked_circuit=True, intraday_top=100)
GRADES = {'A+': 8, 'A': 6, 'B': 4}
SETTINGS = {
    'swing': dict(lookback=20, near_pct=3.0, volume_x=1.5, base_atr_ratio=0.9, stop_atr=1.0, fresh_bars=3),
    'intraday': dict(range_minutes=15, near_atr=0.5, volume_x=1.5, max_range_atr=3.0, last_entry='13:30', fresh_bars=2),
    'options': dict(range_minutes=15, near_atr=0.5, max_range_atr=3.0, last_entry='13:00', fresh_bars=2),
}
RULES = {
    'swing': ['Never widen the stop.', 'A breakout that closes back inside the base is a failed breakout: exit.', 'Exit or cut size before results.'],
    'intraday': ['Never widen the stop.', 'One breakout trade per stock per day.', 'Square off by 15:10.'],
    'options': ['Never average down an option.', 'Expiry day: no new buys after lunch.', 'Stop for the day after two losses.'],
}


def swing(c):
    s = c.settings; df = c.df; close = df.Close; a = last(atr(df, 14)); px = last(close)
    c.require('Above the 50 EMA', px > last(ema(close, 50)), 'only breakouts in an uptrend', group='Trend', weight=1)
    if len(df) >= 200: c.check('Above the 200 EMA', px > last(ema(close, 200)), 1, 'Trend', 'long-term trend up')

    upper, lower = donchian(df, s['lookback']); level = last(upper); base_low = last(lower)
    broke_bars = [i for i in range(1, s['fresh_bars'] + 1) if df.Close.iloc[-i] > upper.iloc[-i]]
    gap_pct = abs(c.real(level) - c.real(px)) / c.real(px) * 100
    if broke_bars and px < level: c.skip('The breakout failed: price closed back inside the base')
    if not broke_bars and gap_pct > s['near_pct']: c.skip(f"No breakout nearby: price is {gap_pct:.1f}% below the {s['lookback']}-day high")
    today = bool(broke_bars) and broke_bars[0] == 1 and df.Close.iloc[-2] <= upper.iloc[-2]

    tight = last(atr(df, 10)) / last(atr(df, 50)) <= s['base_atr_ratio'] if len(df) > 60 else False
    c.check('Tight base before the breakout', tight, 1, 'Setup', 'volatility contracted (10-day ATR under the 50-day ATR)')
    c.check(f"Close above the {s['lookback']}-day high", bool(broke_bars), 3, 'Breakout', f"level {c.fmt(level)}")
    rv = relative_volume(df, 20, at=-(broke_bars[0] if broke_bars else 1))
    c.check(f"Volume {s['volume_x']}x normal", rv >= s['volume_x'], 2, 'Breakout', f'{rv:.1f}x the 20-day average' if rv == rv else 'no volume data')
    c.check('Strong close', close_position(df) >= 0.6, 1, 'Breakout', 'closed in the top 40% of the candle')
    if c.nifty is not None and len(c.nifty) > 60:
        c.check('Nifty above its 50 EMA', last(c.nifty.Close) > last(ema(c.nifty.Close, 50)), 1, 'Context', 'the market supports breakouts')
    rs, ni = c.pct_change(20), c.nifty_pct_change(20)
    c.check('Stronger than Nifty (20 days)', rs is not None and ni is not None and rs > ni, 1, 'Context', f'{rs:+.1f}% vs {ni:+.1f}%' if rs is not None and ni is not None else '')

    status = TRIGGERED if today else WATCH if broke_bars else NEAR
    note = {TRIGGERED: '', WATCH: 'broke out earlier, buy a hold of the level', NEAR: f'alert at {c.fmt(level)}'}[status]
    entry = px if status == TRIGGERED else level + 0.05 * a
    stop = level - s['stop_atr'] * a
    t1 = level + (level - base_low)
    return c.setup(status, entry, stop, [t1], note=note, zone=(level - 0.2 * a, level + 0.2 * a), lines={'20-day high': upper, '50 EMA': ema(close, 50)},
                   stop_why=f"{s['stop_atr']} ATR back inside the base: a breakout that falls back there has failed.",
                   target_why='T1 is the measured move: the height of the base added to the breakout level. T2 and T3 are 2R and 3R.')


def _orb(c, use_volume):
    s = c.settings; df = c.df; a = last(atr(df, 14)); px = last(df.Close)
    h, m = (int(x) for x in s['last_entry'].split(':'))
    if c.minutes_into_session() > h * 60 + m - 555: c.skip(f"No new entries after {s['last_entry']}")
    orr = c.opening_range(s['range_minutes'])
    if not orr: c.skip(f"The first {s['range_minutes']} minutes are not over yet")
    height = orr['high'] - orr['low']
    c.require('Opening range not too wide', height <= s['max_range_atr'] * a, f'range {height / a:.1f} ATR (max {s["max_range_atr"]})', group='Setup')

    day = c.today(); above = day.Close > orr['high']; broke = bool(above.tail(s['fresh_bars']).any())
    if px < orr['high'] - s['near_atr'] * a: c.skip('Price is not near the opening-range high')
    if bool(above.iloc[:-s['fresh_bars']].any()): c.skip('The breakout happened earlier: not a fresh entry')
    c.check('Close beyond the opening range', broke and px > orr['high'], 3, 'Breakout', f"level {c.fmt(orr['high'])}")
    if use_volume:
        rv = relative_volume(df, 20)
        c.check(f"Volume {s['volume_x']}x normal", rv >= s['volume_x'], 2, 'Breakout', f'{rv:.1f}x the last 20 candles' if rv == rv else 'no volume')
        c.check('Price above VWAP', px > last(vwap(df)), 1, 'Trend', 'session buyers in control')
    else:
        c.check('Supertrend agrees', last(supertrend(df, 10, 3.0)[1]) > 0, 1, 'Trend', 'Supertrend (10, 3) on the 5m')
    b = c.bias
    if b is not None and len(b) >= 30: c.check('15m trend agrees', last(b.Close) > last(ema(b.Close, 20)), 2, 'Trend', '15m close above its 20 EMA')
    pdl = c.prev_day()
    if pdl: c.check('Room to the previous day extreme', pdl['high'] <= px or pdl['high'] - px > height, 1, 'Context', 'yesterday\'s extreme is not right overhead')

    status = TRIGGERED if broke and px > orr['high'] else NEAR
    entry = px if status == TRIGGERED else orr['high'] + 0.05 * a
    stop = (orr['high'] + orr['low']) / 2 - 0.1 * a
    return c.setup(status, entry, stop, [orr['high'] + height], note='' if status == TRIGGERED else f"alert at {c.fmt(orr['high'])}",
                   zone=(orr['low'], orr['high']), lines={'VWAP': vwap(df)} if use_volume else {'20 EMA': ema(df.Close, 20)},
                   stop_why='The middle of the opening range: a real breakout should not fall back that far.',
                   target_why='T1 is the opening-range height added to the breakout level. T2 and T3 are 2R and 3R.')


def intraday(c):
    return _orb(c, use_volume=c.has_volume)


def options(c):
    return _orb(c, use_volume=False)
