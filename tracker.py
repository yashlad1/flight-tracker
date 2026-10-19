#!/usr/bin/env python3
"""Flight price tracker for the trip in trip.toml.

Strategy A: one-way out (outbound adults) + one-way back (return adults, one booking).
Strategy B: round trip for the outbound adults + one-way back for the extra return adults.
Every option is costed with 2x23kg bags (data/baggage.json) and scored for
geopolitical / connection risk (data/geo_risk.json).

  python3 tracker.py            scrape, store, report, alert
  python3 tracker.py --report   rebuild report.html from the latest stored run
"""
import argparse
import html
import json
import random
import re
import sqlite3
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import gflights
from gflights import Flight

HERE = Path(__file__).resolve().parent
LEVELS = ["low", "medium", "high"]


def load():
    cfg = tomllib.loads((HERE / "trip.toml").read_text())
    bags = json.loads((HERE / "data/baggage.json").read_text())
    geo = json.loads((HERE / "data/geo_risk.json").read_text())
    # fail at load, with the culprit named, rather than after a 1.5 min scrape
    for section in ("hubs", "airlines"):
        for k, v in geo.get(section, {}).items():
            v["level"] = str(v.get("level", "")).lower()
            if v["level"] not in LEVELS:
                sys.exit(f"data/geo_risk.json {section}.{k}: level must be one of {LEVELS}")
    for k, v in [("default", bags["default"]), *bags["airlines"].items()]:
        if not all(isinstance(v.get(x), (int, float)) for x in ("lowest_fare_pieces", "extra_bag_usd")):
            sys.exit(f"data/baggage.json {k}: lowest_fare_pieces and extra_bag_usd must be numbers")
    return cfg, bags, geo


def lookup(table, name):
    """Airline table lookup: exact (case-insensitive) first, then whole-word containment either
    way ("American" ~ "American Airlines", but "ANA" !~ "Air Canada")."""
    n = name.casefold()
    for k, v in table.items():
        if k.casefold() == n:
            return v
    word = lambda a, b: re.search(rf"\b{re.escape(a)}\b", b)
    for k, v in table.items():
        if word(k.casefold(), n) or word(n, k.casefold()):
            return v
    return None


# --- costing ---------------------------------------------------------------
def bag_cost(f, pax, need, bags, legs=1):
    """USD to bring every passenger up to `need` x 23kg. Uses the first listed airline we
    know (segment order ~ first marketing carrier, whose rules apply to US-origin trips)."""
    carrier = next((a for a in f.airlines if lookup(bags["airlines"], a)), None)
    rule = lookup(bags["airlines"], carrier) if carrier else bags["default"]
    missing = max(0, need - rule["lowest_fare_pieces"])
    return missing * rule["extra_bag_usd"] * pax * legs, carrier or "unknown airline"


def risk(f, geo):
    lvl, notes = 0, []
    for a in f.airlines:
        r = lookup(geo.get("airlines", {}), a)
        if r:
            lvl = max(lvl, LEVELS.index(r["level"]))
            if r["level"] != "low":
                notes.append(f"{a}: {r['note']}")
    cities = dict(zip(f.layovers, (n.split(", ")[-1] for n in f.layover_names)))
    for code in f.layovers:
        where = f"{cities[code]} ({code})" if code in cities else code
        r = geo.get("hubs", {}).get(code)
        if r:
            lvl = max(lvl, LEVELS.index(r["level"]))
            if r["level"] != "low":
                notes.append(f"{where}: {r['note']}")
        t = geo.get("transit_visa", {}).get(code)
        if t and t.get("us_visa_exempts") is not True:
            notes.append(f"{where} transit: {t['indian_passport']}")
    for m in f.layover_min:
        if m < 60:
            lvl = max(lvl, 1)
            notes.append(f"tight {m} min connection")
        elif m >= 360:
            notes.append(f"{m // 60}h {m % 60}m layover")
    if f.stops and len(f.layovers) != f.stops:        # fail closed: unknown hubs aren't "low"
        lvl = max(lvl, 1)
        notes.append("layover airports not parsed")
    if f.flags:
        lvl = 2
        notes += [f"{x}: bags not checked through" for x in f.flags]
    return LEVELS[lvl], notes


