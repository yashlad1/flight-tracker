"""HTML for report.html. Pure functions: data in, one self-contained page out.

Design: one bold element (the airport-signage yellow route band, which shows who flies which way), options as
tickets with a price stub, and prices always shown as arithmetic. Overpass (a highway-signage face) throughout.
Travellers are named by where they start ("Mumbai traveller", "Boston traveller"), never by number.
"""
import html
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HOME_TZ = ZoneInfo("America/New_York")      # "last checked" is shown in Boston time

AIRLINE_SITES = {
    "Emirates": "https://www.emirates.com/us/english/", "Etihad": "https://www.etihad.com/en-us/",
    "Qatar Airways": "https://www.qatarairways.com/en-us/homepage.html",
    "Lufthansa": "https://www.lufthansa.com/us/en/homepage", "SWISS": "https://www.swiss.com/us/en/homepage",
    "Austrian": "https://www.austrian.com/us/en/homepage", "British Airways": "https://www.britishairways.com/",
    "Virgin Atlantic": "https://www.virginatlantic.com/", "Air France": "https://wwws.airfrance.us/",
    "KLM": "https://www.klm.us/", "Delta": "https://www.delta.com/", "American": "https://www.aa.com/",
    "United": "https://www.united.com/", "JetBlue": "https://www.jetblue.com/", "Royal Jordanian": "https://www.rj.com/",
    "Air Canada": "https://www.aircanada.com/", "Kuwait Airways": "https://www.kuwaitairways.com/",
    "Ethiopian": "https://www.ethiopianairlines.com/", "Saudia": "https://www.saudia.com/",
    "Gulf Air": "https://www.gulfair.com/", "Oman Air": "https://www.omanair.com/", "Finnair": "https://www.finnair.com/",
    "Iberia": "https://www.iberia.com/", "Aer Lingus": "https://www.aerlingus.com/", "EgyptAir": "https://www.egyptair.com/",
}

e = html.escape
money = lambda x: f"${x:,.0f}"


def hm(minutes):
    return f"{minutes // 60}h {minutes % 60:02d}m"


def clock(iso):
    return datetime.fromisoformat(iso).strftime("%H:%M")


def day(iso):
    return datetime.fromisoformat(iso).strftime("%a %-d %b")


def local(run_at):
    """Run timestamps are UTC (old rows are naive UTC); return Boston time."""
    t = datetime.fromisoformat(run_at)
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(HOME_TZ)


def checked(run_at):
    return local(run_at).strftime("%a %-d %b, %-I:%M %p").replace("AM", "am").replace("PM", "pm")


def city(cfg, code):
    return cfg.get("cities", {}).get(code, code)


def travellers(n):
    return f"{n} traveller{'s' if n != 1 else ''}"


def names(cfg):
    """(the traveller who flies out and back, the one who flies home only), named by starting city."""
    return f"{city(cfg, cfg['outbound']['from'])} traveller", f"{city(cfg, cfg['return']['from'])} traveller"


def nw(text):
    return f"<span class=nw>{text}</span>"


# --- booking links ----------------------------------------------------------------------------------------------
def book_links(s):
    """[(label, url)]: the airline (first listed carrier we know, which usually sells the ticket), then Expedia and
    Booking.com searches prefilled with route, dates and travellers, then the Google Flights search."""
    legs, pax = s["search"], s["pax"]
    links = [(f"Book on {a}", AIRLINE_SITES[a]) for a in s["f"].airlines if a in AIRLINE_SITES][:1]
    if legs:
        q = {"trip": "oneway" if len(legs) == 1 else "roundtrip", "passengers": f"adults:{pax}",
             "options": "cabinclass:economy", "mode": "search"}
        for i, (d, a, b) in enumerate(legs, 1):
            q[f"leg{i}"] = f"from:{a},to:{b},departure:{d[5:7]}/{d[8:]}/{d[:4]}TANYT"
        links.append(("Expedia", "https://www.expedia.com/Flights-Search?" + urllib.parse.urlencode(q)))
        d, a, b = legs[0]
        q = {"type": "ONEWAY" if len(legs) == 1 else "ROUNDTRIP", "adults": pax, "cabinClass": "ECONOMY",
             "from": f"{a}.AIRPORT", "to": f"{b}.AIRPORT", "depart": d} | ({"return": legs[1][0]} if len(legs) > 1 else {})
        links.append(("Booking.com", f"https://flights.booking.com/flights/{a}.AIRPORT-{b}.AIRPORT/?"
                      + urllib.parse.urlencode(q)))
    links.append(("Compare all sellers", s["url"]))
    return links


def links_html(s):
    out = []
    for i, (label, url) in enumerate(book_links(s)):
        cls = "btn" if i == 0 and label.startswith("Book on") else "lnk"
        out.append(f"<a class={cls} href='{e(url)}' target=_blank rel=noopener>{e(label)}</a>")
    return f"<div class=book>{''.join(out)}</div>"


