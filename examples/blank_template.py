"""
Blank template: the smallest strategy that works. Copy it over strategy.py and grow it rule by rule.
Each section function gets `c` (see STRATEGY_GUIDE.md) and returns c.setup(...) or stops with c.skip / a failed c.require.
"""
from indicators import *
from strategy_api import TRIGGERED, WATCH, NEAR

NAME = 'My strategy'
DESCRIPTION = 'Describe your idea in one sentence. It is shown on the dashboard.'

SECTIONS = {
    'swing':    dict(enabled=True, sides=['long'], main='1d', trigger=None, sector_filter=False, summary='Nifty 500 · my swing rules'),
    'options':  dict(enabled=False, sides=['long', 'short'], main='5m', bias='15m', summary='Nifty 50 index · my option rules'),
    'intraday': dict(enabled=False, sides=['long', 'short'], main='5m', bias='15m', summary='Liquid stocks · my intraday rules'),
}
UNIVERSE = dict(min_price=50, min_turnover_cr=20, skip_locked_circuit=True, intraday_top=100)
GRADES = {'A+': 8, 'A': 6, 'B': 4}
SETTINGS = {'swing': dict(ema_len=20), 'options': dict(ema_len=20), 'intraday': dict(ema_len=20)}
RULES = {'swing': ['Never widen the stop.'], 'options': ['Never average down.'], 'intraday': ['Square off by 15:10.']}


def swing(c):
    df = c.df                                   # daily candles: df.Open, df.High, df.Low, df.Close, df.Volume
    line = ema(df.Close, c.settings['ema_len'])
    a = last(atr(df, 14))                        # last(x) = the latest value

    # 1. Must-have rules: if one fails the stock is skipped
    c.require('Close above the EMA', last(df.Close) > last(line), 'only buy stocks in an uptrend', group='Trend')

    # 2. Scored rules: the score out of 10 is the weight of the rules that pass
    c.check('EMA rising', rising(line, 5), 2, 'Trend', 'the EMA is higher than 5 days ago')
    c.check('RSI above 50', last(rsi(df.Close)) > 50, 1, 'Momentum', 'buyers are in control')
    green = c.check('Green candle', last(df.Close) > last(df.Open), 1, 'Trigger', 'today closed up')

    # 3. The trade
    entry = last(df.Close)
    stop = last(lowest(df.Low, 5)) - 0.25 * a     # below the 5-day low
    return c.setup(TRIGGERED if green else WATCH, entry, stop,
                   lines={'EMA': line},
                   stop_why='Below the 5-day low.', target_why='T1, T2 and T3 are 1.5R, 2R and 3R.')


def options(c):
    df = c.df; line = ema(df.Close, c.settings['ema_len'])
    c.require('Above the EMA', last(df.Close) > last(line), group='Trend')
    c.check('Supertrend up', last(supertrend(df)[1]) > 0, 1, 'Trend')
    return c.setup(WATCH, last(df.Close), last(lowest(df.Low, 6)) - 0.2 * last(atr(df)), lines={'EMA': line})


def intraday(c):
    df = c.df; line = ema(df.Close, c.settings['ema_len'])
    c.require('Above the EMA', last(df.Close) > last(line), group='Trend')
    c.check('Above VWAP', last(df.Close) > last(vwap(df)), 1, 'Trend')
    return c.setup(WATCH, last(df.Close), last(lowest(df.Low, 6)) - 0.2 * last(atr(df)), lines={'EMA': line})