def score(f, pax, cfg, bags, geo, legs=1):
    fee, carrier = bag_cost(f, pax, cfg["prefs"]["bags_per_person"], bags, legs)
    lvl, notes = risk(f, geo)
    return {"f": f, "pax": pax, "fare": f.price, "bags": fee, "bag_rule": carrier,
            "total": f.price + fee, "risk": lvl, "notes": notes}


def excluded(f, cfg):
    banned = {a: True for a in cfg["prefs"].get("exclude_airlines", [])}
    return any(lookup(banned, a) for a in f.airlines)


def allowed(f, cfg):
    """Trip preferences: stops, longest single layover, excluded airlines."""
    p = cfg["prefs"]
    return (f.stops <= p["max_stops"] and max(f.layover_min, default=0) <= p.get("max_layover_hours", 99) * 60
            and not excluded(f, cfg))


def ok(s, max_risk, cfg):
    return LEVELS.index(s["risk"]) <= LEVELS.index(max_risk) and allowed(s["f"], cfg)


def options(quotes, cfg, bags, geo, max_risk):
    """Best option per return date for each strategy. quotes: {(kind, dates): (flights, pax, url)}."""
    out, ret = cfg["outbound"], cfg["return"]
    lands = out["arrive_on"]

    def scored(kind, dates, legs=1):
        flights, pax, url = quotes.get((kind, dates), ([], 0, ""))
        return [dict(score(f, pax, cfg, bags, geo, legs), url=url) for f in flights]

    best_out = min((s for d in out["depart_dates"] for s in scored("out", d)
                    if s["f"].arrive.startswith(lands) and ok(s, max_risk, cfg)),
                   key=lambda s: s["total"], default=None)
    rows = []
    for d2 in ret["depart_dates"]:
        back = min((s for s in scored("ret", d2) if ok(s, max_risk, cfg)), key=lambda s: s["total"], default=None)
        if best_out and back:
            rows.append({"strategy": "A", "dates": f"{best_out['f'].depart[:10]} > {d2}",
                         "legs": [("Out", out["adults"], best_out), ("Back", ret["adults"], back)],
                         "total": best_out["total"] + back["total"],
                         # everyone flying out also flies back; the rest fly back only
                         "per_person": [("Both ways", best_out["total"] / out["adults"] + back["total"] / ret["adults"]),
                                        ("Return only", back["total"] / ret["adults"])],
                         "risk": max(best_out["risk"], back["risk"], key=LEVELS.index), "note": ""})
        extra = [s for s in scored("ret_extra", d2) if ok(s, max_risk, cfg)]
        for d1 in out["depart_dates"]:
            for rt in scored("rt", f"{d1}>{d2}", legs=2):
                if not (rt["f"].arrive.startswith(lands) and ok(rt, max_risk, cfg) and extra):
                    continue
                same = [s for s in extra if s["f"].airlines[0] == rt["f"].airlines[0]]
                if not same and cfg["prefs"].get("return_together", True):
                    continue
                partner = min(same or extra, key=lambda s: s["total"])
                rows.append({"strategy": "B", "dates": f"{d1} > {d2}",
                             "legs": [("Round trip", out["adults"], rt),
                                      ("Back (extra)", ret["adults"] - out["adults"], partner)],
                             "total": rt["total"] + partner["total"],
                             "per_person": [("Both ways", rt["total"] / out["adults"]),
                                            ("Return only", partner["total"] / partner["pax"])],
                             "risk": max(rt["risk"], partner["risk"], key=LEVELS.index),
                             "note": "round-trip return leg not pinned: total is Google's cheapest pairing, "
                                     "price the exact return flight before booking"
                                     + ("" if same else "; extra traveller is on a different airline")})
    # keep the cheapest B per return date
    best = {}
    for r in rows:
        k = (r["strategy"], r["dates"][-10:])
        if k not in best or r["total"] < best[k]["total"]:
            best[k] = r
    return sorted(best.values(), key=lambda r: r["total"])


# --- storage ---------------------------------------------------------------
def db():
    con = sqlite3.connect(HERE / "prices.db")
    con.execute("CREATE TABLE IF NOT EXISTS quotes(run_at TEXT, kind TEXT, dates TEXT, pax INT,"
                " url TEXT, level TEXT, notice TEXT, flight TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS best(run_at TEXT, scope TEXT, total REAL, label TEXT)")
    return con


