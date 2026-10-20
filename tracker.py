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
import json
import random
import re
import sqlite3
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import gflights
import render
from gflights import Flight

HERE = Path(__file__).resolve().parent
LEVELS = ["low", "medium", "high"]
KEEP_RUNS = 8      # raw quotes kept in prices.db; the best-price history keeps every run


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
        fee = v.get("extra_bag_usd")
        fees_ok = isinstance(fee, (int, float)) or (isinstance(fee, list) and fee and
                                                    all(isinstance(x, (int, float)) for x in fee))
        if not (isinstance(v.get("lowest_fare_pieces"), int) and fees_ok):
            sys.exit(f"data/baggage.json {k}: lowest_fare_pieces must be a number and extra_bag_usd a number "
                     f"or a list of numbers [1st bag, 2nd bag, ...]")
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
def bag_rule(f, bags):
    """(airline, rule) for a flight: the first listed airline we know (segment order ~ first marketing
    carrier, whose rules apply to US-origin trips), else the default rule."""
    carrier = next((a for a in f.airlines if lookup(bags["airlines"], a)), None)
    return (carrier, lookup(bags["airlines"], carrier)) if carrier else ("unknown airline", bags["default"])


def bag_cost(f, pax, need, bags, legs=1):
    """USD to bring every passenger up to `need` x 23kg. extra_bag_usd is one price for every extra bag, or a list
    priced by bag number ([1st checked bag, 2nd checked bag]); the bags a fare includes are the first ones."""
    carrier, rule = bag_rule(f, bags)
    fees = rule["extra_bag_usd"] if isinstance(rule["extra_bag_usd"], list) else [rule["extra_bag_usd"]]
    per_person = sum(fees[min(n, len(fees) - 1)] for n in range(rule["lowest_fare_pieces"], need))
    return per_person * pax * legs, carrier


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
        where = cities.get(code, code)
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
            "two_bag_fare": bag_rule(f, bags)[1].get("two_bag_fare") if fee else None,
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
    """Plan B, cheapest first, one per return date: a round trip for the outbound adults + a one-way home on the
    same airline for the rest. (Plan A, all one-ways, is journeys().) quotes: {(kind, dates): (flights, pax, url)}."""
    out, ret = cfg["outbound"], cfg["return"]
    legs_of = {(k, d): legs for k, d, legs, _ in searches(cfg)}

    def scored(kind, dates, legs=1):
        flights, pax, url = quotes.get((kind, dates), ([], 0, ""))
        rows = [dict(score(f, pax, cfg, bags, geo, legs), url=url, search=legs_of.get((kind, dates), []))
                for f in flights]
        return [s for s in rows if ok(s, max_risk, cfg)]

    best = {}
    for d2 in ret["depart_dates"]:
        extra = scored("ret_extra", d2)
        for d1 in out["depart_dates"]:
            for rt in scored("rt", f"{d1}>{d2}", legs=2):
                same = [s for s in extra if s["f"].airlines[0] == rt["f"].airlines[0]]
                if not (rt["f"].arrive.startswith(out["arrive_on"]) and same):
                    continue
                partner = min(same, key=lambda s: s["total"])
                if d2 in best and best[d2]["total"] <= rt["total"] + partner["total"]:
                    continue
                best[d2] = {"dates": f"{d1} > {d2}", "legs": [(out["adults"], rt), (partner["pax"], partner)],
                            "total": rt["total"] + partner["total"],
                            "per_person": [rt["total"] / out["adults"], partner["total"] / partner["pax"]],
                            "risk": max(rt["risk"], partner["risk"], key=LEVELS.index)}
    return sorted(best.values(), key=lambda r: r["total"])


def best_trip(t):
    """(total, how) for one journeys() risk scope: the one-way pair or the round-trip deal, whichever is cheaper."""
    deal = t["deal"]
    if deal and (t["total"] is None or deal["total"] < t["total"]):
        return deal["total"], f"round trip + one-way, home {deal['dates'][-10:]}"
    return t["total"], (f"one-ways, home {t['ret']['date']}" if t["total"] else "")


