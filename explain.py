"""Plain-English 'why this trade', execution steps and trailing plan for every setup, built from the strategy's own checks."""

def _n(v, d=2):
    if v is None: return '-'
    s = f'{v:,.{d}f}'
    return s[:-3] if d == 2 and s.endswith('.00') else s


def build_logic(section, it):
    """Steps for the 'Why this trade' card: one per rule group (with every check, met or not), then stop, targets and cautions."""
    dec = 1 if section == 'options' else 2; f = lambda v: _n(v, dec); out = []; groups = []
    for c in it.get('checks', []):
        if c['group'] not in groups: groups.append(c['group'])
    for g in groups:
        items = [dict(ok=c['ok'], text=c['name'] + (f": {c['why']}" if c['why'] else ''), required=c['required']) for c in it['checks'] if c['group'] == g]
        out.append(dict(title=g, items=items))
    ic = it.get('index_check')
    if ic and section == 'swing':
        base = f"Tracked against {ic['sector_index']}" + (' (built from the Nifty 500 stocks in the same industry)' if ic.get('source') == 'basket' else '') + '. '
        if ic['state'] == 'falling': tail = 'It is falling: ' + '; '.join(ic['reasons']) + '. A stock rarely holds a long when its whole group is selling, so a trigger is held at WATCH.'
        elif ic['state'] == 'unknown': tail = 'Index data was not available this run: check the index chart yourself.'
        else: tail = 'It is ' + ('strong' if ic['state'] == 'strong' else 'holding up') + ': ' + '; '.join(ic['reasons']) + '.'
        out.append(dict(title='Sector index', text=base + tail))
    out.append(dict(title='Stop-loss', text=(it.get('stop_why') or 'Set by the strategy.') + f" Stop {f(it['sl'])}, risk {_n(it.get('risk_pct'), 1)}% of price."))
    out.append(dict(title='Targets', text=(it.get('target_why') or '') + f" T1 {f(it['t1'])} ({_n(it.get('r_t1'), 1)}R), T2 {f(it['t2'])}, T3 {f(it['t3'])}."))
    ot = it.get('options_trade')
    if ot: out.append(dict(title='Strike choice (Greeks)', text=' '.join(ot['reasons'])))
    cautions = list(it.get('notes') or [])
    if it.get('sector'): cautions.append(f"sector {it['sector']} is {it.get('sector_state', 'neutral')}" + (f", {it['rs20']:+.1f}% vs Nifty over 20 days" if it.get('rs20') is not None else ''))
    if (it.get('results') or {}).get('days') is not None: cautions.append(f"results in {it['results']['days']} day(s) on {it['results']['date']}")
    if cautions: out.append(dict(title='Cautions', text='; '.join(c[:1].upper() + c[1:] for c in cautions) + '.'))
    return out