def searches(cfg):
    """[(kind, dates, legs, adults)] for one tracker run."""
    out, ret = cfg["outbound"], cfg["return"]
    s = [("out", d, [(d, out["from"], out["to"])], out["adults"]) for d in out["depart_dates"]]
    s += [("ret", d, [(d, ret["from"], ret["to"])], ret["adults"]) for d in ret["depart_dates"]]
    if ret["adults"] > out["adults"]:
        s += [("rt", f"{d1}>{d2}", [(d1, out["from"], out["to"]), (d2, ret["from"], ret["to"])], out["adults"])
              for d1 in out["depart_dates"] for d2 in ret["depart_dates"]]
        s += [("ret_extra", d, [(d, ret["from"], ret["to"])], ret["adults"] - out["adults"])
              for d in ret["depart_dates"]]
    return s


def scrape(cfg, con):
    run_at = datetime.now().isoformat(timespec="seconds")
    for i, (kind, dates, legs, pax) in enumerate(searches(cfg)):
        if i:
            time.sleep(3 + random.random() * 4)     # be polite; Google throttles bursts
        try:
            flights, level, notice, url = gflights.search(legs, pax)
        except Exception as e:                      # one bad search must not sink the run
            print(f"  {kind} {dates}: FAILED {e!r}", file=sys.stderr, flush=True)
            continue
        print(f"  {kind:9} {dates:23} {pax} pax: {len(flights)} flights, "
              f"from ${min((f.price for f in flights), default=0):,} (Google says {level})", flush=True)
        con.executemany("INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)",
                        [(run_at, kind, dates, pax, url, level, notice, json.dumps(asdict(f))) for f in flights])
        con.commit()
    return run_at


def latest(con, run_at=None):
    run_at = run_at or con.execute("SELECT max(run_at) FROM quotes").fetchone()[0]
    quotes, levels, notices = {}, {}, set()
    for kind, dates, pax, url, level, notice, fj in con.execute(
            "SELECT kind, dates, pax, url, level, notice, flight FROM quotes WHERE run_at=?", (run_at,)):
        quotes.setdefault((kind, dates), ([], pax, url))[0].append(Flight(**json.loads(fj)))
        levels[(kind, dates)] = level
        notices.add(notice)
    return run_at, quotes, levels, notices - {None}


# --- report ----------------------------------------------------------------
def hm(minutes):
    return f"{minutes // 60}h {minutes % 60:02d}m"


def when(iso):
    return datetime.fromisoformat(iso).strftime("%a %d %b %H:%M")


LEG_HEAD = ("<th>Airline</th><th>Departs</th><th>Arrives</th><th>Duration</th><th>Layovers</th>"
            "<th class=num>Fare</th><th class=num>Bags</th><th class=num>Leg total<br>(all pax)</th>"
            "<th class=num>Leg per<br>person</th>")


def leg_cells(s):
    """The LEG_HEAD columns for one scored flight."""
    f = s["f"]
    names = f.layover_names or f.layovers                  # runs stored before names were parsed
    lay = ("<br>".join(f"{html.escape(n)} ({html.escape(c)}) &middot; {hm(m)}"
                       for n, c, m in zip(names, f.layovers, f.layover_min)) if f.stops else "Nonstop")
    return (f"<td><a href='{html.escape(s['url'])}'>{html.escape(', '.join(f.airlines))}</a></td>"
            f"<td class=nw>{when(f.depart)}</td><td class=nw>{when(f.arrive)}</td><td class=nw>{hm(f.duration_min)}</td>"
            f"<td class=lay>{lay}</td><td class=num>${s['fare']:,.0f}</td>"
            f"<td class=num title='{html.escape('bag rule: ' + s['bag_rule'])}'>{bag_txt(s['bags'])}</td>"
            f"<td class=num>${s['total']:,.0f}</td><td class=num>${s['total'] / s['pax']:,.0f}</td>")


def pill(level):
    return f"<span class='pill {level}'>{level}</span>"


def notes_html(notes):
    """One short line per note; the full sentence is on hover."""
    short = lambda n: n if len(n) <= 48 else n[:45].rstrip() + "..."
    return "<br>".join(f"<span title='{html.escape(n)}'>{html.escape(short(n))}</span>" for n in notes)


def bag_txt(fee):
    return "included" if not fee else f"+${fee:,.0f}"