def mark_split_fares(together, alone, alone_pax, min_saving=50):
    """Flag return flights that are cheaper booked one traveller at a time. Booked together, every traveller pays
    the lowest fare with enough seats for all of them; if only one seat is left at a lower fare, one traveller can
    buy it alone and the other pays the together price. So the saving is (together each) - (alone price).
    Only meaningful when the 'alone' search is for exactly 1 traveller."""
    if alone_pax != 1:
        return
    price_alone = {(tuple(f.airlines), f.depart, f.arrive): f.price for f in alone}
    for s in together:
        f = s["f"]
        each = f.price / s["pax"]
        cheap = price_alone.get((tuple(f.airlines), f.depart, f.arrive))
        if cheap is not None and each - cheap >= min_saving:
            s["split"] = {"alone": cheap, "each": each, "saving": each - cheap}


def journeys(quotes, cfg, bags, geo):
    """The trip as the user thinks of it: 1 person out, N people back, and the sum.
    out: allowed outbound flights landing on arrive_on, cheapest first; ret: {date: allowed return flights};
    totals: per risk scope, cheapest outbound + cheapest return (+ the best round-trip deal for comparison)."""
    out, ret = cfg["outbound"], cfg["return"]
    legs_of = {(k, d): legs for k, d, legs, _ in searches(cfg)}

    def scored(kind, d):
        flights, pax, url = quotes.get((kind, d), ([], 0, ""))
        return [dict(score(f, pax, cfg, bags, geo), url=url, search=legs_of.get((kind, d), []), date=d)
                for f in flights if allowed(f, cfg)]

    within = lambda s, scope: LEVELS.index(s["risk"]) <= LEVELS.index(scope)
    outs = sorted((s for d in out["depart_dates"] for s in scored("out", d) if s["f"].arrive.startswith(out["arrive_on"])),
                  key=lambda s: s["total"])
    rets = {d: sorted(scored("ret", d), key=lambda s: s["total"]) for d in ret["depart_dates"]}
    for d, flights in rets.items():
        mark_split_fares(flights, *quotes.get(("ret_extra", d), ([], 0, ""))[:2])
    totals = []
    for label, scope in (("Cheapest", "high"), ("Cheapest without a high-risk flight", "medium"), ("Lowest risk", "low")):
        o = next((s for s in outs if within(s, scope)), None)
        r = min((s for v in rets.values() for s in v if within(s, scope)), key=lambda s: s["total"], default=None)
        deal = next(iter(options(quotes, cfg, bags, geo, scope)), None)
        totals.append({"label": label, "scope": scope, "out": o, "ret": r, "deal": deal,
                       "total": o["total"] + r["total"] if o and r else None,
                       "risk": max(o["risk"], r["risk"], key=LEVELS.index) if o and r else None})
    return {"out": outs, "ret": rets, "totals": totals}


# --- storage ---------------------------------------------------------------
def db():
    con = sqlite3.connect(HERE / "prices.db")
    con.execute("CREATE TABLE IF NOT EXISTS quotes(run_at TEXT, kind TEXT, dates TEXT, pax INT,"
                " url TEXT, level TEXT, notice TEXT, flight TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS best(run_at TEXT, scope TEXT, total REAL)")
    return con