# --- pictograms (AIGA-style, inherit currentColor) ----------------------------------------------------------------
PERSON = ("<svg class=person viewBox='0 0 20 32' aria-hidden=true><circle cx=10 cy=5 r=4.5 />"
          "<path d='M4 12a6 6 0 0 1 12 0v9h-2.5v10h-7V21H4z'/></svg>")
PLANE = ("<svg class=plane viewBox='0 0 24 24' aria-hidden=true><path d='M21 15.5v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V8.5"
         "l-8 5v2l8-2.5V18l-2 1.5V21l3.5-1 3.5 1v-1.5L13 18v-5z'/></svg>")


# --- page parts -------------------------------------------------------------------------------------------------
def band(cfg):
    out, ret = cfg["outbound"], cfg["return"]
    t1, t2 = names(cfg)
    lands = datetime.fromisoformat(out["arrive_on"]).strftime("%a %-d %b")
    days = [datetime.fromisoformat(d) for d in ret["depart_dates"]]
    back = ", ".join(d.strftime("%a %-d") for d in days[:-1]) + f" or {days[-1].strftime('%a %-d %b')}"
    a, b = city(cfg, out["from"]), city(cfg, out["to"])
    return f"""<section class=band aria-label="The trip">
<div class=band-route>
  <div class=place><span class=code>{e(out['from'])}</span><span class=name>{e(a)}</span></div>
  <div class=flows>
    <div class="flow go"><span class=people aria-hidden=true>{PERSON * out['adults']}</span>
      <span><b>{travellers(out['adults'])}</b> to {e(b)}<small>landing {lands}</small></span></div>
    <div class=track>{PLANE}</div>
    <div class="flow home"><span class=people aria-hidden=true>{PERSON * ret['adults']}</span>
      <span><b>{travellers(ret['adults'])}</b> home to {e(a)}<small>leaving {back}</small></span></div>
  </div>
  <div class="place end"><span class=code>{e(out['to'])}</span><span class=name>{e(b)}</span></div>
</div>
<p class=band-note>The {e(t1)} flies out on {lands}; the {e(t2)} joins them for the flight home.
Every traveller checks {cfg['prefs']['bags_per_person']} bags of 23&nbsp;kg on every flight, and every price
below includes those bags.</p>
</section>"""


def risk_line(r, geo):
    """'High disruption risk: connects in Abu Dhabi; Lufthansa rated medium', plus the full source notes."""
    short, full = [], []
    for _, _, s in r["legs"]:
        f = s["f"]
        for code, name in zip(f.layovers, f.layover_names or f.layovers):
            if geo.get("hubs", {}).get(code, {}).get("level", "low") != "low":
                short.append(f"connects in {name.split(', ')[-1]}")
        for a in f.airlines:
            lvl = geo.get("airlines", {}).get(a, {}).get("level", "low")
            if lvl != "low":
                short.append(f"{a} rated {lvl}")
        full += s["notes"]
    if r["note"]:
        full.append(r["note"])
    head = f"{r['risk'].capitalize()} disruption risk"
    short = list(dict.fromkeys(short))
    return head + (": " + "; ".join(short) if short else ""), list(dict.fromkeys(full))


def leg(cfg, r, i, name, pax, s):
    f = s["f"]
    t1, t2 = names(cfg)
    rt = name.startswith("Round trip")
    who = t1 if i == 0 else ("Both travellers" if r["strategy"] == "A" else t2)
    a, b = (cfg["outbound"]["from"], cfg["outbound"]["to"]) if i == 0 else (cfg["return"]["from"], cfg["return"]["to"])
    title = f"{e(city(cfg, a))} to {e(city(cfg, b))}" + (" and back, round trip" if rt else "")
    stops = "".join(f"<span class=stop>{e(c.split(', ')[-1])} <small>{hm(m)}</small></span>"
                    for c, m in zip(f.layover_names or f.layovers, f.layover_min)) or "<span class=stop>Nonstop</span>"
    bags = "bags included" if not s["bags"] else f"{money(s['bags'])} bags"
    each = f", {money(s['total'] / pax)} each" if pax > 1 else ""
    rt_note = (f"<p class=fine>This ticket also covers the {e(t1)}'s flight home. When you book it, choose the "
               f"same return flight as the {e(t2)}'s ticket below. The fare and bags shown cover both "
               f"directions.</p>" if rt else "")
    return f"""<div class=leg>
  <div class=leg-head><h4>{title}</h4><span class=who>{e(who)}</span><span class=airline>{e(', '.join(f.airlines))}</span></div>
  <div class=line>
    <div class=pt><b>{clock(f.depart)}</b><span>{e(city(cfg, a))}</span><small>{day(f.depart)}</small></div>
    <div class=path><span class=dur>{hm(f.duration_min)}</span><span class=stops>{stops}</span></div>
    <div class="pt end"><b>{clock(f.arrive)}</b><span>{e(city(cfg, b))}</span><small>{day(f.arrive)}</small></div>
  </div>
  <p class=sum>{nw(money(s['fare']) + ' fare')} + {nw(bags)} = {nw(f"<b>{money(s['total'])}</b> for {travellers(pax)}{each}")}</p>
  {rt_note}{links_html(s)}
</div>"""