def per_person_html(r):
    return "<br>".join(f"{who}: <b>${cost:,.0f}</b>" for who, cost in r["per_person"])


def rows_html(opts):
    """One row per flight leg; option-level cells span the option's legs."""
    if not opts:
        return "<p class=muted>No option matched.</p>"
    out = ["<div class=scroll><table><tr><th>#</th><th>Plan</th><th>Leg</th><th class=num>Pax</th>"
           f"{LEG_HEAD}<th class=num>Trip total<br>(everyone)</th><th class=num>Trip cost<br>per person</th>"
           "<th>Risk</th><th>Notes</th></tr>"]
    for i, r in enumerate(opts, 1):
        n = len(r["legs"])
        for j, (name, pax, s) in enumerate(r["legs"]):
            notes = s["notes"] + ([r["note"]] if r["note"] and j == 0 else [])
            head = (f"<td rowspan={n}>{i}</td><td rowspan={n}>{r['strategy']}</td>" if j == 0 else "")
            tail = (f"<td rowspan={n} class=num><b>${r['total']:,.0f}</b></td>"
                    f"<td rowspan={n} class=num>{per_person_html(r)}</td><td rowspan={n}>{pill(r['risk'])}</td>"
                    if j == 0 else "")
            out.append(f"<tr class='{'first' if j == 0 else ''}'>{head}<td class=nw>{name}</td><td class=num>{pax}</td>"
                       f"{leg_cells(s)}{tail}<td class=small>{notes_html(notes)}</td></tr>")
    return "\n".join(out + ["</table></div>"])


def chart(con):
    hist = con.execute("SELECT run_at, scope, total FROM best ORDER BY run_at").fetchall()
    runs = sorted({h[0] for h in hist})
    if len(runs) < 2:
        return "<p class=muted>Price history appears after the second run.</p>"
    W, H, L, R, T, B = 720, 220, 56, 120, 12, 28
    vals = [h[2] for h in hist]
    lo, hi = min(vals) * 0.97, max(vals) * 1.03
    x = lambda i: L + i * (W - L - R) / (len(runs) - 1)
    y = lambda v: T + (hi - v) * (H - T - B) / (hi - lo)
    svg = [f"<svg viewBox='0 0 {W} {H}' role=img aria-label='Best total price per run'>"]
    for k in range(5):
        v = lo + k * (hi - lo) / 4
        svg.append(f"<line x1={L} x2={W - R} y1={y(v):.1f} y2={y(v):.1f} class=grid />"
                   f"<text x={L - 6} y={y(v) + 4:.1f} class=tick text-anchor=end>${v / 1000:.1f}K</text>")
    for i in (0, len(runs) - 1):
        svg.append(f"<text x={x(i):.1f} y={H - 8} class=tick text-anchor=middle>{runs[i][5:16].replace('T', ' ')}</text>")
    for n, (scope, name) in enumerate((("any", "Any risk"), ("low", "Low risk only"))):
        pts = [(runs.index(r), t) for r, s, t in hist if s == scope]
        if not pts:
            continue
        path = " ".join(f"{'M' if j == 0 else 'L'}{x(i):.1f},{y(t):.1f}" for j, (i, t) in enumerate(pts))
        svg.append(f"<path d='{path}' class='line s{n + 1}' />")
        svg += [f"<circle cx={x(i):.1f} cy={y(t):.1f} r=4 class='dot s{n + 1}'><title>{name}: ${t:,.0f} "
                f"({runs[i][:16]})</title></circle>" for i, t in pts]
        i, t = pts[-1]
        svg.append(f"<text x={x(i) + 8:.1f} y={y(t) + 4:.1f} class=lbl>{name} ${t:,.0f}</text>")
    return "".join(svg) + "</svg>"