def prune(con, keep=KEEP_RUNS):
    """Drop raw quotes older than the last `keep` runs. CI commits prices.db every run, so unbounded
    growth would bloat the git history. ponytail: old runs can no longer be re-scored after a rules change."""
    con.execute("DELETE FROM quotes WHERE run_at NOT IN "
                "(SELECT DISTINCT run_at FROM quotes ORDER BY run_at DESC LIMIT ?)", (keep,))
    con.commit()
    con.execute("VACUUM")


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
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i, (kind, dates, legs, pax) in enumerate(searches(cfg)):
        if i:
            time.sleep(3 + random.random() * 4)     # be polite; Google throttles bursts
        try:
            flights, level, notice, url = gflights.search(legs, pax)
        except gflights.Blocked as e:               # every later search would hit the same wall
            print(f"  BLOCKED by Google at {kind} {dates}: {e}. Skipping the remaining searches.",
                  file=sys.stderr, flush=True)
            break
        except Exception as e:                      # one bad search must not sink the run
            print(f"  {kind} {dates}: FAILED {e!r}", file=sys.stderr, flush=True)
            continue
        print(f"  {kind:9} {dates:23} {pax} traveller(s): {len(flights)} flights, "
              f"from ${min((f.price for f in flights), default=0):,} (Google says {level})", flush=True)
        con.executemany("INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)",
                        [(run_at, kind, dates, pax, url, level, notice, json.dumps(asdict(f))) for f in flights])
        con.commit()
    prune(con)
    return run_at


def latest(con, run_at=None):
    run_at = run_at or con.execute("SELECT max(run_at) FROM quotes").fetchone()[0]
    quotes, notices = {}, set()
    for kind, dates, pax, url, notice, fj in con.execute(
            "SELECT kind, dates, pax, url, notice, flight FROM quotes WHERE run_at=?", (run_at,)):
        quotes.setdefault((kind, dates), ([], pax, url))[0].append(Flight(**json.loads(fj)))
        notices.add(notice)
    return run_at, quotes, notices - {None}


# --- report ---------------------------------------------------------------------------------------------
def missing(cfg, quotes):
    """Searches of this run that returned nothing (failed, throttled or no flights)."""
    return [f"{k} {d}" for k, d, _, _ in searches(cfg) if (k, d) not in quotes]


def evaluate(con, cfg, bags, geo, run_at=None):
    run_at, quotes, notices = latest(con, run_at)
    if run_at is None:
        sys.exit("No stored runs yet: run `python3 tracker.py` first.")
    return run_at, quotes, notices, options(quotes, cfg, bags, geo, "high"), journeys(quotes, cfg, bags, geo)


def report(con, cfg, bags, geo, ev):
    history = con.execute("SELECT run_at, scope, total FROM best ORDER BY run_at").fetchall()
    (HERE / "report.html").write_text(render.page(cfg, geo, ev, missing(cfg, ev[1]), history))


def alert(con, ev, cfg):
    """Record this run's best totals; notify on an all-time low or on first dropping under target."""
    run_at, quotes, _, _, jr = ev
    if gaps := missing(cfg, quotes):                # a partial run would fake a price jump in history
        print("Incomplete run, not recorded in history; missing:", ", ".join(gaps), file=sys.stderr)
        return
    q = "SELECT {} FROM best WHERE scope='any' AND run_at<?"
    prev_min = con.execute(q.format("min(total)"), (run_at,)).fetchone()[0]
    prev_last = con.execute(q.format("total") + " ORDER BY run_at DESC LIMIT 1", (run_at,)).fetchone()
    by_scope = {t["scope"]: best_trip(t) for t in jr["totals"]}
    for scope, risk_scope in (("any", "high"), ("low", "low")):
        if by_scope[risk_scope][0] is not None:
            con.execute("INSERT INTO best VALUES(?,?,?)", (run_at, scope, by_scope[risk_scope][0]))
    con.commit()
    best, how = by_scope["high"]
    if best is None:
        return
    target = cfg["prefs"].get("target_total_usd")
    new_low = prev_min is not None and best < prev_min
    crossed = target and best <= target and (prev_last is None or prev_last[0] > target)
    if new_low or crossed:
        msg = f"{'New low' if new_low else 'Under target'} ${best:,.0f} ({how})"
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
    for t in ev[-1]["totals"]:
        total, how = best_trip(t)
        print(f"  {t['label']}: " + (f"${total:,.0f} ({how})" if total else "no flights match"))
    print("Report:", HERE / "report.html")
    if not args.report and (gaps := missing(cfg, ev[1])):
        sys.exit(f"Incomplete run, no results for: {', '.join(gaps)}")   # non-zero so CI reports it


if __name__ == "__main__":
    main()
