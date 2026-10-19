# Flight price tracker: Mumbai → Boston → Mumbai

Tracks economy fares, in US dollars, for one specific family trip. Every price includes the cost of
two 23 kg checked bags per person in each direction, and every option gets a disruption-risk rating.
It runs by itself on GitHub Actions every 6 hours and publishes a report:

**Live report: https://yashlad1.github.io/flight-tracker/**

| Journey | Travellers | Dates |
|---|---|---|
| Mumbai (BOM) → Boston (BOS) | 1 adult | must land in Boston on **Fri 18 Dec 2026** (searches 17 and 18 Dec departures) |
| Boston (BOS) → Mumbai (BOM) | 2 adults | departing **26, 27 or 28 Dec 2026** |

There are no API keys and nothing to install: the code uses only the Python standard library (3.11+).

---

## What the report shows

1. **Cheapest trip** and **cheapest low-risk trip**, each with the total for all travellers and the cost per
   traveller.
2. **Cheapest options table**: the cheapest way to book for each return date and each booking plan, within your
   risk limit (`max_risk`).
3. **Best low-risk options**: the same, using only low-risk flights.
4. **Price history**: a chart and a table of the cheapest total on every run.
5. **Where to book**: a short note at the bottom (see [Where to book](#where-to-book)).

### Reading the tables

Each trip option takes two rows, one per flight booking. Columns on the left describe the whole trip; the rest
describe one flight.

| Column | Meaning |
|---|---|
| Plan | **A** or **B**, see [Booking plans](#booking-plans) |
| Whole trip (all travellers) | Everything you pay for this option: every fare plus every bag fee |
| Whole trip per traveller | What each person's travel costs. "Both ways" is the person flying to Boston and back; "Return only" is the person flying back only. The two add up to the whole-trip total. |
| Risk | Disruption risk for this option: low, medium or high (see [Risk rating](#risk-rating)) |
| Journey | Which flight this row is, e.g. "Mumbai → Boston" |
| Travellers | How many people are on this flight booking |
| Layovers | Connecting city and how long you wait there |
| Fare | Ticket price for everyone on this booking, as shown by Google Flights |
| Bags | "included" if the cheapest fare already includes 2 × 23 kg per person, otherwise the estimated extra cost |
| Flight total (all travellers) | Fare + bags for this flight booking |
| Flight cost per traveller | Flight total ÷ travellers on it |
| Book on | Links to book: the airline's own site, Expedia, Booking.com (both pre-filled with route, date and number of travellers) and Google Flights to compare every seller |
| Notes | Why the risk is what it is, transit-visa warnings, and Plan B caveats. Hover a note for the full text. |

### Booking plans

- **Plan A**: one one-way ticket for the traveller flying to Boston, plus one booking for both travellers back.
- **Plan B**: a round-trip ticket for the traveller flying to Boston, plus a separate one-way ticket back for the
  second traveller, on the same airline. Round trips that start in India are sometimes cheaper than two one-ways.
  Plan B prices are "from" prices: Google pairs the round trip with its cheapest return flight. Before booking,
  price the exact return flight both travellers will share.

### Where to book

Use the airline's own website when its price is within about $50 of the travel agencies:

- If a flight is cancelled or rerouted (a real possibility this winter), you deal with the airline directly.
- Adding bags or moving up a fare level to get 2 × 23 kg is easier on the airline's site, and often cheaper
  than paying for extra bags.
- The US 24-hour rule lets you cancel for free within 24 hours of booking, if you book at least 7 days before
  departure.

Expedia or Booking.com can be slightly cheaper, but changes and refunds then go through the agency, which is
slower when flights are disrupted. "Compare all (Google)" opens the Google Flights search; clicking a flight there
lists every site selling it with its price. For Plan B, book both tickets on the same airline's site.

---

## Running it

### Automatically (GitHub Actions)

`.github/workflows/track.yml` runs at 00:00, 06:00, 12:00 and 18:00 UTC. Each run:

1. runs the self-check tests;
2. runs 14 Google Flights searches (about 90 seconds, with polite pauses between them);
3. opens a GitHub issue, which GitHub emails you, on a new all-time low or the first time the cheapest trip drops
   to `target_total_usd`;
4. commits `prices.db` and `report.html` back to the repo;
5. publishes the report to GitHub Pages.

If Google returns nothing for any search, the run fails and GitHub emails you about the failure.

To run it now: **Actions → Track fares → Run workflow**, or

```bash
gh workflow run track.yml --repo yashlad1/flight-tracker
```

### On your own computer

```bash
python3 tracker.py            # scrape, store, write report.html, alert
python3 tracker.py --report   # rebuild report.html from the last stored run, no scraping
python3 test_tracker.py       # self-check
open report.html
```

On a Mac, alerts show as macOS notifications. To schedule it locally instead of on GitHub:

```bash
(crontab -l 2>/dev/null; echo "0 */6 * * * cd $HOME/Development/flight-tracker && /opt/homebrew/bin/python3 tracker.py >> tracker.log 2>&1") | crontab -
```

---

## Configuration (`trip.toml`)

Change the trip here; no code changes are needed. After editing, run `python3 tracker.py --report` to see the
effect on the last stored prices, or wait for the next run.

| Key | Current value | What it does |
|---|---|---|
| `title` | Mumbai → Boston → Mumbai price tracker | Report heading |
| `cities` | BOM = Mumbai, BOS = Boston | Names used for journeys in the report |
| `outbound.from` / `to` | BOM / BOS | Outbound airports (IATA codes) |
| `outbound.depart_dates` | 17 and 18 Dec | Departure dates to search |
| `outbound.arrive_on` | 2026-12-18 | Outbound flights must land on this local date |
| `outbound.adults` | 1 | Travellers flying out |
| `return.from` / `to` | BOS / BOM | Return airports |
| `return.depart_dates` | 26, 27, 28 Dec | Return dates to search |
| `return.adults` | 2 | Travellers flying back |
| `prefs.bags_per_person` | 2 | 23 kg checked bags each person needs, each direction |
| `prefs.max_stops` | 2 | Most stops allowed on one journey |
| `prefs.max_layover_hours` | 3 | Skip any itinerary with a single layover longer than this |
| `prefs.return_together` | true | Plan B: both return travellers must be on the same airline |
| `prefs.max_risk` | high | Highest risk shown in "Best options" (low, medium or high) |
| `prefs.exclude_airlines` | IndiGo, Air India, Akasa Air, Turkish Airlines | Drop any itinerary that uses one of these on any flight |
| `prefs.target_total_usd` | 2600 | Alert the first time the cheapest whole trip drops to this |

---

## How prices are calculated

- **Fares** come from Google Flights in USD, and are totals for everyone on the booking.
- **Bags**: `data/baggage.json` lists, per airline, how many 23 kg bags the cheapest economy fare includes on
  India–US routes and the cost of each extra bag. Extra cost = missing bags per person × fee × travellers ×
  directions (2 for a round trip). The rule used is the first airline on the itinerary that is in the file; for
  trips to or from the US, the first airline's bag rules usually apply.
- **Per traveller**: Plan A splits the return booking evenly between the two travellers. Plan B gives each
  traveller their own ticket.

## Risk rating

Each option's risk is the highest of:

- the airline's and each connecting airport's level in `data/geo_risk.json` (for example, Gulf hubs are high
  because of the 2026 Iran war, European hubs are low);
- **medium** for a connection under 60 minutes, or when the connecting airports couldn't be read;
- **high** for self-transfer or separate-ticket itineraries, because bags aren't checked through.

Notes also flag connecting airports where an Indian passport holder needs a transit visa even with a US visa.

---

## Data files

| File | What it holds | Refresh |
|---|---|---|
| `data/baggage.json` | Bag allowance and extra-bag fee per airline, with sources and confidence | Before booking, and every few weeks |
| `data/geo_risk.json` | Risk level per hub and airline, transit-visa rules and tracked events, with sources | Every few weeks, or after major news |
| `prices.db` | SQLite: raw quotes for the last 8 runs, plus the best total from every run | Written by every run |
| `fixtures/` | A saved slice of a real Google Flights page, used by the tests | When Google's page layout changes |

Both JSON files are snapshots dated 2026-10-19 (`as_of`). Asking Claude to "refresh data/geo_risk.json" or
"refresh data/baggage.json" works.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| GitHub emails "run failed", report shows "Incomplete run" | Google changed its page or blocked the runner | Open the run log; if every search found 0 flights, check the regexes in `gflights.py` against a saved page |
| A search sometimes finds 0 flights | Google served an empty page | The scraper already retries 3 times; occasional misses are normal |
| No alert issue was opened | Price isn't a new low, or it was already under target last run | Expected |
| Report looks stale | The Pages deploy failed | Re-run the workflow |

## Limitations

- Google's server-rendered page lists only its top 8–12 results per search. That usually includes the cheapest
  fare, but not every flight.
- Bag fees are estimates. Some airlines' figures are low confidence (see each entry's `note` in
  `data/baggage.json`).
- Plan B's return flight for the round-trip traveller isn't priced individually (see [Booking plans](#booking-plans)).
- Prices change by the minute. Always confirm on the booking site before paying.
- This scrapes Google Flights for personal use at a low request rate.

## Project layout

```
gflights.py        Google Flights query builder, fetcher and parser
tracker.py         searches, pricing, risk, storage, report, alerts, CLI
trip.toml          the trip and preferences
test_tracker.py    self-check (python3 test_tracker.py, or pytest)
data/              baggage.json, geo_risk.json
fixtures/          saved Google Flights page slice for tests
.github/workflows/ track.yml (schedule, issue alerts, Pages)
prices.db          price history (committed by CI)
report.html        latest report (committed by CI, published to Pages)
CLAUDE-DESIGN.md   design notes for reviewers
```
