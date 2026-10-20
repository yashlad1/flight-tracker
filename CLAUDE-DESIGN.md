# Design notes for reviewers

This document explains how the flight tracker works and why it is built this way, and lists what is known to be
weak, so a reviewer can suggest improvements. For user-facing docs, see `README.md`.

Built 2026-10-19 with Claude Code. Snapshot: about 1,480 lines of Python and YAML, 17 tests, no third-party
dependencies.

---

## 1. Problem

Find the cheapest **bookable** way to fly:

- Mumbai → Boston, 1 adult, landing on 18 Dec 2026 (local);
- Boston → Mumbai, 2 adults, on 26, 27 or 28 Dec 2026;

in economy, priced in USD, where each person needs **2 × 23 kg checked bags each way**, while accounting for the
2026 geopolitical situation (Iran war and Gulf hub closures, Pakistan airspace closed to Indian carriers, Houthi
attacks on Saudi airspace). Then keep watching prices until booking.

### Goals

- A true trip total: fares plus the bag fees needed to reach 2 × 23 kg, for the right number of travellers on each
  leg.
- A comparison of booking structures, because the passenger count differs by direction (1 out, 2 back).
- Risk that is visible and can be filtered, not silently baked into prices.
- Unattended runs with alerts, and history that persists between runs.
- Cheap to run and to maintain: no paid APIs, no keys, no dependencies.

### Non-goals

- Booking flights or holding fares.
- Being a general flight-search product. The code is generic over `trip.toml`, but only the 1-out / 2-back shape
  has been exercised.
- Exhaustive coverage of every itinerary. Google's top results are treated as good enough.

### User decisions that shaped it

| Date | Decision |
|---|---|
| 2026-10-19 | Exclude IndiGo, Air India, Akasa Air and Turkish Airlines on any leg |
| 2026-10-19 | No single layover longer than 3 hours (started at 10 h) |
| 2026-10-19 | Report: one table row per flight, city names only, every price split into total and per traveller, booking links |
| 2026-10-19 | No geopolitical section in the report (risk scoring stays), no full list of every flight, no subtitle, no plan explanation above the tables (it is in the README) |
| 2026-10-19 | Run on GitHub Actions instead of local cron; public repo with a GitHub Pages report link |
| 2026-10-19 | "UI is super bad": full redesign of the report (see section 7) |
| 2026-10-19 | The top of the report shows prices the way the user calculates them: 1 person out, 2 people back, and the sum, at three risk levels |
| 2026-10-19 | Second design review (6/10) applied: whole-trip receipts first, journey tables second (cards on phones), round trip + one-way collapsed, risk legend, "+$X more than the cheapest", plain wording for separate bookings, savings under $50 hidden, 44 px targets, 14 px minimum text, table captions, half-height band on phones, chart hidden until 2 days of data |
| 2026-10-19 | Remove the booking tips and footer from the report; keep it out of search engines with `<meta name=robots content="noindex, nofollow, noarchive">` (robots.txt is also published, but crawlers only read it at the domain root, which a project page can't control) |
| 2026-10-19 | Ponytail audit cuts: Plan A is computed once (`journeys`) instead of again inside `options`; `return_together` and `max_risk` removed (Plan B always keeps both travellers on one airline; the alternatives list shows every risk level); the unused price-level plumbing, the write-only `best.label` column and the naive-timestamp fallback are gone |
| 2026-10-19 | Flag return flights that are cheaper as 2 separate tickets (`mark_split_fares`: matches the 2-person and 1-person searches flight by flight; saving = together price each − 1-person price, shown only when ≥ $10), with steps to still sit together |

---

## 2. Architecture

```
               trip.toml ─────────────┐
                                      ▼
 Google Flights ◀── gflights.search ◀── tracker.searches(cfg)   (14 queries per run)
   (HTML)        │
                 ▼
          gflights.parse ──▶ Flight objects ──▶ prices.db: quotes (last 8 runs)
                                                       │
            data/baggage.json ──▶ bag_cost ─┐          ▼
            data/geo_risk.json ──▶ risk ────┼──▶ score ──▶ journeys (Plan A) + options
                         trip.toml filters ─┘                  (Plan B), per risk level
                                                       │
                       ┌───────────────────────────────┼─────────────────────┐
                       ▼                               ▼                     ▼
               prices.db: best              report.html (tables,      alert: macOS notification
               (every run)                  chart, booking links)     or "ALERT:" line → GitHub issue
```

| File | Lines | Responsibility |
|---|---|---|
| `gflights.py` | ~180 | Build the `tfs` protobuf query, fetch with retries and block detection, parse aria-labels into `Flight` |
| `tracker.py` | ~360 | Config and data loading, costing, risk, filters, plan building, SQLite, alerts, CLI |
| `render.py` | ~610 | The report page: pure functions from data to one self-contained HTML file, booking links, chart |
| `test_tracker.py` | ~270 | 17 plain-`assert` tests; runs with `python3` or `pytest` |
| `.github/workflows/track.yml` | ~65 | Schedule, tests, scrape, issue alert, commit-back, Pages deploy |

The split is deliberate: `gflights.py` knows nothing about this trip and could be reused; everything
trip-specific lives in `tracker.py` and `trip.toml`.

---

## 3. Scraping Google Flights

**Why not an API?** The official flight-search APIs need partner approval, a paid plan or an API key, and
SerpApi charges per search. This project's constraint was no keys and no cost. Google Flights also covers every
carrier on this route.

**How it works:**

1. **Query.** Google Flights encodes a search in the `tfs` URL parameter as a URL-safe base64 protobuf. The schema
   (reverse-engineered by the open-source `fast-flights` project) is small enough to hand-encode in about 20
   lines: legs (date, origin, destination), packed passenger enums, seat class, trip type. A test pins the encoder
   against a real working URL.
2. **Fetch.** A plain `urllib` GET with a desktop Chrome User-Agent and `hl=en&gl=us&curr=USD`. Results are
   server-rendered, so no browser is needed. Google sometimes returns an empty shell; `fetch` retries 3 times with
   backoff. Searches are spaced 3–7 s apart.
   - Every request sends `SOCS`, Google's "Reject all" consent cookie (the value Firefox's cookie-banner tests
     record as Reject), so a runner on an EU-style IP gets results instead of the consent wall. The value is
     untested from an EU IP: GitHub's runners and the dev machine are both in the US.
   - When a response has no results, `blocked()` checks whether it is a block page: a consent page
     (`consent.google.com` or "Before you continue"), a 429 "unusual traffic" page, or a CAPTCHA (`/sorry/` or
     `g-recaptcha`). `fetch` then raises `Blocked` at once instead of retrying into it. `tracker.scrape` logs one
     `BLOCKED by Google at <search>: <which page>` line, skips the remaining searches, and the run fails as
     incomplete. The check only runs on pages without results, because normal results pages mention reCAPTCHA
     in their scripts.
