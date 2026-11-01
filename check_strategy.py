#!/usr/bin/env python3
"""Check a strategy file before it goes live. No internet needed.

    python check_strategy.py                     checks strategy.py
    python check_strategy.py examples/breakout.py

It runs your rules on made-up charts (uptrends, downtrends, ranges) for every enabled section and side, and reports:
  - errors in your code, with the line number in your file
  - settings that are not allowed
  - how often each rule passed, so you can see if a rule never fires or always fires
The GitHub workflow runs this before every scan: if it fails, the scan stops and your last good page stays online.
"""
import collections, json, sys, traceback
import numpy as np
import pandas as pd
import scanner
from scanner import Strategy, evaluate, build_item, INTERVALS

IST = 'Asia/Kolkata'
NOW = pd.Timestamp('2026-03-11 13:02', tz=IST)


def session_index(days, minutes, end_time='13:00'):
    """Intraday timestamps for `days` weekdays ending NOW's date, 09:15 to 15:30 (last day stops at end_time)."""
    dates = pd.bdate_range(end=NOW.normalize().tz_localize(None), periods=days); out = []
    for i, d in enumerate(dates):
        stop = pd.Timestamp(f'{d.date()} {end_time if i == len(dates) - 1 else "15:30"}')
        t = pd.Timestamp(f'{d.date()} 09:15')
        while t < stop: out.append(t); t += pd.Timedelta(minutes=minutes)
    return pd.DatetimeIndex(out).tz_localize(IST)


