"""The small API your strategy uses. You do not need to edit this file: edit strategy.py.

Inside a rule function you get `c`, a Context:
    c.df         candles of the main timeframe (closed candles only). Columns Open, High, Low, Close, Volume.
    c.trigger    swing only: the lower trigger timeframe (1H by default). None on the first, daily-only pass.
    c.bias       options/intraday only: the higher bias timeframe (15m by default), or None.
    c.nifty      swing only: Nifty 50 daily candles.
    c.section    'swing', 'options' or 'intraday'.     c.side   'long' or 'short'.     c.symbol   e.g. 'TCS'.
    c.now        current IST time (pandas Timestamp).  c.settings   your SETTINGS[section] dict.

    c.require(name, ok, why)          a must-have rule. If ok is False the instrument is skipped (the reason is shown on the page).
    c.check(name, ok, weight, group, why)   a scored rule. Score = weight of the rules that pass, scaled to 10.
    c.skip(reason)                    stop here, no setup.
    c.setup(status, entry, stop, ...) the result. status is TRIGGERED, WATCH or NEAR.

SHORTS: write long rules only. For a short the engine flips every chart upside down (price p becomes K - p), runs the same
rules and flips the levels back. So 'close above the 20 EMA' finds 'close below the 20 EMA' for shorts automatically, and the
words in your rule names are flipped too when a short is shown (above/below, high/low, up/down, rising/falling ...).
Inside the rules prices are flipped for shorts: use c.real(x) or c.fmt(x) when you write a price into text.
"""
import math
import re
import numpy as np
import pandas as pd

TRIGGERED, WATCH, NEAR = 'TRIGGERED', 'WATCH', 'NEAR'
STATUSES = (TRIGGERED, WATCH, NEAR)


class NoSetup(Exception):
    """Raised by c.require / c.skip. The engine catches it and records the reason."""


class Context:
    def __init__(self, section, side, symbol, df, trigger=None, bias=None, nifty=None, settings=None, now=None, K=None, nifty_K=None):
        self.section, self.side, self.symbol = section, side, symbol
        self.df, self.trigger, self.bias, self.nifty = df, trigger, bias, nifty
        self.settings = dict(settings or {}); self.now = now if now is not None else pd.Timestamp.now(tz='Asia/Kolkata')
        self.K, self.nifty_K = K, nifty_K; self.checks = []; self.result = None

    # ---------------------------------------------------------- basics
    @property
    def long(self): return self.side == 'long'

    @property
    def has_volume(self):
        """False for indices (no volume feed) and for frames with mostly empty volume."""
        return len(self.df) > 0 and float((self.df.Volume > 0).mean()) > 0.5

    def real(self, x):
        """Convert a price inside the rules back to the real chart price (only differs for shorts)."""
        if x is None: return None
        return float(x) if self.K is None else float(self.K - x)

    def fmt(self, x, d=2):
        v = self.real(x)
        return '-' if v is None or (isinstance(v, float) and math.isnan(v)) else f'{v:,.{d}f}'

    # ---------------------------------------------------------- rules
    def require(self, name, ok, why='', group='Must have', weight=0):
        """A rule that must pass. If it fails the instrument is skipped and `name` is shown as the reason."""
        ok = bool(ok); self.checks.append(dict(name=str(name), ok=ok, weight=float(weight), group=str(group), why=str(why or ''), required=True))
        if not ok: raise NoSetup(str(name) + (': ' + why if why else ''))
        return True

    def check(self, name, ok, weight=1, group='Setup', why=''):
        """A scored rule. Returns ok, so you can also use it in if-statements."""
        ok = bool(ok); self.checks.append(dict(name=str(name), ok=ok, weight=float(weight), group=str(group), why=str(why or ''), required=False))
        return ok

    def skip(self, reason):
        raise NoSetup(str(reason))

    def passed(self, name):
        return any(c['name'] == name and c['ok'] for c in self.checks)

    # ---------------------------------------------------------- handy helpers
    def today(self, df=None):
        """Candles of the latest session in an intraday frame."""
        df = self.df if df is None else df
        return df[df.index.normalize() == df.index[-1].normalize()]

    def prev_day(self, df=None):
        """dict(high, low, close) of the previous session from an intraday frame, or None."""
        df = self.df if df is None else df; d = df.index.normalize(); days = sorted(set(d))
        if len(days) < 2: return None
        p = df[d == days[-2]]; return dict(high=float(p.High.max()), low=float(p.Low.min()), close=float(p.Close.iloc[-1]))

    def opening_range(self, minutes=15, df=None):
        """dict(high, low) of the first `minutes` of today's session, or None if it is not complete yet."""
        day = self.today(df); start = day.index[0] if len(day) else None
        if start is None: return None
        first = day[day.index < start + pd.Timedelta(minutes=minutes)]
        if len(first) == len(day): return None
        return dict(high=float(first.High.max()), low=float(first.Low.min()))

    def minutes_into_session(self):
        t = self.df.index[-1]; return t.hour * 60 + t.minute - (9 * 60 + 15)

    def pct_change(self, bars, df=None):
        """Real % change over `bars` candles, signed for the trade side (positive = moving your way)."""
        df = self.df if df is None else df
        if len(df) <= bars: return None
        a, b = self.real(df.Close.iloc[-1 - bars]), self.real(df.Close.iloc[-1])
        ch = 100 * (b / a - 1) if a else 0.0
        return ch if self.long else -ch

    def nifty_pct_change(self, bars):
        if self.nifty is None or len(self.nifty) <= bars: return None
        a = float(self.nifty.Close.iloc[-1 - bars]); b = float(self.nifty.Close.iloc[-1])
        if self.nifty_K is not None: a, b = self.nifty_K - a, self.nifty_K - b
        ch = 100 * (b / a - 1) if a else 0.0
        return ch if self.long else -ch

    # ---------------------------------------------------------- the result
    def setup(self, status, entry, stop, targets=None, note='', zone=None, lines=None, stop_why='', target_why='', notes=None, label=None):
        """Describe the trade. Prices are as seen by the rules (the engine flips them back for shorts).
        status   TRIGGERED (enter now), WATCH (in the area, waiting for the trigger) or NEAR (close, set an alert)
        entry    entry price.  stop   stop-loss price.  targets   up to 3 prices; missing ones become 1.5R, 2R and 3R
        note     short text after the status, e.g. 'waiting for 1H close'
        zone     (low, high) shaded on the chart as the entry area, optional
        lines    {'20 EMA': series, ...} drawn on the chart, optional
        stop_why / target_why   one sentence each, shown under 'Why this trade'
        notes    list of cautions"""
        st = str(status).upper().split(' ')[0]
        if st not in STATUSES: raise ValueError(f'status must be one of {STATUSES}, got {status!r}')
        self.result = dict(status=st, note=str(note or ''), entry=_f(entry), stop=_f(stop), targets=[_f(t) for t in (targets or []) if t is not None][:3],
                           zone=(tuple(sorted((_f(zone[0]), _f(zone[1])))) if zone else None), lines=dict(lines or {}), stop_why=str(stop_why or ''),
                           target_why=str(target_why or ''), notes=list(notes or []), label=label)
        return self.result


