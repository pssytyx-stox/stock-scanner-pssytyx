"""End-to-end test of every section, the market and news pages and the phone alerts, with fake downloads. No internet needed.
Run: python tests/test_pipeline.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
import argparse, json, tempfile
import numpy as np, pandas as pd
import scanner as sc, check_strategy as cs, newsfeed, notify

fails = []
def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'   {info}' if info else ''))
    if not cond: fails.append(name)

NOW = cs.NOW; zoo = cs.charts(); names = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'GGG', 'HHH']
pick = [0, 1, 2, 3, 4, 8, 12, 16]                       # uptrends with pullbacks, a steady uptrend, a downtrend, a range, volatile
FR = {'1d': {}, '1h': {}, '5m': {}, '15m': {}}
for n, i in zip(names, pick):
    ch = zoo[i]; FR['1d'][n], FR['1h'][n], FR['5m'][n], FR['15m'][n] = ch['daily'], ch['hourly'], ch['m5'], ch['m15']
steady = next(z for z in zoo if z['name'].startswith('steady uptrend'))
FR['1d'].update({'^NSEI': steady['daily'] * [1, 1, 1, 1, 0] + [0, 0, 0, 0, 0], '^NSEBANK': zoo[5]['daily'], '^INDIAVIX': (zoo[13]['daily'] / 70).assign(Volume=0), '^CNXIT': steady['daily']})
FR['5m']['^NSEI'] = zoo[0]['m5'].assign(Volume=0.0); FR['15m']['^NSEI'] = zoo[0]['m15'].assign(Volume=0.0); FR['1h']['^CNXIT'] = steady['hourly']

def to_raw(f, interval):
    """Undo the engine's tidy step so the fake looks like a Yahoo download (UTC intraday timestamps, plus one unfinished candle)."""
    f = f.copy()
    if interval != '1d': f.index = f.index.tz_convert('UTC')
    return f
def fake_download(symbols, period, interval, chunk=50, pause=1.0):
    out = {s: to_raw(FR[interval][s], interval) for s in symbols if s in FR[interval]}; return out, [s for s in symbols if s not in out]
sc.download_many = fake_download
industries = {'AAA': 'Information Technology', 'BBB': 'Information Technology', 'CCC': 'Information Technology', 'DDD': 'Realty', 'EEE': 'Realty', 'FFF': 'Realty', 'GGG': 'Chemicals', 'HHH': 'Chemicals'}
sc.load_nifty500 = lambda *a, **k: (names, 'test universe (8 symbols)', industries)
soon = (NOW + pd.Timedelta(days=2)).strftime('%Y-%m-%d')
sc.results_info = lambda s, now: dict(date=soon, days=2, source='test') if s == 'AAA' else None
RSS = '<rss><channel><item><title>Markets rally as RBI holds rates - ET</title><link>https://example.com/a</link><pubDate>Wed, 11 Mar 2026 04:30:00 GMT</pubDate><source>ET</source></item></channel></rss>'
newsfeed.fetch_url = lambda url, timeout=15: RSS

out = tempfile.mkdtemp(); args = argparse.Namespace(out=out, watchlist='watchlist.txt', universe_csv=None, events='events.json', top=60, intraday_top=0, state_dir=tempfile.mkdtemp())
st = sc.Strategy('strategy.py')
for name in ('swing', 'options', 'intraday', 'market', 'news'): getattr(sc, 'run_' + name)(st, args, NOW)
J = {k: json.load(open(os.path.join(out, k + '.json'))) for k in ('swing', 'options', 'intraday', 'market', 'news', 'liquid', 'breadth')}

