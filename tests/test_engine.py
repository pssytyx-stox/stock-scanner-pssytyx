"""Engine tests: indicators, the strategy API, shorts by mirroring, scoring and error handling. No internet needed.
Run: python tests/test_engine.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
import types
import numpy as np, pandas as pd
import scanner as sc, check_strategy as cs
from indicators import *
from strategy_api import Context, NoSetup, score_checks, grade_of, TRIGGERED, WATCH

fails = []
def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'   {info}' if info else ''))
    if not cond: fails.append(name)

zoo = cs.charts(); up = zoo[0]; NOW = cs.NOW

print('--- indicators ---')
d = up['daily']; r = rsi(d.Close)
check('RSI stays between 0 and 100', float(r.dropna().min()) >= 0 and float(r.dropna().max()) <= 100)
check('ATR is positive', float(atr(d).dropna().min()) > 0)
m5 = up['m5']; vw = vwap(m5); day = m5.index.normalize(); first = np.r_[True, day[1:] != day[:-1]]
check('VWAP restarts each session (first bar = its typical price)', np.allclose(vw[first].values, ((m5.High + m5.Low + m5.Close) / 3)[first].values))
s = pd.Series([1, 1, 1, 3.0]); check('crossed_above sees a cross on the last bar', crossed_above(s, 2.0) and not crossed_above(s.iloc[:-1], 2.0))
check('crossed_below mirrors it', crossed_below(-s, -2.0))
trend = pd.DataFrame({'Open': np.arange(100.), 'High': np.arange(100.) + 1, 'Low': np.arange(100.) - 1, 'Close': np.arange(100.) + .5, 'Volume': 1.0})
check('Supertrend is up in a steady uptrend', supertrend(trend)[1].iloc[-1] > 0)
idx = cs.session_index(5, 60); vv = pd.DataFrame({'Open': 1.0, 'High': 1.0, 'Low': 1.0, 'Close': 1.0, 'Volume': [500.0 if t.hour == 9 else 100.0 for t in idx]}, index=idx)
check('relative volume compares the same time of day', abs(relative_volume(vv, same_time=True, at=-len(idx) + list(idx).index(idx[idx.hour == 9][-1])) - 1.0) < 1e-9)

print('--- strategy API ---')
c = Context('swing', 'long', 'X', d)
try: c.require('Must', False, 'because'); ok = False
except NoSetup as ex: ok = 'Must' in str(ex) and 'because' in str(ex)
check('a failed require stops with its name and reason', ok)
c = Context('swing', 'long', 'X', d); c.check('a', True, 3); c.check('b', False, 1); sc10, groups = score_checks(c.checks)
check('score is the passed weight scaled to 10', sc10 == 8 and groups[0]['got'] == 3 and groups[0]['max'] == 4, str((sc10, groups)))
check('grades from the thresholds', grade_of(8, {'A+': 8, 'A': 6, 'B': 4}) == 'A+' and grade_of(5, {'A+': 8, 'A': 6, 'B': 4}) == 'B' and grade_of(3, {'A+': 8, 'A': 6, 'B': 4}) == 'skip')
try: Context('swing', 'long', 'X', d).setup('MAYBE', 1, 0); ok = False
except ValueError: ok = True
check('an unknown status is refused', ok)

print('--- engine ---')
def make(fn, **sections):
    mod = types.SimpleNamespace(NAME='t', SECTIONS={'swing': dict(enabled=True, sides=['long', 'short'], main='1d', trigger=None)}, GRADES={'A': 1}, swing=fn)
    st = sc.Strategy.__new__(sc.Strategy); st.mod = mod; st.path = 'test'; st.name = 't'; st.description = ''
    st.sections = {k: dict(v, **mod.SECTIONS.get(k, {})) for k, v in sc.SECTION_DEFAULTS.items()}; st.sections['options']['enabled'] = st.sections['intraday']['enabled'] = False
    st.universe = dict(sc.UNIVERSE_DEFAULTS); st.grades = mod.GRADES; st.settings = {}; st.rules = {}; st.rulebook = {k: {} for k in sc.SECTION_DEFAULTS}
    return st

def rule(c):
    e = ema(c.df.Close, 20); a = last(atr(c.df))
    c.check('above', last(c.df.Close) > last(e), 2, 'Trend'); c.check('rsi', last(rsi(c.df.Close)) > 50, 1, 'Momentum')
    return c.setup(WATCH, last(c.df.Close), last(lowest(c.df.Low, 5)) - .25 * a, [last(c.df.Close) + 3 * a], zone=(last(e) - a, last(e)), lines={'20 EMA': e})

st = make(rule); K0 = 5000.0
rl, _ = sc.evaluate(st, 'swing', 'long', 'X', d, now=NOW)
rs, _ = sc.evaluate(st, 'swing', 'short', 'X', sc.invert(d, K0), now=NOW)
check('a long setup is produced', rl is not None and rl['entry'] > rl['sl'])
check('the same chart flipped gives the same short (same score)', rs is not None and rs['score'] == rl['score'], f"{rs and rs['score']} vs {rl['score']}")
check('short levels are the flipped long levels', all(abs((K0 - rl[k]) - rs[k]) < 1e-6 for k in ('entry', 'sl', 't1', 't2', 't3')))
check('short stop is above entry, targets below', rs['sl'] > rs['entry'] > rs['t1'] > rs['t2'] > rs['t3'])
check('short zone and lines are flipped back to real prices', abs(rs['zone_top'] - (K0 - rl['zone_bot'])) < 1e-6 and abs(rs['lines']['20 EMA'].iloc[-1] - (K0 - rl['lines']['20 EMA'].iloc[-1])) < 1e-6)
check('rule wording is flipped for the short', [x['name'] for x in rs['checks']] == ['below', 'rsi'] and [x['name'] for x in rl['checks']] == ['above', 'rsi'])
check('missing targets become 2R and 3R', abs(rl['r_t2'] - 2) < 1e-9 and abs(rl['r_t3'] - 3) < 1e-9)
bad, why = sc.evaluate(make(lambda c: c.setup(WATCH, 100, 110)), 'swing', 'long', 'X', d, now=NOW)
check('a stop on the wrong side is refused with a reason', bad is None and 'other side' in why, why)
def boom(c): return 1 / 0
r_, why = sc.safe_evaluate(make(boom), 'swing', 'long', 'X', d, now=NOW)
check('a crash in the strategy skips the instrument instead of stopping the scan', r_ is None and 'ZeroDivisionError' in why, why)
st2 = make(rule); sc.evaluate(st2, 'swing', 'long', 'X', d, now=NOW)
check('the rulebook records every rule the strategy used', set(st2.rulebook['swing']) == {'above', 'rsi'})
st3 = make(lambda c: (c.check('fixed', True, 1, 'G', 'same text'), c.check('live', True, 1, 'G', f'value {len(c.df)}'), c.setup(WATCH, last(c.df.Close), last(c.df.Low) - 5))[-1])
sc.evaluate(st3, 'swing', 'long', 'X', d, now=NOW); one = {r['name']: r['why'] for r in st3.rules_out('swing')}
sc.evaluate(st3, 'swing', 'long', 'Y', d.iloc[:-1], now=NOW); two = {r['name']: r['why'] for r in st3.rules_out('swing')}
check('the rules card shows a description only once two stocks agree on it, never one with live numbers', one == {'fixed': '', 'live': ''} and two == {'fixed': 'same text', 'live': ''}, str((one, two)))

print('--- the shipped strategies run ---')
for p in ('strategy.py', 'examples/breakout.py', 'examples/blank_template.py'):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): code = cs.main(p)
    check(f'{p} passes check_strategy', code == 0, buf.getvalue()[-300:] if code else '')
bad_path = os.path.join(ROOT, 'tests', '_broken_strategy.py'); open(bad_path, 'w').write(open('strategy.py').read().replace("px = last(close)", "px = last(clse)", 1))
buf = io.StringIO()
with contextlib.redirect_stdout(buf): code = cs.main(bad_path)
os.remove(bad_path)
check('a typo in the strategy is caught and its line is named', code == 1 and '_broken_strategy.py' in buf.getvalue() and 'line' in buf.getvalue(), buf.getvalue()[-200:])

print('\n' + ('ALL PASSED' if not fails else f'{len(fails)} FAILED: {fails}')); sys.exit(1 if fails else 0)