3. **Parse.** Each result has an aria-label like:
   `From 904 US dollars. 2 stops flight with JetBlue, Qatar Airways and IndiGo. Leaves … at 6:09 PM on Saturday,
   December 26 and arrives at … Total duration 22 hr 11 min. Layover (1 of 2) is a 1 hr 28 min layover at John F.
   Kennedy International Airport in New York. …`
   Regexes pull out the price, airlines, times, duration, stop count, layover durations, airport names and cities.
   Layover IATA codes come from the row text (`2 stops in JFK, DOH`). Self-transfer and separate-ticket badges are
   matched in the row text.
4. **Extras.** Google's "Prices are currently low / typical / high" signal and its live "Travel update" banner are
   captured too. The banner is shown in the risk legend; the price level is only logged, and stored in
   `quotes.level`.

**Facts established by testing (2026-10-19):**

- Prices for N adults are the **total** for N, not per person (checked by comparing 1-adult and 2-adult queries,
  and against the browser).
- Scraped prices matched the Google Flights UI exactly, checked independently in a browser.
- Requests from GitHub Actions runners (Azure IPs) return normal results.

**Fragility guards:**

- Layover codes and flags are only read when stops > 0, because a row's text window can run into the next card.
- If the number of parsed layover airports doesn't match the stop count, the risk becomes medium ("fail closed").
- An incomplete run (any search with 0 results) exits non-zero, so CI emails a failure, and it is kept out of the
  price history so the chart doesn't show a fake jump.
- A block page is named in the log instead of showing up as "0 flights" (see Fetch above).

### The inline `ds:1` JSON: evaluated, not adopted (2026-10-19)

The page also embeds the results as JSON in `AF_initDataCallback({key: 'ds:1', …})`, which the fli library
parses. A prototype parser was compared with the aria-label parser on all 14 searches of one live run: **14 of
14 identical**, 127 flights, every field equal (price, airlines, departure and arrival, duration, stops, layover
codes, minutes and airport names). The saved fixture can't be used for this, because it is a slice without the
script blocks. ds:1 was not adopted, because it isn't clearly better:

- **No gain today.** The output is identical, so switching only moves the risk.
- **It still needs the HTML.** The self-transfer and separate-ticket badges couldn't be found in ds:1: no live
  result on these routes has one (none in the last 8 stored runs either). "Prices are currently …" and the travel
  banner are HTML-only as well. Switching would mean depending on both formats instead of one.
- **It fails quietly.** If Google renumbers a field, positional indices can return plausible wrong numbers (a
  duration read as a price) that go straight into the history. The aria-label regex fails loudly: no match means
  0 flights, and the run fails.

Switch if the aria-label wording changes and ds:1 still matches. The fields, as of 2026-10-19:
`data[2][0]` holds the top results and `data[3][0]` the others, each a row `r`:

| Field | Where |
|---|---|
| price (USD total) | `r[1][0][1]` (missing for unpriced rows, e.g. some SAS results) |
| airlines | `r[0][1]` |
| segments | `r[0][2]`; stops = segments − 1 (`r[0][10]` is *not* the stop count) |
| departure | date `r[0][4]` `[y, m, d]`, time `r[0][5]` `[h, m]` (zeros are left out: `[21]` = 21:00) |
| arrival | date `r[0][7]`, time `r[0][8]` |
| duration (min) | `r[0][9]` |
| layovers | `r[0][13]`: each `[minutes, IATA, IATA, _, airport, city, …]` |

### Bag filter in `tfs` (field 13): tested, no effect (2026-10-19)

fast-flights encodes `Info.baggage = Baggage{carry_on_bags = 2, checked_bags = 3}` at field 13. One BOM→BOS
search (18 Dec, 1 adult) was fetched with no field 13, `checked_bags` 0, 1 and 2:

- Google reads the field: it echoes `[0, 1]` (carry-on 0, checked 1) back in `ds:0` for both 1 and 2 checked
  bags, so it caps the filter at one checked bag.
- **No price changed** on any of the 8 flights. KLM moved $755 → $756 between fetches, with `checked_bags = 0`
  too, so that is drift.
- With the filter on, Google drops its "Prices are currently typical" signal from the page.

So the server-rendered page doesn't add bag fees (the browser presumably reprices through the RPC, which plain HTTP
can't call), and the filter couldn't express a 2nd bag anyway. `data/baggage.json` stays the source of bag costs.

### If blocking starts

GitHub runners use Azure IPs. If `BLOCKED` lines become regular, in rough order of effort:

1. Run from a home IP instead (local cron, see the README) or a self-hosted runner.
2. Use `curl_cffi` to send Chrome's TLS fingerprint, as fli does. That is the first third-party dependency.
3. Move the price source to a paid API (SerpApi's free tier covers about 6 searches a day; see the research
   note in the kb).

The batchexecute RPC isn't an option: since Aug 2026 it needs a header only a browser can generate. Automating
`/travel/flights/booking` isn't either, because robots.txt disallows it.

---

## 4. Pricing model

### Searches per run (14)

| Kind | What | Count |
|---|---|---|
| `out` | One-way BOM→BOS, 1 adult, on 17 and 18 Dec | 2 |
| `ret` | One-way BOS→BOM, 2 adults, on 26/27/28 Dec | 3 |
| `rt` | Round trip for 1 adult, each outbound date × each return date | 6 |
| `ret_extra` | One-way BOS→BOM for the 2nd traveller, on each return date | 3 |

### Plans

- **Plan A** (`journeys`) = cheapest allowed `out` that lands on `arrive_on` + cheapest allowed `ret` on any return
  date, at each risk level (high, medium, low).
- **Plan B** (`options`) = an `rt` (outbound must land on `arrive_on`) + a `ret_extra` on the same return date and
  the round trip's first airline, so both travellers fly home together. B totals are lower bounds:
  Google's round-trip price uses its cheapest return for that outbound, and the scraper never sees which return
  flight that is.
- `options` returns the cheapest B per return date, sorted by total. The collapsed section lists them at any risk;
  each whole-trip card offers the cheapest B at its own risk level when it beats Plan A.
- History and alerts record the cheaper of A and B at the "any" and "low" levels (`best_trip`).

### Bags

```
missing = max(0, bags_per_person - lowest_fare_pieces)
fee     = missing × extra_bag_usd × travellers × directions   (directions = 2 for a round trip)
```

The rule comes from the **first airline on the itinerary that is in `baggage.json`**. That approximates the US DOT
"first marketing carrier" rule for trips to or from the US, and it skips domestic feeder carriers that aren't in
the table (e.g. JetBlue on BOS–JFK). Unknown carriers fall back to `default`.

### Per traveller