print('--- swing ---')
sw = J['swing']; S = sw['setups']
check('swing ran over the universe', sw['universe'] == 8 and sw['scanned'] == 8, f"{sw['scanned']}/{sw['universe']}")
check('swing carries the strategy name, summary and its rulebook', sw['strategy']['name'] == 'EMA Trend Pullback' and sw['strategy']['summary'] and len(sw['strategy']['rules']) >= 6)
check('swing found at least one setup', len(S) >= 1, str([(s['symbol'], s['status'], s['score']) for s in S]))
if S:
    s0 = S[0]
    check('every setup has levels, a chart and the lines', all(s0[k] is not None for k in ('entry', 'sl', 't1', 't2', 't3')) and len(s0['candles']) == len(s0['times']) and s0['lines'] and len(s0['lines'][0]['values']) == len(s0['candles']))
    check('long only: stop below entry, targets above', all(s['direction'] == 'long' and s['sl'] < s['entry'] < s['t1'] for s in S))
    check('checks and groups explain the score', s0['checks'] and s0['groups'] and 0 <= s0['score'] <= 10)
    check('why-this-trade has a step per rule group plus stop and targets', {'Trend', 'Setup', 'Stop-loss', 'Targets'} <= {x['title'] for x in s0['logic']})
    check('execution and trail plans are filled in and use your risk rules', s0['plan']['execution'] and s0['plan']['trail'] and s0['plan']['rules'] == st.rules['swing'])
    check('prices sit on the 5 paise tick', all(abs(round(s['entry'] / 0.05) * 0.05 - s['entry']) < 1e-6 for s in S))
    check('sector index check is attached', all('index_check' in s for s in S))
    aaa = [s for s in S if s['symbol'] == 'AAA']
    if aaa: check('results date is attached and listed under cautions', aaa[0]['results']['days'] == 2 and any('Results in 2' in (x.get('text') or '') for x in aaa[0]['logic']))
check('liquidity ranking for intraday is written', J['liquid']['top'] and set(J['liquid']['top']) <= set(names))
check('breadth is written', J['breadth']['summary'] and J['breadth']['summary']['count'] == 8)

print('--- options ---')
op = J['options']
check('options snapshot is there', op['snapshot']['spot'] is not None and 'above_15m' in op['snapshot'])
check('every side is either a setup or has a reason', len(op['setups']) + len(op['snapshot']['why_none']) == 2, str(op['snapshot']['why_none']))
for s in op['setups']:
    check(f"{s['label']} has a strike with Greeks", s.get('options_trade') and s['options_trade']['instrument'].startswith('NIFTY'))

print('--- intraday ---')
it = J['intraday']
check('intraday used the liquidity list', 'Most liquid' in it['note'], it['note'])
check('intraday setups (if any) have both sides valid', all((s['sl'] < s['entry']) == (s['direction'] == 'long') for s in it['setups']))

print('--- market and news ---')
check('market regime and playbook', J['market']['daily']['regime'] and J['market']['playbook']['swing'])
check('playbook text does not mention a specific strategy', not any(w in json.dumps(J['market']['playbook']) for w in ('order block', 'OI wall', 'CHoCH')))
check('news headlines and events', J['news']['headlines'] and isinstance(J['news']['events'], list))

print('--- a section turned off ---')
st_off = sc.Strategy('examples/blank_template.py'); sc.run_options(st_off, args, NOW); off = json.load(open(os.path.join(out, 'options.json')))
check('a disabled section writes an empty page that says so', off['setups'] == [] and off['strategy']['enabled'] is False and 'Turned off' in off['note'])
sc.run_options(st, args, NOW)

print('--- alerts ---')
sent = []
notify.post = lambda base, topic, title, body, tags, click: sent.append((title, body))
os.environ.update(NTFY_TOPIC='test-topic', NTFY_MIN_SCORE='0', NTFY_STATUSES='TRIGGER,WATCH,NEAR', NTFY_UPDATES='off')
state = os.path.join(tempfile.mkdtemp(), 'n.json'); sys.argv = ['notify', '--dir', out, '--state', state]
n_setups = sum(len(J[k]['setups']) for k in ('swing', 'intraday')) + len(json.load(open(os.path.join(out, 'options.json')))['setups'])
notify.main(); first = len(sent); notify.main()
check('one push per setup', first == n_setups, f'{first} vs {n_setups}')
check('nothing is pushed twice in a day', len(sent) == first)
check('push text has entry, SL and the rules that passed', not sent or ('Entry' in sent[0][1] and 'Passed:' in sent[0][1]))

print('\n' + ('ALL PASSED' if not fails else f'{len(fails)} FAILED: {fails}')); sys.exit(1 if fails else 0)