CSS = """
:root{color-scheme:light;--bg:#fcfcfb;--fg:#0b0b0b;--muted:#52514e;--line:#e4e3df;--s1:#2a78d6;--s2:#eb6834;
--low:#1c7c4a;--medium:#9a6400;--high:#c2302f}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#1a1a19;--fg:#f0efec;--muted:#c3c2b7;--line:#33322f;
--s1:#3987e5;--s2:#d95926;--low:#4fbf85;--medium:#e0a33a;--high:#f07070}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1480px;padding:16px}
a{color:inherit}table{border-collapse:collapse;width:100%;margin:8px 0 20px}th,td{border-bottom:1px solid var(--line);
padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}.muted,.small{color:var(--muted)}
.small{font-size:12px}.nw{white-space:nowrap}td{white-space:normal}.pill{border:1px solid currentColor;border-radius:9px;padding:0 7px;font-size:12px}
.pill.low{color:var(--low)}.pill.medium{color:var(--medium)}.pill.high{color:var(--high)}
.kpis{display:flex;gap:24px;flex-wrap:wrap}.kpi>b{display:block;font-size:28px}.kpi span{display:block}
svg{width:100%;max-width:720px}.grid{stroke:var(--line);stroke-width:1}.tick,.lbl{fill:var(--muted);font-size:11px}
.lbl{fill:var(--fg)}.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.line.s1{stroke:var(--s1)}.line.s2{stroke:var(--s2)}.dot{stroke:var(--bg);stroke-width:2}.dot.s1{fill:var(--s1)}
.dot.s2{fill:var(--s2)}.key{display:inline-block;width:14px;height:3px;vertical-align:middle;margin:0 4px 0 12px}
.scroll{overflow-x:auto}.lay{min-width:190px;max-width:240px}.num{text-align:right;white-space:nowrap}td.small{white-space:nowrap}
tr.first td{border-top:2px solid var(--line)}details{margin:6px 0}summary{cursor:pointer}
"""


def missing(cfg, quotes):
    """Searches of this run that returned nothing (failed, throttled or no flights)."""
    return [f"{k} {d}" for k, d, _, _ in searches(cfg) if (k, d) not in quotes]


SEARCH_NAMES = {"out": "One-way out", "ret": "One-way back", "rt": "Round trip", "ret_extra": "One-way back (extra)"}


def evaluate(con, cfg, bags, geo, run_at=None):
    run_at, quotes, levels, notices = latest(con, run_at)
    if run_at is None:
        sys.exit("No stored runs yet: run `python3 tracker.py` first.")
    return run_at, quotes, levels, notices, options(quotes, cfg, bags, geo, cfg["prefs"]["max_risk"]), \
        options(quotes, cfg, bags, geo, "low")