def walk(idx, seed, drift, vol, base=1000.0, pullback_every=0, bounce=False):
    r = np.random.default_rng(seed); n = len(idx); steps = drift + r.normal(0, vol, n)
    if pullback_every:
        q = max(1, pullback_every // 4)
        for k in range(pullback_every, n, pullback_every): steps[k:k + q] -= 0.6 * abs(drift) * pullback_every / q
    if (pullback_every or bounce) and n > 12: steps[-6:-2] = -abs(drift) * 2 - vol * 0.9; steps[-2:] = abs(drift) * 4 + vol * 2.6   # end on a dip and a bounce
    c = base * np.exp(np.cumsum(steps)); o = np.r_[c[0], c[:-1]]; w = np.abs(r.normal(0, vol * 0.6, n)) * c
    return pd.DataFrame({'Open': o, 'High': np.maximum(o, c) + w, 'Low': np.minimum(o, c) - w, 'Close': c, 'Volume': r.integers(5e4, 2e5, n).astype(float)}, index=idx)


def charts():
    """A small zoo of made-up charts: strong and weak uptrends with pullbacks, downtrends and ranges."""
    d_idx = pd.bdate_range(end=NOW.normalize().tz_localize(None) - pd.Timedelta(days=1), periods=320)
    kinds = [('uptrend with pullbacks', 0.0025, 0.012, 14), ('steady uptrend', 0.0015, 0.008, 0), ('downtrend', -0.0025, 0.012, 14), ('range', 0.0, 0.01, 0), ('volatile', 0.0, 0.025, 0)]
    out = []
    for i, (name, drift, vol, pb) in enumerate(kinds):
        for seed in range(4):
            s = 100 * i + seed
            out.append(dict(name=f'{name} #{seed + 1}', daily=walk(d_idx, s, drift, vol, 1000, pb), hourly=walk(session_index(60, 60), s + 1, abs(drift) / 6 + 0.0003, vol / 3, 1000, pb, True),
                            m5=walk(session_index(5, 5), s + 2, drift / 20, vol / 8, 1000, pb * 3), m15=walk(session_index(15, 15), s + 3, drift / 10, vol / 5, 1000, pb * 2),
                            m1h=walk(session_index(30, 60), s + 4, drift / 6, vol / 3, 1000, pb)))
    return out


def frame_for(ch, interval):
    return {'1d': ch['daily'], '1h': ch['hourly'], '5m': ch['m5'], '15m': ch['m15']}[interval]


def problem(msg):
    print('PROBLEM: ' + msg); return 1


def check_config(st):
    errs = 0
    for sec, cfg in st.sections.items():
        if not cfg['enabled']: continue
        if not set(cfg.get('sides', [])) <= {'long', 'short'} or not cfg.get('sides'): errs += problem(f"SECTIONS['{sec}']['sides'] must be a list with 'long' and/or 'short'.")
        allowed_main = ['1d'] if sec == 'swing' else ['5m', '15m']
        if cfg.get('main') not in allowed_main: errs += problem(f"SECTIONS['{sec}']['main'] is {cfg.get('main')!r}; use one of {allowed_main}.")
        if sec == 'swing' and cfg.get('trigger') not in (None, '1h'): errs += problem("SECTIONS['swing']['trigger'] must be '1h' or None.")
        if sec != 'swing' and cfg.get('bias') not in (None, '15m', '1h'): errs += problem(f"SECTIONS['{sec}']['bias'] must be '15m', '1h' or None.")
    if not st.grades or not all(isinstance(v, (int, float)) for v in st.grades.values()): errs += problem('GRADES must look like {"A+": 8, "A": 6, "B": 4}.')
    return errs


def main(path='strategy.py'):
    print(f'Checking {path}')
    try: st = Strategy(path)
    except Exception:
        tb = traceback.format_exc(); print(tb); return problem(f'{path} could not be loaded. Look at the last lines above: they name the line with the mistake.')
    print(f'Strategy: {st.name}')
    errs = check_config(st)
    if errs: return 1
    zoo = charts(); nifty = next(z['daily'] for z in zoo if z['name'].startswith('steady uptrend'))
    for sec, cfg in st.sections.items():
        if not cfg['enabled']: print(f'\n{sec}: turned off'); continue
        found = collections.Counter(); reasons = collections.Counter(); passes = collections.Counter(); seen = collections.Counter()
        for ch in zoo:
            df = frame_for(ch, cfg['main']) if sec != 'swing' else ch['daily']
            trig = ch['hourly'] if sec == 'swing' and cfg.get('trigger') else None
            bias = (ch['m15'] if cfg.get('bias') == '15m' else ch['m1h']) if sec != 'swing' and cfg.get('bias') else None
            if sec != 'swing': df = df.assign(Volume=0.0) if sec == 'options' else df
            for side in cfg['sides']:
                for t in ([None, trig] if sec == 'swing' and trig is not None else [trig]):
                    try: r, why = evaluate(st, sec, side, ch['name'], df, t, bias, nifty if sec == 'swing' else None, NOW)
                    except Exception:
                        tb = traceback.format_exc().splitlines(); mine = [l for l in tb if path.split('/')[-1] in l]
                        print('\n'.join(tb[-12:]))
                        return problem(f"{sec} rules crashed on a {ch['name']} chart ({side}). " + (f"The error is at {mine[-1].strip()}." if mine else 'See the lines above.'))
                    st_checks = st.rulebook[sec]
                    if r:
                        found[r['status'].split(' ')[0]] += 1
                        for c in r['checks']: seen[c['name']] += 1; passes[c['name']] += c['ok']
                        try: json.dumps(build_item(st, ch['name'], side, r, df, (cfg['main'], cfg.get('trigger')), 60, sec), default=str)
                        except Exception as ex: return problem(f'{sec}: the setup could not be turned into page data ({ex}). Check the values you pass to c.setup().')
                    else: reasons[why.split(':')[0]] += 1
        total = sum(found.values()) + sum(reasons.values())
        print(f'\n{sec}: {total} test runs, {sum(found.values())} setups ' + (f"({', '.join(f'{k} {v}' for k, v in found.items())})" if found else ''))
        if reasons: print('  skipped because: ' + '; '.join(f'{k} ({v})' for k, v in reasons.most_common(5)))
        if not st.rulebook[sec]: errs += problem(f'{sec}: your rules never called c.require() or c.check(), so nothing can be scored.')
        for name, n in seen.items(): print(f'  rule "{name}": passed {passes[name]} of {n} setups')
    if errs: return 1
    print('\nOK: the strategy runs without errors. Made-up charts only test that the code works, not that the strategy makes money.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'strategy.py'))
