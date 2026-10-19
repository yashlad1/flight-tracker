# flight-tracker

Tracks economy fares, in USD, for:

- **BOM → BOS**, 1 adult, landing in Boston on **18 Dec 2026** (searches 17 and 18 Dec departures)
- **BOS → BOM**, 2 adults, departing **26, 27 or 28 Dec 2026**

Every option is costed with **2 × 23 kg checked bags per person, each direction**, whether they are
included in the fare or cost extra. Each option is also scored for **geopolitical and connection risk**:
airspace closures, Gulf/Europe hub disruption, transit-visa rules, tight connections and self-transfers.

The scraper uses only the Python standard library (3.11+): no pip installs, no API keys, no browser.

## Run

```bash
python3 tracker.py            # scrape (~14 searches, ~1.5 min), store, write report.html, alert on new low
python3 tracker.py --report   # rebuild report.html from the last run (e.g. after editing data/*.json)
python3 test_tracker.py       # self-check
open report.html
```

Edit `trip.toml` to change dates, passenger counts, max stops, the risk filter, or the alert target.

## Schedule it (GitHub Actions, every 6 hours)

`.github/workflows/track.yml` runs the tracker on GitHub's servers at 00:00, 06:00, 12:00 and 18:00 UTC. Your Mac
doesn't need to be on. Each run:

- runs the self-check, then scrapes;
- opens a GitHub issue (GitHub emails you) on a new low, or the first time the total drops to `target_total_usd`;
- commits `prices.db` and `report.html` back to the repo, so history survives between runs;
- publishes the report to GitHub Pages.

For a run right now: **Actions → Track fares → Run workflow**, or `gh workflow run track.yml`.

The latest report is published at **https://yashlad1.github.io/flight-tracker/**. This repo is public, so
anyone with the link can see the routes, dates and prices.

If Google returns nothing, the run fails and GitHub emails you. That usually means Google is blocking cloud IPs.
The fallback is a local cron job:

```bash
(crontab -l 2>/dev/null; echo "0 */6 * * * cd $HOME/Development/flight-tracker && /opt/homebrew/bin/python3 tracker.py >> tracker.log 2>&1") | crontab -
```

## How it works

| File | Role |
|---|---|
| `gflights.py` | Builds Google Flights' protobuf `tfs` query, fetches the server-rendered page and parses each result's aria-label (price, airlines, times, layover airports, warnings) |
| `tracker.py` | Runs the searches, stores every quote in `prices.db` (SQLite), builds the best combinations, writes `report.html`, sends alerts |
| `data/baggage.json` | Bags included in each airline's cheapest India↔US economy fare, plus the fee per missing 23 kg bag |
| `data/geo_risk.json` | Risk for each hub and airline, transit-visa rules and current events, with sources |

The tracker compares two ways to book:

- **A**: a one-way ticket out for 1 adult, plus a one-way ticket back for 2 adults on one booking.
- **B**: a round trip for the traveller flying out, plus a one-way back for the second traveller. When it can, the
  tracker picks the same airline for both; book them onto the same return flight. Round trips that start in India
  are often cheaper than two one-ways.

Bag fees follow the first airline listed that is in `baggage.json`. For trips to or from the US, the first
marketing carrier's bag rules usually apply. On a mixed-carrier trip, hover the Bags cell to see which rule
was used, and confirm at booking.

## Keeping it honest

- `data/geo_risk.json` and `data/baggage.json` are snapshots (see `as_of`). Re-check them before you book,
  and refresh them every few weeks. Asking Claude to "refresh geo_risk.json" works.
- Google Flights prints about 8 "top" results per search. That covers the cheapest fare, but not every flight.
- This is personal-use scraping at a low request rate. If Google changes its markup, live searches come back
  empty. The report then shows an "Incomplete run" banner, and the run stays out of the price history. Fix the
  regexes in `gflights.py` first.
- Strategy B totals are "from" prices. Before booking, price the exact return flight both travellers will share.
- When run locally on a Mac, alerts are macOS notifications. In GitHub Actions, they are GitHub issues.