- Plan A: the receipt shows the 2-person return booking per person (return total ÷ 2).
- Plan B: each traveller's own ticket (`per_person`); the two add up to the trip total (this is tested).

### Filters

`allowed()` = stops ≤ `max_stops`, longest single layover ≤ `max_layover_hours`, and no excluded airline on any
leg. `ok()` = `allowed()` and risk ≤ the requested level.

---

## 5. Risk model

The level of an itinerary is the maximum of:

- each listed airline's level in `geo_risk.json` (whole-word, case-insensitive match);
- each layover hub's level;
- medium for a connection under 60 minutes, or when the hubs couldn't be parsed;
- high for self-transfer or separate tickets.

A transit-visa note is added when `transit_visa[hub].us_visa_exempts` is not `true`. Risk is never converted into
dollars; the report shows both "any risk" and "low risk only" so the user can weigh price against risk.

`geo_risk.json` (as of 2026-10-19) has 23 hubs, 18 airlines, 16 transit-visa rules and 17 events, with 117
sourced references. It was written by a research agent, and an independent verifier spot-checked 3 of its claims.

---

## 6. Storage

SQLite at `prices.db`, committed to git by CI:

```sql
quotes(run_at TEXT, kind TEXT, dates TEXT, pax INT, url TEXT, level TEXT, notice TEXT, flight TEXT /* JSON Flight */)
best(run_at TEXT, scope TEXT /* 'any' | 'low' */, total REAL)
```

- `quotes` keeps only the last `KEEP_RUNS` (8) runs, then runs `VACUUM`. Without pruning, about 270 runs by
  December, each committing a whole binary database, would bloat the git history.
- `best` keeps every run. It feeds the chart, the history table and the alert logic.
- New `Flight` fields get defaults so old JSON rows still load.
- `run_at` is stored in UTC with an offset (`2026-10-19T19:45:48+00:00`), and shown in Boston time. Earlier rows
  mixed Mac local time and GitHub's UTC; they were converted once on 2026-10-19.

---

## 7. Report and alerts

`render.py` builds one static page: inline CSS, an inline SVG chart, Overpass from Google Fonts, and no
JavaScript. It has a light and a dark theme (`prefers-color-scheme`).

**Design brief.** The user called the first version, a wide table, "super bad", later misread who flies which
way, and thinks in journeys: "1 person Mumbai→Boston + 2 people Boston→Mumbai = trip". So the page leads with
that sum.

- **One loud element:** an airport-signage yellow band with person pictograms, 1 flying to Boston and 2 flying
  home (half height on phones). Everything else is quiet: navy ink on cool white, Overpass, tabular figures.
- **"Whole trip" comes first**: three receipt cards (`tracker.journeys()` totals) for cheapest, cheapest without a
  high-risk flight, and lowest risk. Each is a two-line sum with a yellow total row, the extra cost compared with
  the cheapest, and booking buttons for both flights. A cheaper round trip + one-way sits inside the card in a
  `<details>`; a separate-bookings saving shows only when it is at least $50.
- **"All flights by journey"**: two tables with a hidden caption, which become cards under 600 px. Each card reads
  flight → price and risk → booking buttons.
- **"Other ways to book"**: Plan B options in a collapsed `<details>`, each opening into a ticket card.
- **Copy rules.** Risk is always written in words with a one-line legend, never colour alone. People are "person
  from Mumbai" / "person from Boston"; elsewhere it is "person" / "people". No PAX, no plan letters, no "trick".
- **Quality floor.** No horizontal scroll at 375 px, every tap target at least 44 px, text at least 14 px, focus
  outlines on every control, and one motion (the plane), off under reduced motion.

**Booking links per flight:**

- the airline's homepage (first known carrier);
- Expedia and Booking.com searches pre-filled with route, dates and traveller count (URL formats checked in a
  browser on 2026-10-19);
- the Google Flights search, which lists every seller once you click a flight.

**Alert rule:**

- a new all-time low versus all earlier runs (scope "any"); or
- the first run at or under `target_total_usd`, compared with the previous run, so it doesn't repeat every run.

On macOS the alert is an `osascript` notification. In CI, an `ALERT:` line in the log makes the workflow open a
GitHub issue.

### CI workflow

- Permissions: `contents`, `issues`, `pages` and `id-token`, all write.
- `concurrency: track`, so two runs never write `prices.db` at once.
- `bash -eo pipefail`, so `| tee` keeps the exit code.
- The commit-back and Pages steps run with `if: always()`, so partial data is still saved.

---

## 8. How it was verified