def when(r):
    """(departure day, arrival day) of the option's flight home, e.g. ('Mon 28 Dec', 'Tue 29 Dec')."""
    f = r["legs"][1][2]["f"]
    return day(f.depart), day(f.arrive)


def plan_text(cfg, r):
    t1, t2 = names(cfg)
    return (f"A one-way for the {t1}, then one booking home for both travellers." if r["strategy"] == "A"
            else f"A round trip for the {t1}, plus a one-way home for the {t2}.")


def ticket(cfg, geo, r, label=None):
    leave, lands = when(r)
    home, away = city(cfg, cfg["return"]["to"]), city(cfg, cfg["return"]["from"])
    line, full = risk_line(r, geo)
    why = (f"<details class=why><summary>Why {r['risk']} risk, and other notes</summary><ul>"
           + "".join(f"<li>{e(n)}</li>" for n in full) + "</ul></details>") if full else ""
    (_, c1), (_, c2) = r["per_person"]
    t1, t2 = names(cfg)
    return f"""<article class="ticket r-{r['risk']}">
<div class=main>
  <header>{f'<p class=label>{e(label)}</p>' if label else ''}<h3>Leave {e(away)} {leave} <small>(land in {e(home)} {lands})</small></h3>
    <p class=plan>{e(plan_text(cfg, r))}</p>
    <p class=risk><span class="dot"></span>{e(line)}</p></header>
  {''.join(leg(cfg, r, i, n, p, s) for i, (n, p, s) in enumerate(r['legs']))}
  {why}
</div>
<aside class=stub>
  <span class=stub-k>Whole trip</span><b class=total>{money(r['total'])}</b><span class=stub-k>for both travellers</span>
  <dl><dt>{e(t1)} <small>there and back</small></dt><dd>{money(c1)}</dd>
      <dt>{e(t2)} <small>home only</small></dt><dd>{money(c2)}</dd></dl>
</aside>
</article>"""


def row(cfg, geo, r, also_above=False):
    """Compact, expandable line for the full options list; opens into the full ticket."""
    leave, _ = when(r)
    airlines = " and ".join(dict.fromkeys(a for _, _, s in r["legs"] for a in s["f"].airlines[:1]))
    via = ", ".join(dict.fromkeys(n.split(", ")[-1] for _, _, s in r["legs"] for n in (s["f"].layover_names or s["f"].layovers)))
    (_, c1), (_, c2) = r["per_person"]
    t1, t2 = names(cfg)
    style = "Separate one-ways" if r["strategy"] == "A" else "Round trip + one-way"
    return f"""<details class="opt r-{r['risk']}"><summary>
  <span class=o-when><b>Leave {e(city(cfg, cfg['return']['from']))} {leave}</b><small>{style}{', shown above' if also_above else ''}</small></span>
  <span class=o-route>{e(airlines)}<small>via {e(via) or 'nonstop'}</small></span>
  <span class=risk><span class=dot></span>{r['risk'].capitalize()} risk</span>
  <span class=o-price><b>{money(r['total'])}</b><small>{e(t1)} {money(c1)}<br>{e(t2)} {money(c2)}</small></span>
</summary>{ticket(cfg, geo, r)}</details>"""


def chart(history):
    rows = [(r, s, t) for r, s, t, _ in history]
    runs = sorted({r for r, _, _ in rows})
    days = {local(r).date() for r in runs}
    if len(days) < 2:
        return (f"<p class=fine>Not enough history yet: prices have been checked {len(runs)} "
                f"time{'s' if len(runs) != 1 else ''}, all on one day. The chart appears once there are checks on "
                f"two different days.</p>")
    W, H, L, R, T, B = 760, 240, 56, 130, 16, 30
    vals = [t for _, _, t in rows]
    lo, hi = min(vals) * 0.96, max(vals) * 1.04
    x = lambda i: L + i * (W - L - R) / (len(runs) - 1)
    y = lambda v: T + (hi - v) * (H - T - B) / (hi - lo)
    svg = [f"<svg viewBox='0 0 {W} {H}' role=img aria-label='Cheapest whole-trip price at each check'>"]
    for k in range(4):
        v = lo + k * (hi - lo) / 3
        svg.append(f"<line x1={L} x2={W - R} y1={y(v):.1f} y2={y(v):.1f} class=grid />"
                   f"<text x={L - 8} y={y(v) + 4:.1f} class=tick text-anchor=end>${v / 1000:.1f}k</text>")
    for i in sorted({0, len(runs) - 1}):
        svg.append(f"<text x={x(i):.1f} y={H - 8} class=tick text-anchor={'start' if i == 0 else 'end'}>"
                   f"{local(runs[i]).strftime('%a %-d %b')}</text>")
    for n, (scope, name) in enumerate((("any", "Cheapest"), ("low", "Low risk"))):
        pts = [(runs.index(r), t) for r, s, t in rows if s == scope]
        if not pts:
            continue
        path = " ".join(f"{'M' if j == 0 else 'L'}{x(i):.1f},{y(t):.1f}" for j, (i, t) in enumerate(pts))
        svg.append(f"<path d='{path}' class='ln s{n + 1}' />")
        svg += [f"<circle cx={x(i):.1f} cy={y(t):.1f} r=4 class='pt s{n + 1}'><title>{name}: {money(t)}, "
                f"{checked(runs[i])}</title></circle>" for i, t in pts]
        i, t = pts[-1]
        svg.append(f"<text x={x(i) + 10:.1f} y={y(t) + 4:.1f} class=end-lbl>{name} {money(t)}</text>")
    return ("<p class=legend><span class='key s1'></span>Cheapest whole trip <span class='key s2'></span>"
            "Cheapest low-risk whole trip</p>" + "".join(svg) + "</svg>")


