# Writing your strategy

Everything the scanner looks for is in **`strategy.py`**. The engine downloads the candles, runs your rules on every stock (and on Nifty for options), scores the results and builds the dashboard. You only describe the rules.

You can edit it on the GitHub website: open `strategy.py`, click the pencil, change it, commit. Before every scan the workflow runs `check_strategy.py`. If something is wrong, the run stops with a message that names the line, and your last good dashboard stays online.

## The parts of strategy.py

| Part | What it controls |
|---|---|
| `NAME`, `DESCRIPTION` | Shown on the dashboard |
| `SECTIONS` | Which sections run, which sides (long/short), which timeframes, the subtitle on each page |
| `UNIVERSE` | Which stocks qualify at all: minimum price, minimum turnover, skip locked circuits, how many liquid stocks intraday scans |
| `GRADES` | Score needed for A+, A and B. Anything under the lowest grade is dropped |
| `SETTINGS` | Every number your rules use, one block per section. Inside a rule, `c.settings` is the block for that section |
| `RULES` | Your risk rules, shown on every trade page |
| `def swing(c)`, `def intraday(c)`, `def options(c)` | The rules themselves |

### SECTIONS

```python
SECTIONS = {
    'swing':    dict(enabled=True, sides=['long'], main='1d', trigger='1h', sector_filter=True, summary='...'),
    'options':  dict(enabled=True, sides=['long', 'short'], main='5m', bias='15m', summary='...'),
    'intraday': dict(enabled=True, sides=['long', 'short'], main='5m', bias='15m', summary='...'),
}
```

- `enabled=False` turns a section off. Its page then says so.
- `sides`: `'long'`, `'short'` or both. For options, long is a CALL and short is a PUT.
- `main` is the timeframe your rules read as `c.df`. Swing: `'1d'`. Options and intraday: `'5m'` or `'15m'`.
- `trigger` (swing only) is the entry timeframe, given to you as `c.trigger`: `'1h'` or `None`.
- `bias` (options and intraday) is a higher timeframe, given to you as `c.bias`: `'15m'`, `'1h'` or `None`.
- `sector_filter` (swing only): if the stock's sector index is falling, a TRIGGERED long is held at WATCH.

## How a rule function works

```python
def swing(c):
    df = c.df                                    # candles: df.Open, df.High, df.Low, df.Close, df.Volume
    e20 = ema(df.Close, 20)

    c.require('Above the 20 EMA', last(df.Close) > last(e20), 'only uptrends', group='Trend')   # must pass
    c.check('RSI above 50', last(rsi(df.Close)) > 50, 2, 'Momentum', 'buyers in control')      # scored, 2 points

    entry = last(df.Close)
    stop = last(lowest(df.Low, 5))
    return c.setup(WATCH, entry, stop, lines={'20 EMA': e20})
```

1. **`c.require(name, ok, why, group=..., weight=0)`** is a must-have rule. If `ok` is False the stock is skipped, and `name: why` becomes the reason (for options it is shown on the page as "why there is no CALL/PUT").
2. **`c.check(name, ok, weight, group, why)`** is a scored rule. It also returns `ok`, so you can use it in an `if`.
3. **`c.skip(reason)`** stops here with no setup.
4. **`return c.setup(...)`** describes the trade.

Every require and check you call is listed on the trade page with a ✓ or ✗, grouped by `group`, and on the "How this list is built" card. Write the names and the `why` text for a reader.

### Score and grade

The score out of 10 is the weight of the rules that passed divided by the weight of all the rules that ran, times 10. Example: checks worth 2 + 2 + 1 + 1 = 6 points, the 2 + 2 + 1 pass, so the score is 5 / 6 × 10 ≈ 8 = A+ with the default `GRADES`. A `require` has no weight unless you give it one.

### c.setup(...)

| Argument | Meaning |
|---|---|
| `status` | `TRIGGERED` (enter now), `WATCH` (in the area, waiting for the trigger) or `NEAR` (close, set an alert) |
| `entry`, `stop` | Prices. The stop must be below the entry (for longs) |
| `targets` | Up to 3 prices. Missing ones become 1.5R, 2R and 3R |
| `note` | Short text after the status, e.g. `'waiting for the 1H close'` |
| `zone` | `(low, high)` shaded on the chart as the entry area |
| `lines` | `{'name': series}` drawn on the chart, e.g. moving averages |
| `stop_why`, `target_why` | One sentence each, shown under "Why this trade" |
| `notes` | A list of cautions |

Only TRIGGERED setups send a phone alert by default.

## What c gives you