def report(con, cfg, bags, geo, ev):
    run_at, quotes, levels, notices, any_opts, low_opts = ev
    detail = []
    for (kind, dates), (flights, pax, url) in sorted(quotes.items()):
        ss = sorted((dict(score(f, pax, cfg, bags, geo, 2 if kind == "rt" else 1), url=url)
                     for f in flights if allowed(f, cfg)), key=lambda s: s["total"])
        trs = "".join(f"<tr>{leg_cells(s)}<td>{pill(s['risk'])}</td><td class=small>{notes_html(s['notes'])}</td></tr>"
                      for s in ss)
        hidden = len(flights) - len(ss)
        detail.append(f"<details><summary>{SEARCH_NAMES[kind]} {dates.replace('>', ' to ')} &middot; {pax} pax &middot; "
                      f"{len(ss)} flights{f' ({hidden} hidden by trip.toml filters)' if hidden else ''} &middot; "
                      f"Google price level: {levels[(kind, dates)] or 'n/a'} &middot; "
                      f"<a href='{html.escape(url)}'>open search</a></summary>"
                      f"<div class=scroll><table><tr>{LEG_HEAD}<th>Risk</th><th>Notes</th></tr>{trs}</table></div></details>")
    hist = con.execute("SELECT run_at, scope, total, label FROM best ORDER BY run_at DESC LIMIT 20").fetchall()
    hist_rows = "".join(f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>${r[2]:,.0f}</td><td>{html.escape(r[3])}</td></tr>" for r in hist)
    kpi = lambda o: (f"${o[0]['total']:,.0f}</b><span class=small>{per_person_html(o[0])}</span>" if o
                     else "n/a</b>")
    page = f"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Flight Price Tracker</title><style>{CSS}</style>
<h1>{html.escape(cfg.get('title', 'Flight price tracker'))}</h1>
<p class=muted>Run {run_at} &middot; all prices USD, economy, totals for all travellers &middot;
out {cfg['outbound']['adults']} adult landing {cfg['outbound']['arrive_on']} &middot;
back {cfg['return']['adults']} adults on {', '.join(cfg['return']['depart_dates'])} &middot;
bags costed to {cfg['prefs']['bags_per_person']}&times;23kg per person per direction &middot;
excluding {html.escape(', '.join(cfg['prefs'].get('exclude_airlines', [])) or 'no airlines')}</p>
<div class=kpis><div class=kpi>Cheapest trip, everyone<b>{kpi(any_opts)}</div>
<div class=kpi>Cheapest low-risk trip, everyone<b>{kpi(low_opts)}</div>
</div>
{''.join(f"<p><span class='pill high'>Incomplete run</span> no results for {html.escape(m)}</p>" for m in missing(cfg, quotes))}
{''.join(f"<p><span class='pill medium'>Google Flights live notice</span> {html.escape(n)}</p>" for n in sorted(notices))}
<h2>Best options (risk &le; {cfg['prefs']['max_risk']})</h2>
<p class=small>A = one-way out + one-way back on one booking. B = round trip for the outbound traveller + a one-way
for the extra return traveller. B totals are "from" prices: Google pairs the round trip with its cheapest return, so
price the exact return flight both travellers will share before booking. Bag fees are estimates from
data/baggage.json; hover a cell for the rule used.</p>
{rows_html(any_opts)}
<h2>Best low-risk options</h2>{rows_html(low_opts)}
<h2>Price history</h2><div><span class=key style="background:var(--s1)"></span>Any risk
<span class=key style="background:var(--s2)"></span>Low risk only</div>{chart(con)}
<details><summary>History table</summary><table><tr><th>Run</th><th>Scope</th><th>Best total</th><th>Option</th></tr>{hist_rows}</table></details>
<h2>Every flight found</h2>{''.join(detail)}
<p class=small>Scraped from Google Flights for personal use. Prices change by the minute; confirm on the airline site before paying.</p>
</html>"""
    (HERE / "report.html").write_text(page)


def alert(con, ev, cfg):
    """Record this run's best totals; notify on an all-time low or on first dropping under target."""
    run_at, quotes, _, _, any_opts, low_opts = ev
    if gaps := missing(cfg, quotes):                # a partial run would fake a price jump in history
        print("Incomplete run, not recorded in history; missing:", ", ".join(gaps), file=sys.stderr)
        return
    q = "SELECT {} FROM best WHERE scope='any' AND run_at<?"
    prev_min = con.execute(q.format("min(total)"), (run_at,)).fetchone()[0]
    prev_last = con.execute(q.format("total") + " ORDER BY run_at DESC LIMIT 1", (run_at,)).fetchone()
    for scope, opts in (("any", any_opts), ("low", low_opts)):
        if opts:
            o = opts[0]
            con.execute("INSERT INTO best VALUES(?,?,?,?)", (run_at, scope, o["total"], f"{o['strategy']} {o['dates']}"))
    con.commit()
    if not any_opts:
        return
    best = any_opts[0]["total"]
    target = cfg["prefs"].get("target_total_usd")
    new_low = prev_min is not None and best < prev_min
    crossed = target and best <= target and (prev_last is None or prev_last[0] > target)
    if new_low or crossed:
        msg = f"{'New low' if new_low else 'Under target'} ${best:,.0f} ({any_opts[0]['strategy']} {any_opts[0]['dates']})"
        print("ALERT:", msg)
        if sys.platform == "darwin":
            subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Flight tracker"'], check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="rebuild report from the latest stored run, no scraping")
    args = ap.parse_args()
    cfg, bags, geo = load()
    con = db()
    if args.report:
        ev = evaluate(con, cfg, bags, geo)
    else:
        print("Scraping Google Flights...")
        ev = evaluate(con, cfg, bags, geo, scrape(cfg, con))
        alert(con, ev, cfg)
    report(con, cfg, bags, geo, ev)
    for o in ev[4][:3]:
        pp = ", ".join(f"{who} ${cost:,.0f}" for who, cost in o["per_person"])
        print(f"  {o['strategy']} {o['dates']}: ${o['total']:,.0f} total; per person: {pp} ({o['risk']} risk)")
    print("Report:", HERE / "report.html")
    if not args.report and (gaps := missing(cfg, ev[1])):
        sys.exit(f"Incomplete run, no results for: {', '.join(gaps)}")   # non-zero so CI reports it


if __name__ == "__main__":
    main()