def via_text(f):
    return ", ".join(f"{n.split(', ')[-1]} {hm(m)}" for n, m in zip(f.layover_names or f.layovers, f.layover_min)) or "nonstop"


def j_row(cfg, s, a, b):
    """One flight in a journey table: what it is, what it costs for everyone on it, its risk."""
    f, pax = s["f"], s["pax"]
    links = book_links(s)
    first, compare_all = links[0], links[-1]
    lands = "" if f.arrive[:10] == f.depart[:10] else f" ({day(f.arrive)})"
    bags = "bags included" if not s["bags"] else f"{money(s['bags'])} bags"
    each = f"<small>{money(s['total'] / pax)} each</small>" if pax > 1 else ""
    if s.get("split"):
        each += f"<small class=split>About {money(s['split']['saving'])} less as 2 separate tickets</small>"
    return f"""<tr class=r-{s['risk']}>
  <td><b>{e(', '.join(f.airlines))}</b>
    <small>{day(f.depart)}, {clock(f.depart)} {e(city(cfg, a))} to {clock(f.arrive)} {e(city(cfg, b))}{lands}</small>
    <small>via {e(via_text(f))}</small>
    <span class=jlinks><a class=lnk href='{e(first[1])}' target=_blank rel=noopener>{e(first[0])}</a>
    <a class=lnk href='{e(compare_all[1])}' target=_blank rel=noopener>Compare prices</a></span></td>
  <td class=num><b>{money(s['total'])}</b>{each}<small>{money(s['fare'])} fare + {bags}</small></td>
  <td><span class=risk><span class=dot></span>{s['risk'].capitalize()}</span></td>
</tr>"""


def journeys_html(cfg, jr, per_date=2, top=4):
    out, ret = cfg["outbound"], cfg["return"]
    lands = datetime.fromisoformat(out["arrive_on"]).strftime("%a %-d %b")
    o_rows = "".join(j_row(cfg, s, out["from"], out["to"]) for s in jr["out"][:top]) or \
        "<tr><td colspan=3>No flights match.</td></tr>"
    r_rows = ""
    for d, flights in jr["ret"].items():
        r_rows += f"<tr class=grp><th colspan=3 scope=colgroup>Leaving {day(d + 'T00:00')}</th></tr>"
        r_rows += "".join(j_row(cfg, s, ret["from"], ret["to"]) for s in flights[:per_date]) or \
            "<tr><td colspan=3>No flights match.</td></tr>"
    head = lambda who: (f"<thead><tr><th scope=col>Flight</th><th scope=col class=num>Price for {who}</th>"
                        "<th scope=col>Risk</th></tr></thead>")
    return f"""<div class=jgrid>
<div class=jcard><h3>{e(city(cfg, out['from']))} to {e(city(cfg, out['to']))}</h3>
  <p class=jsub>{travellers(out['adults']).replace('traveller', 'person')}, landing {lands}, cheapest first</p>
  <table class=jt>{head(travellers(out['adults']).replace('traveller', 'person'))}<tbody>{o_rows}</tbody></table></div>
<div class=jcard><h3>{e(city(cfg, ret['from']))} to {e(city(cfg, ret['to']))}</h3>
  <p class=jsub>{travellers(ret['adults']).replace('travellers', 'people')}, cheapest {per_date} for each day</p>
  <table class=jt>{head(travellers(ret['adults']).replace('travellers', 'people'))}<tbody>{r_rows}</tbody></table>
  {split_how(jr)}</div>
</div>"""


def split_how(jr):
    """Explain separate tickets, only when some flight on the page is cheaper that way."""
    shown = [s for v in jr["ret"].values() for s in v[:2] if s.get("split")]
    if not shown:
        return ""
    return """<div class=split-how><p><b>Cheaper as 2 separate tickets?</b> On the flights marked above, the airline has
one seat left at a lower fare, so the first traveller can buy it alone and the second pays the normal price. Booking
together is simpler: you are seated together and rebooked together if the flight changes. If you book separately:</p>
<ol><li>Book the exact same flight (same date and flight numbers) twice. Book the cheaper ticket first, then the
second straight away, because the price can rise once that seat is gone.</li>
<li>Right after booking, open <i>Manage booking</i> on each ticket and pick seats next to each other. On the
cheapest fares this can cost extra; free seats are given at check-in, when adjacent seats may be gone.</li>
<li>Ask the airline (by phone or chat) to link the two bookings, so you stay together if the flight is changed.</li>
<li>Check in together at the airport counter and ask to be seated together.</li></ol></div>"""