- **Unit tests (16):**
  - `tfs` encoding against a known-good URL;
  - parsing a synthetic page and a slice of a real saved Google page;
  - block-page detection (consent, 429, CAPTCHA, empty shell); `fetch` raising `Blocked` on the first block page
    without retrying, while a server error is still retried and re-raised and an empty shell still returns `""`
    after 3 tries; the consent cookie on every request;
  - nonstop rows never inherit layovers;
  - exclusions;
  - word-boundary airline lookup;
  - the bag-rule carrier choice;
  - the risk levels;
  - plan building (including the same-airline rule, the layover cap and the per-traveller split);
  - booking-link URLs;
  - pruning;
  - the rendered page (who flies which way, per-traveller arithmetic, Boston-time stamp, escaping of scraped text).
- **Live checks:**
  - 6 full runs locally (one of them in a cron-like bare environment) and 1 on GitHub Actions;
  - scraped prices compared against the Google Flights UI in a browser (exact match);
  - pre-filled Expedia and Booking.com links opened in a browser (correct route, dates and travellers; Booking.com
    showed $1,566 for 2 adults, matching Google's Lufthansa fare).
- **Review:**
  - an independent code-review agent produced 11 findings; all were addressed, except one that a browser check
    disproved;
  - an independent verifier agent passed the system end to end;
  - the redesigned page was checked in a browser at 1280 px and 375 px, in light and dark, and critiqued by a
    separate design-review agent.

---

## 9. Known weaknesses (most important first)

1. **Scraping is unofficial.** A Google markup change breaks parsing. That shows up as an incomplete run and a
   failed CI job, but it needs manual regex repair (or the switch to ds:1 described in section 3). Blocks are
   named in the log but not worked around. It is also against Google's terms of service for automated use
   (personal, low rate).
2. **Coverage is Google's top 8–12 results per search.** The browser shows more after JavaScript loads. During
   verification, one $1,191 round trip appeared in the browser but not in the scrape.
3. **Plan B is a lower bound.** The round trip's return flight is not pinned, and its risk and layover limits are
   only checked on the outbound leg.
4. **Bag fees are a flat per-bag estimate.** The model doesn't consider upgrading the fare level, which is often
   cheaper than two extra bags. Some airlines' data is low confidence. Mixed-carrier itineraries use a heuristic.
5. **Risk data is a manual snapshot.** Nothing refreshes `geo_risk.json` or `baggage.json` automatically, and there
   is no staleness warning when `as_of` gets old.
6. **History is computed under the rules in force at the time.** After a rules change (layover cap, exclusions),
   older `best` rows aren't comparable. They were recomputed by hand twice. Pruning now makes old runs impossible
   to re-score.
7. **Concurrency is single-writer.** It relies on the CI `concurrency` group; two local runs at once just
   interleave (seen once, harmless).
8. **`tracker.py` still mixes costing, storage and alerts** in one file. Page rendering moved to `render.py`.
9. **Public repo.** Route, dates, traveller counts and prices are visible. There are no names or credentials.
10. **Hard-coded airline homepages** in `AIRLINE_SITES` can go stale. Deep links into airline booking engines were
    avoided because they break often.

---

## 10. Where a reviewer could help most

1. **Coverage.** Is there a cheap, robust way to get Google's full result list (the JavaScript-loaded "other
   flights") or the booking-options page per flight, without a headless browser? Or is a second source worth
   adding (e.g. SerpApi's free tier) for cross-checking?
2. **Plan B accuracy.** Is it worth a second request per round trip to pin the return flight (Google's selected-flight
   `tfs` encoding), so B totals become exact and the return leg gets risk-checked?
3. **Bag cost model.** Should `baggage.json` model fare levels (e.g. Saver vs Flex price deltas) so the tracker
   picks "upgrade fare" versus "buy bags" automatically?
4. **Risk.** Is max-of-levels the right aggregation? Should transit-visa needs depend on each traveller's visa
   status (configurable per traveller)?
5. **Data freshness.** What is a sensible automatic refresh for `geo_risk.json` (EASA conflict-zone bulletins,
   FAA notices)? Should the report warn when `as_of` is older than N days?
6. **History.** Should `best` store the rules version (hash of `trip.toml` prefs) so the chart can mark rule
   changes instead of mixing them?
7. **Code shape.** Is splitting `tracker.py` further (pricing / storage) worth it at this size, or is one file
   easier to maintain?
8. **Alerting.** Are GitHub issues the right channel, compared with email via SMTP or a push service like ntfy?
   Should a drop of, say, 5% also alert, not just a new low?