_PAIRS = [('above', 'below'), ('up', 'down'), ('uptrend', 'downtrend'), ('rising', 'falling'), ('rises', 'falls'), ('rise', 'fall'), ('high', 'low'), ('highs', 'lows'),
          ('higher', 'lower'), ('highest', 'lowest'), ('bullish', 'bearish'), ('buyers', 'sellers'), ('buy', 'sell'), ('support', 'resistance'), ('green', 'red'),
          ('top', 'bottom'), ('demand', 'supply'), ('overbought', 'oversold'), ('gains', 'losses')]
_SWAP = {}
for _a, _b in _PAIRS: _SWAP.setdefault(_a, _b); _SWAP.setdefault(_b, _a)
_RX = re.compile(r'\b(' + '|'.join(sorted(map(re.escape, _SWAP), key=len, reverse=True)) + r')\b', re.IGNORECASE)

def flip_words(text):
    """Turn the wording of a long rule into the wording for a short ('close above the high' -> 'close below the low')."""
    def sub(m):
        w = m.group(0); t = _SWAP.get(w.lower(), w)
        return t.upper() if w.isupper() and len(w) > 1 else t[:1].upper() + t[1:] if w[:1].isupper() else t
    return _RX.sub(sub, text) if text else text


def _f(x):
    if isinstance(x, pd.Series): x = x.iloc[-1]
    return None if x is None else float(x)


def grade_of(score, grades):
    for g, lo in sorted(grades.items(), key=lambda kv: -kv[1]):
        if score >= lo: return g
    return 'skip'


def score_checks(checks):
    """Score out of 10 from the weights, plus a per-group breakdown."""
    tot = sum(c['weight'] for c in checks); got = sum(c['weight'] for c in checks if c['ok'])
    groups = []
    for c in checks:
        g = next((x for x in groups if x['name'] == c['group']), None)
        if g is None: g = dict(name=c['group'], got=0.0, max=0.0); groups.append(g)
        g['max'] += c['weight']; g['got'] += c['weight'] if c['ok'] else 0.0
    for g in groups: g['got'], g['max'] = round(g['got'], 2), round(g['max'], 2)
    return (int(round(10 * got / tot)) if tot > 0 else 0), groups