def totals_html(cfg, jr, geo):
    out, ret = cfg["outbound"], cfg["return"]
    hubs = {n.split(", ")[-1] for v in [jr["out"], *jr["ret"].values()] for s in v
            for c, n in zip(s["f"].layovers, s["f"].layover_names or s["f"].layovers)
            if geo.get("hubs", {}).get(c, {}).get("level") == "high"}
    notes = {"high": "The lowest price, whatever the risk.",
             "medium": "Skips every flight rated high risk" + (f", such as stops in {', '.join(sorted(hubs))}." if hubs else "."),
             "low": "Only flights rated low risk, in both directions."}
    rows, seen = [], {}
    for t in jr["totals"]:
        if not t["total"]:
            rows.append(f"<div class=tot><div class=t-label><b>{e(t['label'])}</b></div><p>No flights match.</p></div>")
            continue
        o, r = t["out"], t["ret"]
        same = seen.setdefault((id(o), id(r)), t["label"])
        deal = t["deal"]
        split = r.get("split")
        tip = (f"<p class=t-deal>Booking the 2 return tickets separately saves about <b>{money(split['saving'])}</b> "
               f"(whole trip about {money(t['total'] - split['saving'])}). See how to still sit together above.</p>"
               if split else "")
        tip += (f"<p class=t-deal>Booking trick: a round trip for the {e(names(cfg)[0])} plus a one-way for the "
               f"{e(names(cfg)[1])} brings this to <b>{money(deal['total'])}</b>, saving {money(t['total'] - deal['total'])}. "
               f"It is in the options list below.</p>" if deal and deal["total"] < t["total"] else "")
        rows.append(f"""<div class="tot r-{t['risk']}">
  <div class=t-label><b>{e(t['label'])}</b><small>{e(notes[t['scope']]) if same == t['label'] else 'Same flights as ' + e(same).lower() + '.'}</small>
    <span class=risk><span class=dot></span>{t['risk'].capitalize()} risk</span></div>
  <div class=t-sum>
    <div class=t-leg><small>{e(city(cfg, out['from']))} to {e(city(cfg, out['to']))}, {travellers(out['adults']).replace('traveller', 'person')}</small>
      <b>{money(o['total'])}</b><span>{e(o['f'].airlines[0])}, {day(o['f'].depart)}</span></div>
    <div class=op aria-hidden=true>+</div>
    <div class=t-leg><small>{e(city(cfg, ret['from']))} to {e(city(cfg, ret['to']))}, {travellers(ret['adults']).replace('travellers', 'people')}</small>
      <b>{money(r['total'])}</b><span>{e(r['f'].airlines[0])}, {day(r['f'].depart)}, {money(r['total'] / r['pax'])} each</span></div>
    <div class=op aria-hidden=true>=</div>
    <div class="t-leg t-total"><small>Whole trip</small><b>{money(t['total'])}</b><span>for {'both' if ret['adults'] == 2 else 'all ' + str(ret['adults'])} travellers</span></div>
  </div>{tip}
</div>""")
    return "".join(rows)