def build_plan(section, it, rules=()):
    """Execution steps and the trailing plan. All prices are levels you can place as orders or alerts."""
    d = it['direction']; up = d == 'long'; dec = 1 if section == 'options' else 2; f = lambda v: _n(v, dec)
    e, sl, t1, t2, t3 = it['entry'], it['sl'], it['t1'], it['t2'], it['t3']; risk = abs(e - sl); sym = it['symbol']; side = 'buy' if up else 'sell short'
    trig = it.get('tf_trigger') or it.get('tf_structure'); hl = 'higher low' if up else 'lower high'; below = 'below' if up else 'above'
    marks = [dict(label='T1: take half, SL to entry', price=t1, at='t1'), dict(label='T2: SL to T1', price=t2, at='t2'), dict(label='T3: exit or trail', price=t3, at='t3')]
    if section == 'swing':
        ex = [f"Size: quantity = your risk in rupees divided by {f(risk)} (entry minus stop). The calculator on this page does it for you.",
              f"Order: {'BUY' if up else 'SELL'} {sym} as a delivery (CNC) limit order at {f(e)}. If the day ends unfilled, cancel it and look again tomorrow. Do not chase.",
              f"Protect at once: stop-loss at {f(sl)}. For delivery trades place a GTT (OCO) with the trigger at {f(sl)} and the target at {f(t1)}.",
              f"Exit plan: half at T1 {f(t1)}, a quarter at T2 {f(t2)}, trail the rest."]
        tr = [dict(when='Order filled', action=f"Stop at {f(sl)}. It only ever moves in your favour."),
              dict(when=f"Price reaches T1 {f(t1)}", action=f"Sell half. Move the stop to entry {f(e)}: the trade is now free."),
              dict(when=f"Price reaches T2 {f(t2)}", action=f"Sell a quarter. Move the stop to T1 {f(t1)}."),
              dict(when='After T2', action=f"Trail the last quarter under each new {trig} {hl}. Exit at T3 {f(t3)}.")]
        if it.get('index_check'): tr.append(dict(when=f"{it['index_check']['sector_index']} closes below its 21 EMA (daily)", action='Sell half: the group is turning against the trade.'))
        tr.append(dict(when='Results or big news within 2 days', action='Exit or cut the size before the announcement.'))
    elif section == 'intraday':
        ex = [f"Size: quantity = risk in rupees divided by {f(risk)}. Check the margin and your daily loss limit.",
              f"Order: {side.upper()} {sym} (MIS) with a limit order at {f(e)}. Skip it if the next candle runs away without filling you.",
              f"Protect at once: SL-M at {f(sl)}.", f"Targets: half at T1 {f(t1)}, a quarter at T2 {f(t2)}, trail the rest."]
        tr = [dict(when='Order filled', action=f"Stop at {f(sl)}."), dict(when=f"Price reaches T1 {f(t1)}", action=f"Book half. Move the stop to entry {f(e)}."),
              dict(when=f"Price reaches T2 {f(t2)}", action=f"Book a quarter. Move the stop to T1 {f(t1)}."),
              dict(when='After T2', action=f"Trail under each new {trig} {hl}."), dict(when='15:10', action='Square off whatever is left. Brokers auto-square MIS around 15:15 to 15:20 and charge for it.'),
              dict(when='No progress in 8 candles', action='Exit at the market. A setup that does not move has failed.')]
    else:
        ot = it.get('options_trade') or {}; unit = ot.get('instrument', f'NIFTY {"CE" if up else "PE"}'); p0 = ot.get('premium'); psl = ot.get('premium_sl'); pt = ot.get('premium_targets') or [None] * 3
        ex = [f"Strike: buy {unit} (expiry {ot.get('expiry', '-')}). Model premium {f(p0) if p0 else '-'}; skip or size down if the live price is more than 15% above it.",
              f"Size: lots = risk in rupees divided by (premium risk per unit x lot size {ot.get('lot_size', 65)}).",
              "Order: a limit order at or near the ask when the trigger candle closes. Market orders on options can fill far from the quote.",
              f"Stop: exit if a {trig} candle closes {below} the index level {f(sl)} (option about {f(psl) if psl else '-'}).",
              f"Exit plan: half at index T1 {f(t1)} (option about {f(pt[0]) if pt[0] else '-'}), a quarter at T2 {f(t2)}, trail the rest."]
        tr = [dict(when='Order filled', action=f"Index stop {f(sl)}. Never average down."), dict(when=f"Index reaches T1 {f(t1)}", action='Sell half. Move the stop to your cost price.'),
              dict(when=f"Index reaches T2 {f(t2)}", action=f"Sell a quarter. Move the stop to the T1 level {f(t1)}."), dict(when='After T2', action=f"Trail under each new {trig} {hl}."),
              dict(when='No progress in 6 to 8 candles', action='Exit. Theta works against you every minute you wait.'), dict(when='15:10', action='Exit everything. Do not carry weekly options overnight.')]
    return dict(execution=ex, trail=tr, rules=list(rules) or ['Never widen the stop.'], marks=marks)
