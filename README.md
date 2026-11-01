# DownerStuffScreener kit

A stock scanner for Indian markets that runs on GitHub for free and shows its results as a dashboard on your phone or laptop. You decide the trading logic: it lives in one file, `strategy.py`, and the dashboard adapts to whatever rules you write.

It ships with a working strategy (EMA Trend Pullback) and two more in `examples/`. Use one of them as is, change its numbers, or write your own. See **STRATEGY_GUIDE.md**.

## What you get

| Page | What it shows |
|---|---|
| **Overview** | Market regime, today's event risks, the best setups from every section, headlines |
| **Swing** | Nifty 500 stocks that match your swing rules (long only by default), checked against their sector index |
| **Options** | Nifty 50 call and put setups from your options rules, with a strike picked using the Greeks |
| **Intraday** | The most liquid Nifty 500 stocks that match your intraday rules, long and short |
| **Market** | Trending, range-bound or volatile; India VIX expected move; breadth; sector strength |
| **News** | Headlines, expiry days, holidays, policy meetings, results dates of your setups |
| **Trade** (tap any row) | Chart with entry, stop and targets, every rule ticked or crossed, position size, how to execute and trail |

Each screener page has a **How this list is built** card that lists the rules the scanner actually ran, so anyone looking at your dashboard can see your logic.

## Set it up (GitHub website only, no git needed)

1. **Create a new repository** (in your account or your organisation). Make a fresh repository rather than a fork: GitHub does not run scheduled scans on forks by default.
2. **Upload the files.** Repository → *Add file* → *Upload files*. Drag in everything from this folder, including the hidden `.github` folder (on a Mac press Cmd + Shift + . in Finder to see it). Commit.
3. **Turn on Pages.** Settings → Pages → *Source*: **GitHub Actions**.
4. **Phone alerts (optional).** Install the free **ntfy** app and subscribe to a long random topic name, for example `scanner-k8d2x9q4`. Then Settings → Secrets and variables → Actions:
   - Secret `NTFY_TOPIC` = your topic name. Anyone who knows the name can read your pushes, so keep it random.
   - Variable `PAGE_URL` = your dashboard address, e.g. `https://<owner>.github.io/<repo>/`. Tapping a push opens it.
5. **First run.** Actions → **scan** → *Run workflow* → mode **all**. It takes a few minutes. After that it runs on its own every weekday.
6. Open `https://<owner>.github.io/<repo>/` and add it to your home screen.

### Optional repository variables

| Variable | Default | What it does |
|---|---|---|
| `STRATEGY_FILE` | `strategy.py` | Run another strategy file, e.g. `examples/breakout.py` |
| `APP_NAME` | `DownerStuffScreener` | Name shown in phone pushes |
| `NTFY_MIN_SCORE` | `6` | Only push setups with this score or higher (6 = grade A) |
| `NTFY_STATUSES` | `TRIGGER` | Which statuses push. `TRIGGER,WATCH` adds setups that are waiting for the trigger |
| `NTFY_UPDATES` | `swing` | "Scan updated" pushes: `swing` (hourly), `all` (every scan, about 150 a day) or `off` |

### Notes for organisations

- If the first run fails at *deploy*, an organisation policy is probably blocking it. Check Organisation settings → Actions (allowed actions and workflow permissions) and any protection rules on the `github-pages` environment.
- **Public repository:** Actions minutes are free. Your dashboard is public too.
- **Private repository:** the 5-minute schedule uses a lot of Actions minutes (roughly 80 runs per trading day), well beyond the free allowance, and Pages on a private repository needs a paid plan. If you only use swing, delete the three 5-minute `cron` lines in `.github/workflows/scan.yml`: that cuts it to about 8 runs a day.

## Change the logic

Open `strategy.py` on GitHub, click the pencil, edit, commit. The next scan runs your new rules. Before every scan the workflow runs `check_strategy.py`: if your edit has a mistake, the run stops with a message naming the line, and your last good dashboard stays online. Full guide: **STRATEGY_GUIDE.md**.

To switch to a ready-made strategy, either copy a file from `examples/` over `strategy.py`, or set the repository variable `STRATEGY_FILE` to its path.

## Make it yours

- **Name and footer:** `site/config.js`.
- **Home-screen name:** `"name"` and `"short_name"` in `site/manifest.webmanifest`, and `apple-mobile-web-app-title` in the `site/*.html` files.
- **Push name:** the `APP_NAME` variable.
- **Holidays and events:** `events.json`. It lists holidays and events to the end of 2026 plus one in February 2027. Add the next year's NSE holidays from the NSE circular, because the weekly expiry date is worked out from them.
- **Stock list:** the Nifty 500 list is downloaded live. If that fails it uses `nifty500.csv` if you upload one (from niftyindices.com), and otherwise the short `watchlist.txt`.

## Schedule (IST, Monday to Friday)

| What | How often |
|---|---|
| Options, intraday and market pages | every 5 minutes, 09:17 to 15:32 |
| Swing page | every hour at about :25 (after each 1H candle closes), plus 08:37 and 16:17 |
| News and events | about every 30 minutes |

GitHub often starts scheduled runs 5 to 30 minutes late at busy times. The pages refresh themselves every minute while the market is open, and the "Updated" pill turns red when a section is stale. After 60 days without a commit GitHub pauses scheduled runs: click *Enable* on the Actions tab.

## Files

| File | Edit it? | What it is |
|---|---|---|
| `strategy.py` | **yes** | Your rules, settings and risk rules |
| `examples/` | copy from | Ready-made strategies and a blank template |
| `events.json` | yes | Holidays and market events |
| `watchlist.txt` | optional | Backup stock list |
| `site/config.js` | optional | Dashboard name and footer |
| `STRATEGY_GUIDE.md` | read | How to write rules |
| `check_strategy.py` | no | Tests your strategy before each scan |
| `scanner.py` | no | The engine: data, sections, page data |
| `strategy_api.py`, `indicators.py` | no | The tools your rules use |
| `explain.py`, `greeks.py`, `market.py`, `newsfeed.py`, `notify.py`, `sector_index.py` | no | Trade explanations, option strikes, market regime, news, alerts, sector check |
| `site/` | no | The dashboard |
| `tests/` | no | Tests for the engine (`python tests/run_all.py`) |

## Limits

- Prices come from Yahoo Finance, which is unofficial and can be delayed. Scanning 500 symbols can be rate-limited. A failed run keeps the last good page.
- The Nifty index has no volume data here, so options rules cannot use volume.
- Option premiums are model prices (Black-Scholes with India VIX). Always compare with the live option chain.
- Results dates come from Yahoo and are often missing for NSE stocks. Check the exchange announcements.
- A scan finds candidates that match rules. It is not a trade signal and not investment advice.