def page(cfg, geo, ev, gaps, history):
    run_at, _, _, notices, any_opts, low_opts, jr = ev
    warn = "".join(f"<p class=alert>No results for {e(g)} on the last check, so prices may be incomplete.</p>"
                   for g in gaps)
    notice = "".join(f"<p class=fine>Google Flights is also showing a general notice on these routes: "
                     f"{e(n[0].lower() + n[1:])}</p>" for n in sorted(notices))
    rows_any = "".join(row(cfg, geo, o) for o in any_opts) or "<p>No options match.</p>"
    rows_low = "".join(row(cfg, geo, o) for o in low_opts) or "<p>No low-risk options found.</p>"
    p = cfg["prefs"]
    left_out = [f"layovers over {p['max_layover_hours']} hours"] if p.get("max_layover_hours") else []
    left_out += p.get("exclude_airlines", [])
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Flight Price Tracker</title>
<link rel=preconnect href=https://fonts.googleapis.com><link rel=preconnect href=https://fonts.gstatic.com crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;800&display=swap" rel=stylesheet>
<style>{CSS}</style></head>
<body>
<header class=top><h1>{e(cfg.get('title', 'Flight price tracker'))}</h1>
<p>Last checked {checked(run_at)} (Boston time). Prices are checked every 6 hours.</p></header>
{band(cfg)}
<main>
{warn}
<section class=journeys aria-labelledby=h-j><h2 id=h-j>Prices by journey</h2>
<p class=intro>Every price includes {cfg['prefs']['bags_per_person']} bags of 23&nbsp;kg for each person.</p>
{journeys_html(cfg, jr)}
<h2 class=h-total id=h-total>Whole trip</h2>
<p class=intro>The cheapest {e(city(cfg, cfg['outbound']['from']))} to {e(city(cfg, cfg['outbound']['to']))} flight plus the
cheapest flight home, at three levels of risk.</p>
{totals_html(cfg, jr, geo)}{notice}</section>
<section class=all aria-labelledby=h-all><h2 id=h-all>Every booking option, with details</h2>
<p class=intro>Separate one-way tickets, or a round trip plus a one-way. Open a line to see each flight and how to
book it.</p>
<fieldset class=toggle><legend class=sr>Show</legend>
<input type=radio name=show id=show-any checked><label for=show-any>Show everything</label>
<input type=radio name=show id=show-low><label for=show-low>Show only low risk</label></fieldset>
<div class=list-any>{rows_any}</div><div class=list-low>{rows_low}</div>
</section>
<section class=history aria-labelledby=h-hist><h2 id=h-hist>Price over time</h2>{chart(history)}</section>
<section class=tips aria-labelledby=h-tips><h2 id=h-tips>Booking tips</h2>
<ul><li>Book on the airline's own site unless Expedia or Booking.com is more than about $50 cheaper. If a flight is
cancelled or rerouted, you then deal with the airline directly.</li>
<li>To get 2 bags of 23&nbsp;kg, compare the airline's next fare level with paying for bags. The upgrade is often
cheaper.</li>
<li>If you book directly with the airline at least 7 days before the flight, US rules let you cancel within
24 hours of booking for a full refund.</li>
<li>Book the 2 travellers flying home on one booking unless this page shows a saving for separate tickets. One
booking keeps you seated together and rebooked together.</li>
<li>For a round trip + one-way: book the round trip first, then book the Boston traveller's one-way on the same
flight as the round trip's return.</li></ul></section>
</main>
<footer><p>Prices come from Google Flights, in US dollars, economy class, and change by the minute. Bag fees are
estimates. Left out of every list: {e(', '.join(left_out))}. Confirm the final price before you pay.</p></footer>
</body></html>"""


CSS = """
:root{color-scheme:light;--paper:#f5f7fa;--surface:#fff;--ink:#14213d;--ink-2:#4a5672;--rule:#a9b4c8;--hair:#e1e6ef;
--sign:#ffcc00;--sign-ink:#14213d;--route:#2f5bea;--low:#1e7f4f;--medium:#a15c00;--high:#b4312a;
--s1:#2a78d6;--s2:#c4501f;--focus:#2f5bea}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--paper:#0f1828;--surface:#16213a;--ink:#e9eef7;
--ink-2:#a9b4ca;--rule:#4a5a80;--hair:#26324f;--route:#8eaaff;--low:#4fbf85;--medium:#e0a33a;--high:#f07a72;
--s1:#3987e5;--s2:#e8743d;--focus:#ffcc00}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:400 16px/1.5 Overpass,system-ui,sans-serif;
font-variant-numeric:tabular-nums}
a{color:var(--route)}
a:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:4px}
h1,h2,h3,h4,p{margin:0}.nw{white-space:nowrap}
.top,main,footer{max-width:1080px;margin:0 auto;padding:0 20px}
.top{padding-top:24px;padding-bottom:16px}
.top h1{font-size:20px;font-weight:800}.top p{color:var(--ink-2);font-size:15px}
/* the route band: the one loud element */
.band{background:var(--sign);color:var(--sign-ink);padding:28px 20px 22px}
.band-route{max-width:1040px;margin:0 auto;display:grid;grid-template-columns:auto 1fr auto;gap:24px;align-items:center}
.place{display:flex;flex-direction:column;line-height:1}.place.end{text-align:right}
.code{font-size:60px;font-weight:800;letter-spacing:-.02em}.name{font-size:18px;font-weight:600;margin-top:6px}
.flows{display:grid;gap:10px}
.flow{display:flex;align-items:center;gap:12px;font-size:18px;line-height:1.25}
.flow small{display:block;font-size:15px}.flow.home{flex-direction:row-reverse;text-align:right}
.people{display:inline-flex;gap:4px;flex:none}.person{width:18px;height:29px;fill:currentColor}
.track{position:relative;height:3px;background:var(--sign-ink);border-radius:2px}
.plane{position:absolute;left:50%;top:50%;width:28px;height:28px;transform:translate(-50%,-50%) rotate(90deg);
fill:var(--sign-ink);background:var(--sign);border-radius:50%}
.band-note{max-width:1040px;margin:18px auto 0;font-size:15px;max-width:1040px}
main{padding-top:28px;padding-bottom:40px}
section{margin-top:44px}section:first-of-type{margin-top:0}
h2{font-size:24px;font-weight:800;margin-bottom:12px}
.alert{margin:0 0 18px;padding:10px 14px;border-left:4px solid var(--high);background:var(--surface)}
.intro,.fine{color:var(--ink-2);font-size:14px}.intro{margin:-4px 0 14px}.fine{margin-top:8px}
/* prices by journey */
.jgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
.jcard{background:var(--surface);border:1px solid var(--rule);border-radius:14px;padding:18px 20px 8px}
.jcard h3{font-size:22px;font-weight:800}.jsub{color:var(--ink-2);font-size:14px;margin-bottom:8px}
.jt{width:100%;border-collapse:collapse}.jt th{font-size:13px;color:var(--ink-2);font-weight:600;text-align:left;
padding:6px 0;border-bottom:1px solid var(--rule)}.jt th.num{text-align:right}
.jt td{padding:12px 0;border-bottom:1px solid var(--hair);vertical-align:top}.jt tr:last-child td{border-bottom:0}
.jt td:first-child{padding-right:12px}.jt td+td,.jt th+th{padding-left:14px}
.jt td b{font-weight:800}.jt td small{display:block;color:var(--ink-2);font-size:13px;line-height:1.35}
.jt td.num b{font-size:20px}.jt .grp th{padding-top:16px;font-size:15px;color:var(--ink);font-weight:800;border-bottom:1px solid var(--rule)}
.jt .risk{margin:0;font-size:14px}.jlinks{display:flex;flex-wrap:wrap;gap:0 14px;font-size:14px}
.jlinks .lnk{min-height:36px}
.h-total{margin-top:36px}
.jt small.split{color:var(--low);font-weight:600}
.split-how{border-top:1px solid var(--rule);margin:4px 0 12px;padding-top:12px;font-size:14px}
.split-how ol{margin:8px 0 0;padding-left:20px}.split-how li{margin-bottom:6px}
.tot{background:var(--surface);border:1px solid var(--rule);border-radius:14px;padding:16px 20px;margin-bottom:12px;
display:grid;grid-template-columns:230px 1fr;gap:16px;align-items:center}
.t-label b{display:block;font-size:18px;font-weight:800}.t-label small{display:block;color:var(--ink-2);font-size:13px}
.t-label .risk{margin-top:4px;font-size:14px}
.t-sum{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.t-leg{display:flex;flex-direction:column;line-height:1.25;min-width:150px}.t-leg small{color:var(--ink-2);font-size:13px}
.t-leg b{font-size:24px;font-weight:800}.t-leg span{font-size:13px;color:var(--ink-2)}
.op{font-size:24px;font-weight:800;color:var(--ink-2)}
.t-total{background:var(--sign);color:var(--sign-ink);border-radius:10px;padding:8px 14px}
.t-total small,.t-total span{color:var(--sign-ink)}.t-total b{font-size:28px}
.t-deal{grid-column:1/-1;font-size:14px;border-top:1px dashed var(--rule);padding-top:10px}
/* tickets */
.ticket{display:grid;grid-template-columns:1fr 220px;background:var(--surface);border:1px solid var(--rule);
border-radius:14px;overflow:hidden}
.main{padding:18px 22px 16px;min-width:0}
.ticket h3{font-size:20px;font-weight:800}.ticket h3 small{font-size:15px;font-weight:600;color:var(--ink-2)}
.plan{font-size:15px;color:var(--ink-2)}
.risk{display:flex;align-items:flex-start;gap:8px;font-size:15px;margin-top:6px;font-weight:600}
.dot{width:10px;height:10px;border-radius:50%;flex:none;margin-top:.45em}
.r-low .dot{background:var(--low)}.r-medium .dot{background:var(--medium)}.r-high .dot{background:var(--high)}
.r-low .risk{color:var(--low)}.r-medium .risk{color:var(--medium)}.r-high .risk{color:var(--high)}
.leg{border-top:1px solid var(--hair);margin-top:14px;padding-top:14px}
.leg-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}
.leg-head h4{font-size:16px;font-weight:800}.who{font-size:14px;font-weight:600;padding:0 9px;border-radius:99px;
background:var(--paper);border:1px solid var(--rule)}.airline{margin-left:auto;font-weight:600}
.line{display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:center;margin:10px 0 8px}
.pt{display:flex;flex-direction:column;line-height:1.2}.pt b{font-size:22px;font-weight:800}
.pt span{font-weight:600}.pt small{color:var(--ink-2);font-size:13px}.pt.end{text-align:right}
.path{position:relative;display:flex;flex-direction:column;align-items:center;gap:4px;padding:0 4px}
.path::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:2px dashed var(--rule)}
.dur,.stops{position:relative;background:var(--surface);padding:0 8px;font-size:13px;color:var(--ink-2)}
.stops{display:flex;gap:10px;color:var(--ink);font-weight:600}.stop small{font-weight:400;color:var(--ink-2)}
.sum{font-size:15px}.sum b{font-weight:800}
.book{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;margin-top:8px;font-size:15px}
.btn,.lnk{display:inline-flex;align-items:center;min-height:44px}
.btn{background:var(--ink);color:var(--surface);text-decoration:none;font-weight:700;padding:0 18px;border-radius:8px}
.btn:hover{background:var(--route)}.lnk{font-weight:600;padding:0 2px}
.why{margin-top:10px;font-size:14px;color:var(--ink-2)}.why summary{cursor:pointer;font-weight:600;padding:12px 0}
.why ul{margin:0;padding-left:18px}
/* the stub: perforation + price */
.stub{position:relative;padding:20px 22px;display:flex;flex-direction:column;justify-content:center;
border-left:2px dashed var(--rule);background:var(--paper)}
.stub::before,.stub::after{content:"";position:absolute;left:-11px;width:20px;height:20px;border-radius:50%;
background:var(--paper)}
.stub::before{top:-11px}.stub::after{bottom:-11px}
.opt .stub{border-left:0;border-top:2px dashed var(--rule)}
.opt .stub::before{top:-11px;left:-11px}
.opt .stub::after{top:-11px;bottom:auto;left:auto;right:-11px}
.stub-k{font-size:14px;color:var(--ink-2)}.total{font-size:40px;font-weight:800;line-height:1.05;letter-spacing:-.02em}
.stub dl{margin:14px 0 0;display:grid;grid-template-columns:1fr auto;gap:6px 14px;font-size:15px;max-width:340px}
.stub dt{font-weight:600}.stub dt small{display:block;font-weight:400;color:var(--ink-2);font-size:13px}
.stub dd{margin:0;font-weight:800;text-align:right}
/* risk toggle, no JS */
.toggle{position:relative;border:1px solid var(--rule);padding:0;margin:0 0 16px;display:inline-flex;
background:var(--surface);border-radius:10px}
.toggle input{position:absolute;width:1px;height:1px;opacity:0;margin:0}
.toggle label{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;cursor:pointer;font-weight:600;
font-size:15px;border-radius:9px}
.toggle input:checked+label{background:var(--ink);color:var(--surface)}
.toggle input:focus-visible+label{outline:3px solid var(--focus);outline-offset:-3px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.list-low{display:none}body:has(#show-low:checked) .list-low{display:block}
body:has(#show-low:checked) .list-any{display:none}
/* compact option rows */
.opt{background:var(--surface);border:1px solid var(--rule);border-radius:12px;margin-bottom:10px;overflow:hidden}
.opt>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:1.3fr 1.4fr .9fr 1.3fr 20px;gap:14px;
align-items:center;padding:14px 18px;min-height:44px}
.opt>summary::-webkit-details-marker{display:none}
.opt>summary::after{content:"";width:9px;height:9px;border-right:2px solid var(--ink-2);border-bottom:2px solid var(--ink-2);
transform:rotate(45deg);justify-self:end;margin-top:-4px}
.opt[open]>summary::after{transform:rotate(-135deg);margin-top:4px}
.opt>summary>span{display:flex;flex-direction:column;line-height:1.3}.opt small{color:var(--ink-2);font-size:13px}
.opt>summary .risk{flex-direction:row;margin:0}.o-price{text-align:right}.o-price b{font-size:22px;font-weight:800}
.opt[open]>summary{border-bottom:1px solid var(--hair)}.opt>summary:hover{background:var(--paper)}
.opt .ticket{border:0;border-radius:0;grid-template-columns:1fr}.opt .stub{background:var(--surface)}
/* chart */
.history svg{width:100%;max-width:760px;display:block}.grid{stroke:var(--hair);stroke-width:1}
.tick{fill:var(--ink-2);font-size:12px}.end-lbl{fill:var(--ink);font-size:13px;font-weight:600}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.ln.s1{stroke:var(--s1)}.ln.s2{stroke:var(--s2)}
circle.pt{stroke:var(--paper);stroke-width:2}circle.pt.s1{fill:var(--s1)}circle.pt.s2{fill:var(--s2)}
.legend{font-size:14px;color:var(--ink-2);margin-bottom:6px}.key{display:inline-block;width:16px;height:3px;
border-radius:2px;vertical-align:middle;margin:0 6px 0 0}.key.s1{background:var(--s1)}.key.s2{background:var(--s2);margin-left:18px}
.tips ul{margin:0;padding-left:20px;max-width:72ch}.tips li{margin-bottom:8px}
footer{padding-bottom:40px;color:var(--ink-2);font-size:14px}footer p{max-width:80ch}
@media (max-width:900px){.jgrid{grid-template-columns:1fr}.tot{grid-template-columns:1fr}}
@media (max-width:760px){
 .code{font-size:42px}.band-route{grid-template-columns:1fr 1fr;gap:14px}.flows{grid-column:1/-1;grid-row:2}
 .place.end{grid-column:2;grid-row:1}.flow,.flow.home{flex-direction:row;text-align:left}.track{margin:4px 0}
 .ticket{grid-template-columns:1fr}.stub{border-left:0;border-top:2px dashed var(--rule)}
 .stub::before{top:-11px;left:-11px}.stub::after{top:-11px;bottom:auto;left:auto;right:-11px}
 .main{padding:16px}.pt b{font-size:19px}.airline{margin-left:0;width:100%}
 .jcard{padding:14px 14px 4px}.t-sum{gap:8px}.t-leg{min-width:0}.t-leg b{font-size:21px}.op{font-size:20px}
 .t-total{width:100%}
 .opt>summary{grid-template-columns:1fr auto 14px;gap:6px 12px}.o-when{grid-column:1}.o-route{grid-column:1}
 .opt>summary .risk{grid-column:1}.o-price{grid-column:2;grid-row:1/span 3;align-self:start}
 .opt>summary::after{grid-column:3;grid-row:1/span 3}
}
@media (prefers-reduced-motion:no-preference){.plane{animation:fly 1.6s ease-out 1}
 @keyframes fly{from{left:8%}to{left:50%}}}
"""
