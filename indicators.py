"""Indicators you can use in strategy.py. Every function takes pandas Series / DataFrames (columns Open, High, Low, Close, Volume)
and returns a Series of the same length unless it says otherwise. Use .iloc[-1] for the latest value, .iloc[-2] for the one before.

    from indicators import *
    e20 = ema(df.Close, 20); r = rsi(df.Close, 14); a = atr(df, 14)
    if crossed_above(df.Close, e20, within=3): ...
"""
import numpy as np
import pandas as pd

__all__ = ['ema', 'sma', 'rsi', 'atr', 'true_range', 'vwap', 'supertrend', 'macd', 'bollinger', 'adx', 'highest', 'lowest', 'donchian',
           'crossed_above', 'crossed_below', 'rising', 'falling', 'relative_volume', 'weekly', 'last', 'candle_body', 'close_position']


# ------------------------------------------------------------------ moving averages
def ema(s, n):
    """Exponential moving average."""
    return s.ewm(span=n, adjust=False).mean()

def sma(s, n):
    """Simple moving average."""
    return s.rolling(n).mean()


# ------------------------------------------------------------------ momentum and volatility
def rsi(close, n=14):
    """Wilder RSI, 0 to 100."""
    d = close.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(dn.notna(), np.nan)

def true_range(df):
    pc = df.Close.shift()
    return pd.concat([df.High - df.Low, (df.High - pc).abs(), (df.Low - pc).abs()], axis=1).max(axis=1)

def atr(df, n=14):
    """Average true range (Wilder smoothing)."""
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()

def macd(close, fast=12, slow=26, signal=9):
    """Returns (macd line, signal line, histogram)."""
    m = ema(close, fast) - ema(close, slow); s = ema(m, signal)
    return m, s, m - s

def bollinger(close, n=20, k=2.0):
    """Returns (middle, upper, lower)."""
    mid = sma(close, n); sd = close.rolling(n).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd

def adx(df, n=14):
    """Returns (adx, +DI, -DI). ADX above about 22 means a trend, below 20 a range."""
    up = df.High.diff(); dn = -df.Low.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index); ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = true_range(df).ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / tr; ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, ndi

def supertrend(df, n=10, mult=3.0):
    """Returns (line, direction). direction is +1 while the trend is up, -1 while it is down."""
    a = atr(df, n).bfill().values; hl2 = ((df.High + df.Low) / 2).values; c = df.Close.values
    ub, lb = hl2 + mult * a, hl2 - mult * a; N = len(c); line = np.full(N, np.nan); dirn = np.ones(N)
    fu, fl = ub.copy(), lb.copy()
    for i in range(1, N):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        dirn[i] = 1 if c[i] > fu[i - 1] else -1 if c[i] < fl[i - 1] else dirn[i - 1]
        line[i] = fl[i] if dirn[i] > 0 else fu[i]
    return pd.Series(line, index=df.index), pd.Series(dirn, index=df.index)

def vwap(df):
    """Session VWAP that restarts every day. Needs volume: the Nifty index has none on Yahoo, so do not use it for options."""
    tp = (df.High + df.Low + df.Close) / 3; day = df.index.normalize() if isinstance(df.index, pd.DatetimeIndex) else np.zeros(len(df))
    pv = (tp * df.Volume).groupby(day).cumsum(); v = df.Volume.groupby(day).cumsum()
    return (pv / v.replace(0, np.nan)).fillna(tp)


# ------------------------------------------------------------------ highs, lows and crosses
def highest(s, n, skip_current=False):
    """Highest value of the last n bars (optionally not counting the current bar, for breakouts)."""
    return (s.shift(1) if skip_current else s).rolling(n).max()

def lowest(s, n, skip_current=False):
    return (s.shift(1) if skip_current else s).rolling(n).min()

def donchian(df, n=20):
    """Returns (upper, lower) of the previous n bars, not counting the current one. A close above upper is a breakout."""
    return highest(df.High, n, True), lowest(df.Low, n, True)

def _ser(x, like):
    return x if isinstance(x, pd.Series) else pd.Series(float(x), index=like.index)

def crossed_above(a, b, within=1):
    """True if series a crossed above b (or a level) on one of the last `within` bars."""
    b = _ser(b, a); above = a > b; x = above & ~above.shift(1, fill_value=True)
    return bool(x.tail(within).any())

def crossed_below(a, b, within=1):
    b = _ser(b, a); below = a < b; x = below & ~below.shift(1, fill_value=True)
    return bool(x.tail(within).any())

def rising(s, bars=3):
    """True if the latest value is above the value `bars` bars ago."""
    return len(s) > bars and bool(s.iloc[-1] > s.iloc[-1 - bars])

def falling(s, bars=3):
    return len(s) > bars and bool(s.iloc[-1] < s.iloc[-1 - bars])


# ------------------------------------------------------------------ volume and candles
def relative_volume(df, n=20, same_time=False, at=-1):
    """Volume of one bar divided by normal volume. same_time=True compares an intraday bar only with the same
    time-of-day bar on earlier days (the 09:15 candle is always heavy, so a whole-day average flatters it).
    Returns a float, or nan when there is no volume (indices)."""
    v = df.Volume.values; t = len(df) + at if at < 0 else at
    if t <= 0 or v[t] <= 0: return float('nan')
    base = None
    if same_time and isinstance(df.index, pd.DatetimeIndex):
        idx = df.index; key = (idx[t].hour, idx[t].minute); d = idx[t].date()
        pos = [i for i in range(t) if (idx[i].hour, idx[i].minute) == key and idx[i].date() != d]
        if len(pos) >= 3: base = v[pos[-10:]]
    if base is None: base = v[max(0, t - n):t]
    m = float(np.mean(base)) if len(base) else 0.0
    return float(v[t] / m) if m > 0 else float('nan')

def weekly(df):
    """Daily candles -> weekly candles (week ending Friday)."""
    return df.resample('W-FRI').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

def last(s, k=1):
    """Shortcut: last(s) is s.iloc[-1], last(s, 2) is the value before it."""
    return float(s.iloc[-k])

def candle_body(df, at=-1):
    """Body size (close minus open) of one candle."""
    return float(df.Close.iloc[at] - df.Open.iloc[at])

def close_position(df, at=-1):
    """Where the close sits inside the candle's range: 1.0 = closed at the high, 0.0 = at the low."""
    h, l, c = float(df.High.iloc[at]), float(df.Low.iloc[at]), float(df.Close.iloc[at])
    return (c - l) / (h - l) if h > l else 0.5