| | |
|---|---|
| `c.df` | Main timeframe candles, closed candles only |
| `c.trigger` | Swing only: trigger timeframe candles. **None on the first pass**: the engine first runs every stock on daily data, then downloads 1H data only for stocks that produced a setup and runs your rules again. So trigger rules must cope with `None` (the default strategy simply lets them fail) |
| `c.bias` | Options and intraday: bias timeframe candles, or None |
| `c.nifty` | Swing only: Nifty 50 daily candles |
| `c.section`, `c.side`, `c.long`, `c.symbol`, `c.now` | Where you are |
| `c.settings` | Your `SETTINGS` block for this section |
| `c.has_volume` | False for the Nifty index (Yahoo has no index volume) |
| `c.today()` | Today's candles (intraday frames) |
| `c.prev_day()` | `dict(high, low, close)` of the previous session |
| `c.opening_range(15)` | `dict(high, low)` of the first 15 minutes, or None if it is not over yet |
| `c.minutes_into_session()` | Minutes since 09:15 at the latest candle |
| `c.pct_change(20)`, `c.nifty_pct_change(20)` | Real % change over 20 candles, positive when it moves your way |
| `c.real(x)`, `c.fmt(x)` | A price as it really is on the chart (see Shorts) |

## Indicators

From `indicators.py` (already imported in `strategy.py`). They return a pandas Series unless noted. `last(s)` is the latest value, `last(s, 2)` the one before.

| Function | |
|---|---|
| `ema(s, n)`, `sma(s, n)` | Moving averages |
| `rsi(close, 14)` | RSI 0 to 100 |
| `atr(df, 14)`, `true_range(df)` | Volatility |
| `macd(close, 12, 26, 9)` | Returns `(macd, signal, histogram)` |
| `bollinger(close, 20, 2)` | Returns `(middle, upper, lower)` |
| `adx(df, 14)` | Returns `(adx, +DI, -DI)` |
| `supertrend(df, 10, 3)` | Returns `(line, direction)`, direction +1 up / -1 down |
| `vwap(df)` | Session VWAP. Needs volume, so not for the index |
| `highest(s, n)`, `lowest(s, n)` | Highest / lowest of the last n bars (`skip_current=True` to exclude the current bar) |
| `donchian(df, 20)` | `(upper, lower)` of the previous 20 bars. A close above upper is a breakout |
| `crossed_above(a, b, within=1)`, `crossed_below(...)` | True if a crossed b (a series or a number) in the last `within` bars |
| `rising(s, 3)`, `falling(s, 3)` | Compared with 3 bars ago |
| `relative_volume(df, 20, same_time=False)` | Volume ÷ normal volume (a number). `same_time=True` compares with the same time of day on earlier days |
| `weekly(df)` | Daily candles → weekly candles |
| `close_position(df)` | Where the close sits in the candle: 1 = at the high, 0 = at the low |
| `candle_body(df)` | Close minus open |

## Shorts: write long rules only

For a short the engine turns every chart upside down (each price p becomes K − p), runs your long rules, and turns the levels back. "Close above the 20 EMA" automatically means "close below the 20 EMA" for a short. The wording is flipped too when a short is shown: above ↔ below, high ↔ low, up ↔ down, rising ↔ falling, buyers ↔ sellers and so on.

Two things to know:

- Inside your rules, prices are flipped for shorts. If you write a price into a `why` or `note` text, use `c.fmt(x)` (or `c.real(x)` for the number), not `x`.
- Plain percentages computed from flipped prices are distorted. Use `c.pct_change()` instead of computing returns yourself.

## Common edits

**Change a number.** Edit `SETTINGS`, e.g. `'volume_x': 1.3` → `'volume_x': 2.0`.

**Add a rule.**
```python
m, sig, hist = macd(df.Close)
c.check('MACD above signal', last(m) > last(sig), 1, 'Momentum', 'momentum turning up')
```

**Make a rule a must-have.** Change `c.check(...)` to `c.require(...)` and move the weight to `weight=...`.

**Remove a rule.** Delete its line (and anything that uses its result).

**Long only for intraday.** `SECTIONS['intraday']['sides'] = ['long']`.

**Turn off options.** `SECTIONS['options']['enabled'] = False`.

**Use a ready-made strategy.** Copy `examples/breakout.py` over `strategy.py`, or set the repository variable `STRATEGY_FILE` to `examples/breakout.py`. `examples/blank_template.py` is the smallest working strategy to start from.

## Testing

On GitHub: commit, then Actions → scan → Run workflow → mode **all**. The first step, *Check the strategy*, prints how many test charts produced setups and how often each rule passed. A rule that passes 0 times or every time is worth a second look.

On your own computer (Python 3.10 or newer):
```
pip install -r requirements.txt
python check_strategy.py                  # your strategy.py
python check_strategy.py examples/breakout.py
python scanner.py --mode swing --out _site/data   # a real scan (needs internet)
```

The test charts are made up. They prove the code runs, not that the strategy makes money. Paper-trade a new strategy before you trust it.

## Common mistakes

| Message | Fix |
|---|---|
| `NameError: name 'x' is not defined` | A typo in a variable or function name on the line shown |
| `The stop must be on the other side of the entry` | For longs the stop must be below the entry |
| `status must be one of ('TRIGGERED', 'WATCH', 'NEAR')` | Use one of those three in `c.setup` |
| `'NoneType' object has no attribute ...` | `c.trigger` or `c.bias` is None: check `if c.trigger is not None` first |
| `IndexError` | Not enough candles for a long lookback: lower the number |
| Every stock skipped by the same rule | That rule is too strict, or written the wrong way round |
