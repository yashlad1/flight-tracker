"""HTML for report.html. Pure functions: data in, one self-contained page out.

Design: the answer first. The whole trip is a receipt (1 person out + 2 people back = total) at three risk levels,
then the flights behind it, then the round-trip alternative, collapsed. One bold element: the airport-signage
yellow route band. Overpass (a highway-signage face) throughout. People are named by where they start
("person from Mumbai", "person from Boston"), never by number; everywhere else it is "person" / "people".
"""
import html
import urllib.parse
from datetime import datetime
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
cap = lambda t: t[:1].upper() + t[1:]


def hm(minutes):
    return f"{minutes // 60}h {minutes % 60:02d}m"


def clock(iso):
    return datetime.fromisoformat(iso).strftime("%H:%M")


def day(iso):
    return datetime.fromisoformat(iso).strftime("%a %-d %b")


def local(run_at):
    """Run timestamps are UTC with an offset; return Boston time."""
    return datetime.fromisoformat(run_at).astimezone(HOME_TZ)


def checked(run_at):
    return local(run_at).strftime("%a %-d %b, %-I:%M %p").replace("AM", "am").replace("PM", "pm")


def city(cfg, code):
    return cfg.get("cities", {}).get(code, code)


def people(n):
    return "1 person" if n == 1 else f"{n} people"


def names(cfg):
    """(who flies out and back, who flies home only), named by where they start."""
    return f"person from {city(cfg, cfg['outbound']['from'])}", f"person from {city(cfg, cfg['return']['from'])}"


def via_text(f):
    return ", ".join(f"{n.split(', ')[-1]} {hm(m)}" for n, m in zip(f.layover_names or f.layovers, f.layover_min)) or "nonstop"


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
    links.append(("Compare prices", s["url"]))
    return links


def link(label, url, cls):
    return f"<a class={cls} href='{e(url)}' target=_blank rel=noopener>{e(label)}</a>"


def links_html(s, short=False):
    """Primary 'Book on <airline>' button, then text links. short: only the button and 'Compare prices'."""
    ls = book_links(s)
    ls = [ls[0], ls[-1]] if short and len(ls) > 2 else ls
    return "<div class=book>" + "".join(link(n, u, "btn" if i == 0 and n.startswith("Book on") else "lnk")
                                        for i, (n, u) in enumerate(ls)) + "</div>"


# --- pictograms (AIGA-style, inherit currentColor) ----------------------------------------------------------------
PERSON = ("<svg class=person viewBox='0 0 20 32' aria-hidden=true><circle cx=10 cy=5 r=4.5 />"
          "<path d='M4 12a6 6 0 0 1 12 0v9h-2.5v10h-7V21H4z'/></svg>")
PLANE = ("<svg class=plane viewBox='0 0 24 24' aria-hidden=true><path d='M21 15.5v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V8.5"
         "l-8 5v2l8-2.5V18l-2 1.5V21l3.5-1 3.5 1v-1.5L13 18v-5z'/></svg>")


# --- page parts -------------------------------------------------------------------------------------------------
def band(cfg):
    out, ret = cfg["outbound"], cfg["return"]
    lands = datetime.fromisoformat(out["arrive_on"]).strftime("%a %-d %b")
    days = [datetime.fromisoformat(d) for d in ret["depart_dates"]]
    back = ", ".join(d.strftime("%a %-d") for d in days[:-1]) + f" or {days[-1].strftime('%a %-d %b')}"
    a, b = city(cfg, out["from"]), city(cfg, out["to"])
    return f"""<section class=band aria-label="The trip">
<div class=band-route>
  <div class=place><span class=code>{e(out['from'])}</span><span class=name>{e(a)}</span></div>
  <div class=flows>
    <div class="flow go"><span class=people aria-hidden=true>{PERSON * out['adults']}</span>
      <span><b>{people(out['adults'])}</b> to {e(b)}<small>landing {lands}</small></span></div>
    <div class=track>{PLANE}</div>
    <div class="flow home"><span class=people aria-hidden=true>{PERSON * ret['adults']}</span>
      <span><b>{people(ret['adults'])}</b> home to {e(a)}<small>leaving {back}</small></span></div>
  </div>
  <div class="place end"><span class=code>{e(out['to'])}</span><span class=name>{e(b)}</span></div>
</div>
</section>"""


def risk_legend(jr, geo, notices):
    hubs = sorted({n.split(", ")[-1] for v in [jr["out"], *jr["ret"].values()] for s in v
                   for c, n in zip(s["f"].layovers, s["f"].layover_names or s["f"].layovers)
                   if geo.get("hubs", {}).get(c, {}).get("level") == "high"})
    high = f"connects through {', '.join(hubs)}, where flights were closed or cancelled at short notice this year" \
        if hubs else "connects through an airport with major disruption this year"
    note = "".join(f" Google Flights also shows a general notice for these routes: {e(n[0].lower() + n[1:])}"
                   for n in sorted(notices))
    return (f"<details class=legend-risk><summary><b>Risk</b> means the chance of a cancellation or long delay, not "
            f"safety. <span class=more>What the levels mean</span></summary><p><b>High</b>: {e(high)}. <b>Medium</b>: "
            f"an airline or airport with strikes or other disruption this year. <b>Low</b>: no known problems.{note}</p>"
            f"</details>")


def receipt_line(cfg, s, a, b, first):
    f, pax = s["f"], s["pax"]
    each = f", {money(s['total'] / pax)} each" if pax > 1 else ""
    return (f"<div class=r-line><dt>{'' if first else '<span class=plus aria-hidden=true>+</span>'}"
            f"{e(city(cfg, a))} to {e(city(cfg, b))}, {people(pax)}"
            f"<small>{e(', '.join(f.airlines))}, {day(f.depart)}, {clock(f.depart)}, via {e(via_text(f))}{each}. "
            f"{money(s['fare'])} fare + {'bags included' if not s['bags'] else money(s['bags']) + ' bags'}</small>"
            f"{upgrade_note(s)}</dt><dd>{money(s['total'])}</dd></div>")


def upgrade_note(s):
    """Where bags cost extra but a higher fare includes 2 x 23 kg, say so: upgrading is often cheaper."""
    fare = s.get("two_bag_fare")
    return (f"<small class=upg>Or choose {e(s['bag_rule'])}'s {e(fare)} fare or higher: 2 × 23&nbsp;kg included. "
            f"Compare it with {money(s['bags'])} in bag fees.</small>") if fare else ""


def split_note(s):
    sp = s.get("split")
    return (f"<small class=split>About {money(sp['saving'])} less if the {s['pax']} people book separately. It is then "
            f"two bookings: if one is changed or cancelled, the other is not rebooked with it.</small>") if sp else ""


def trip_card(cfg, geo, t, cheapest, seen):
    out, ret = cfg["outbound"], cfg["return"]
    if not t["total"]:
        return f"<article class=tot><h3>{e(t['label'])}</h3><p>No flights match.</p></article>"
    o, r = t["out"], t["ret"]
    same = seen.setdefault((id(o), id(r)), t["label"])
    delta = t["total"] - cheapest
    extra = f"<span class=delta>{money(delta)} more than the cheapest</span>" if delta > 0 else ""
    body = (f"<p class=same>Same flights as “{e(same)}”.</p>" if same != t["label"] else f"""<dl class=receipt>
  {receipt_line(cfg, o, out['from'], out['to'], True)}
  {receipt_line(cfg, r, ret['from'], ret['to'], False)}
  <div class="r-line r-total"><dt>Whole trip, {people(ret['adults'])}</dt><dd>{money(t['total'])}</dd></div>
</dl>
<div class=t-book>
  <div><span class=t-k>{e(city(cfg, out['from']))} to {e(city(cfg, out['to']))}</span>{links_html(o, short=True)}</div>
  <div><span class=t-k>{e(city(cfg, ret['from']))} to {e(city(cfg, ret['to']))}</span>{links_html(r, short=True)}</div>
</div>{split_note(r)}""")
    deal = t["deal"]
    p1, p2 = names(cfg)
    deal_html = (f"""<details class=deal><summary>Cheaper way to book this: <b>{money(deal['total'])}</b>, saves
{money(t['total'] - deal['total'])}</summary>
<p>Buy a round trip for the {e(p1)} and a one-way for the {e(p2)}, on the same flight home. It is two bookings: if
one is changed or cancelled, the other is not rebooked with it.</p>{ticket(cfg, geo, deal)}</details>"""
                 if deal and same == t["label"] and deal["total"] < t["total"] else "")
    return f"""<article class="tot r-{t['risk']}">
<header class=t-head><h3>{e(t['label'])}</h3>
  <p class=t-meta><span class=risk><span class=dot></span>{t['risk'].capitalize()} risk</span>{extra}</p></header>
{body}{deal_html}
</article>"""


def j_row(cfg, s, a, b):
    """One flight in a journey table (a card on phones)."""
    f, pax = s["f"], s["pax"]
    lands = "" if f.arrive[:10] == f.depart[:10] else f" ({day(f.arrive)})"
    bags = "bags included" if not s["bags"] else f"{money(s['bags'])} bags"
    each = f"<small>{money(s['total'] / pax)} each</small>" if pax > 1 else ""
    return f"""<tr class="fr r-{s['risk']}">
  <td class=fl><b>{e(', '.join(f.airlines))}</b>
    <small>{day(f.depart)}: {clock(f.depart)} {e(city(cfg, a))} to {clock(f.arrive)} {e(city(cfg, b))}{lands}</small>
    <small>via {e(via_text(f))}</small></td>
  <td class=num><b>{money(s['total'])}</b>{each}<small>{money(s['fare'])} fare + {bags}</small>{upgrade_note(s)}{split_note(s)}</td>
  <td class=rk><span class=risk><span class=dot></span>{s['risk'].capitalize()}</span></td>
</tr><tr class=bk><td colspan=3>{links_html(s)}</td></tr>"""


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
    a, b = e(city(cfg, out["from"])), e(city(cfg, out["to"]))
    table = lambda cap_, who, rows: (f"<table class=jt><caption class=sr>{cap_}</caption><thead><tr>"
                                     f"<th scope=col>Flight</th><th scope=col class=num>Price for {who}</th>"
                                     f"<th scope=col>Risk</th></tr></thead><tbody>{rows}</tbody></table>")
    return f"""<div class=jgrid>
<div class=jcard><h3>{a} to {b}</h3><p class=jsub>{people(out['adults'])}, landing {lands}, cheapest first</p>
  {table(f"{a} to {b} flights, price for {people(out['adults'])}", people(out['adults']), o_rows)}</div>
<div class=jcard><h3>{b} to {a}</h3><p class=jsub>{people(ret['adults'])}, cheapest {per_date} for each day</p>
  {table(f"{b} to {a} flights, price for {people(ret['adults'])}", people(ret['adults']), r_rows)}</div>
</div>"""


# --- round trip + one-way tickets (in the collapsed alternatives section) ----------------------------------------
def leg(cfg, i, pax, s):
    """Leg 0 of a Plan B option is the round trip, leg 1 the one-way home."""
    f = s["f"]
    p1, p2 = names(cfg)
    rt = i == 0
    who = cap(p1 if rt else p2)
    a, b = (cfg["outbound"]["from"], cfg["outbound"]["to"]) if rt else (cfg["return"]["from"], cfg["return"]["to"])
    title = f"{e(city(cfg, a))} to {e(city(cfg, b))}" + (" and back, round trip" if rt else "")
    stops = "".join(f"<span class=stop>{e(c.split(', ')[-1])} <small>{hm(m)}</small></span>"
                    for c, m in zip(f.layover_names or f.layovers, f.layover_min)) or "<span class=stop>Nonstop</span>"
    bags = "bags included" if not s["bags"] else f"{money(s['bags'])} bags"
    each = f", {money(s['total'] / pax)} each" if pax > 1 else ""
    rt_note = (f"<p class=fine>This ticket also covers the {e(p1)}'s flight home: choose the same return flight as "
               f"the {e(p2)}'s ticket below. The fare and bags shown cover both directions.</p>" if rt else "")
    return f"""<div class=leg>
  <div class=leg-head><h4>{title}</h4><span class=who>{e(who)}</span><span class=airline>{e(', '.join(f.airlines))}</span></div>
  <div class=line>
    <div class=pt><b>{clock(f.depart)}</b><span>{e(city(cfg, a))}</span><small>{day(f.depart)}</small></div>
    <div class=path><span class=dur>{hm(f.duration_min)}</span><span class=stops>{stops}</span></div>
    <div class="pt end"><b>{clock(f.arrive)}</b><span>{e(city(cfg, b))}</span><small>{day(f.arrive)}</small></div>
  </div>
  <p class=sum><span class=nw>{money(s['fare'])} fare</span> + <span class=nw>{bags}</span> =
    <span class=nw><b>{money(s['total'])}</b> for {people(pax)}{each}</span></p>
  {rt_note}{links_html(s)}
</div>"""


def risk_line(r, geo):
    short, full = [], []
    for _, s in r["legs"]:
        f = s["f"]
        for code, name in zip(f.layovers, f.layover_names or f.layovers):
            if geo.get("hubs", {}).get(code, {}).get("level", "low") != "low":
                short.append(f"connects in {name.split(', ')[-1]}")
        for a in f.airlines:
            lvl = geo.get("airlines", {}).get(a, {}).get("level", "low")
            if lvl != "low":
                short.append(f"{a} rated {lvl}")
        full += s["notes"]
    full.append("round-trip return leg not pinned: total is Google's cheapest pairing, price the exact return "
                "flight before booking")
    head = f"{r['risk'].capitalize()} risk"
    short = list(dict.fromkeys(short))
    return head + (": " + "; ".join(short) if short else ""), list(dict.fromkeys(full))


def ticket(cfg, geo, r):
    f_home = r["legs"][1][1]["f"]
    airlines = " and ".join(dict.fromkeys(s["f"].airlines[0] for _, s in r["legs"]))
    line, full = risk_line(r, geo)
    why = (f"<details class=why><summary>Why {r['risk']} risk, and other notes</summary><ul>"
           + "".join(f"<li>{e(n)}</li>" for n in full) + "</ul></details>") if full else ""
    c1, c2 = r["per_person"]
    p1, p2 = names(cfg)
    return f"""<article class="ticket r-{r['risk']}">
<div class=main>
  <header><h3>{e(airlines)}: leave {e(city(cfg, cfg['return']['from']))} {day(f_home.depart)}
    <small>(land in {e(city(cfg, cfg['return']['to']))} {day(f_home.arrive)})</small></h3>
    <p class=risk><span class="dot"></span>{e(line)}</p></header>
  {''.join(leg(cfg, i, p, s) for i, (p, s) in enumerate(r['legs']))}
  {why}
</div>
<aside class=stub>
  <span class=stub-k>Whole trip</span><b class=total>{money(r['total'])}</b><span class=stub-k>for {people(cfg['return']['adults'])}</span>
  <dl><dt>Round trip <small>{e(p1)}</small></dt><dd>{money(c1)}</dd>
      <dt>One-way home <small>{e(p2)}</small></dt><dd>{money(c2)}</dd></dl>
</aside>
</article>"""


def alt_row(cfg, geo, r):
    leave = day(r["legs"][1][1]["f"].depart)
    airlines = " and ".join(dict.fromkeys(s["f"].airlines[0] for _, s in r["legs"]))
    via = ", ".join(dict.fromkeys(n.split(", ")[-1] for _, s in r["legs"] for n in (s["f"].layover_names or s["f"].layovers)))
    c1, c2 = r["per_person"]
    return f"""<details class="opt r-{r['risk']}"><summary>
  <span class=o-when><b>Leave {e(city(cfg, cfg['return']['from']))} {leave}</b><small>{e(airlines)}, via {e(via) or 'nonstop'}</small></span>
  <span class=risk><span class=dot></span>{r['risk'].capitalize()} risk</span>
  <span class=o-price><b>{money(r['total'])}</b><small>round trip {money(c1)} + one-way {money(c2)}</small></span>
</summary>{ticket(cfg, geo, r)}</details>"""


def chart(rows):
    """rows: [(run_at, scope, total)] from the best table."""
    runs = sorted({r for r, _, _ in rows})
    if len({local(r).date() for r in runs}) < 2:
        return ""
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
    for n, (scope, name) in enumerate((("any", "Cheapest"), ("low", "Lowest risk"))):
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
            "Lowest-risk whole trip</p>" + "".join(svg) + "</svg>")


def page(cfg, geo, ev, gaps, history):
    run_at, _, notices, alts, jr = ev
    trend = chart(history)
    cheapest = jr["totals"][0]["total"] or 0
    seen = {}
    cards = "".join(trip_card(cfg, geo, t, cheapest, seen) for t in jr["totals"])
    p1, p2 = names(cfg)
    warn = "".join(f"<p class=alert>No results for {e(g)} on the last check, so prices may be incomplete.</p>"
                   for g in gaps)
    alt_html = (f"""<details class=alts><summary><h2>Other ways to book: round trip + one-way</h2>
<span>{len(alts)} option{'s' if len(alts) != 1 else ''}, from {money(alts[0]['total'])}</span></summary>
<p class=intro>A round trip for the {e(p1)} plus a one-way for the {e(p2)} on the same flight home. Sometimes cheaper,
but it is two bookings: if one is changed or cancelled, the other is not rebooked with it.</p>
{''.join(alt_row(cfg, geo, o) for o in alts)}</details>""" if alts else "")
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Flight Price Tracker</title>
<meta name=robots content="noindex, nofollow, noarchive">
<link rel=preconnect href=https://fonts.googleapis.com><link rel=preconnect href=https://fonts.gstatic.com crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;800&display=swap" rel=stylesheet>
<style>{CSS}</style></head>
<body>
<header class=top><h1>{e(cfg.get('title', 'Flight price tracker'))}</h1>
<p>Last checked {checked(run_at)}, Boston time. Updates every 6 hours.</p></header>
{band(cfg)}
<main>
{warn}
<section aria-labelledby=h-trip><h2 id=h-trip>Whole trip</h2>
<p class=intro>{cap(people(cfg['outbound']['adults']))} to {e(city(cfg, cfg['outbound']['to']))} plus
{people(cfg['return']['adults'])} home, with {cfg['prefs']['bags_per_person']} bags of 23&nbsp;kg each.</p>
{risk_legend(jr, geo, notices)}
<div class=cards>{cards}</div></section>
<section aria-labelledby=h-flights><h2 id=h-flights>All flights by journey</h2>
<p class=intro>Pick a different flight. Each price is for everyone on that flight, bags included.</p>
{journeys_html(cfg, jr)}</section>
{alt_html}
{f'<section aria-labelledby=h-hist><h2 id=h-hist>Price over time</h2>{trend}</section>' if trend else ''}
</main>
</body></html>"""


CSS = """
:root{color-scheme:light;
--paper:#f5f7fa;--surface:#fff;--ink:#14213d;--ink-2:#4a5672;--rule:#a9b4c8;--hair:#e1e6ef;
--sign:#ffcc00;--sign-ink:#14213d;--route:#2f5bea;--low:#1e7f4f;--medium:#a15c00;--high:#b4312a;
--s1:#2a78d6;--s2:#c4501f;--focus:#2f5bea;
/* type scale: 14 / 16 / 18 / 22 / 26 / 32, three weights, three line heights */
--t-sm:14px;--t-md:16px;--t-lg:18px;--t-num:22px;--t-h2:26px;--t-total:32px;--t-code:48px;
--w-reg:400;--w-mid:600;--w-bold:800;--lh-text:1.5;--lh-head:1.25;--lh-num:1.1;
/* spacing scale: multiples of 4 */
--sp-1:4px;--sp-2:8px;--sp-3:12px;--sp-4:16px;--sp-5:24px;--sp-6:32px;--sp-7:48px;
--pad:20px;--radius:12px}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--paper:#0f1828;--surface:#16213a;--ink:#e9eef7;
--ink-2:#a9b4ca;--rule:#4a5a80;--hair:#26324f;--route:#8eaaff;--low:#4fbf85;--medium:#e0a33a;--high:#f07a72;
--s1:#3987e5;--s2:#e8743d;--focus:#ffcc00}}
@media (max-width:760px){:root{--pad:16px;--t-code:32px;--t-h2:22px;--t-total:28px}}

*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:var(--w-reg) var(--t-md)/var(--lh-text) Overpass,system-ui,sans-serif;
font-variant-numeric:tabular-nums}
h1,h2,h3,h4,p,dl,dd,ul,ol{margin:0}
h1,h2,h3,h4{line-height:var(--lh-head);font-weight:var(--w-bold)}
b,strong{font-weight:var(--w-bold)}
small{font-size:var(--t-sm);line-height:1.4}
a{color:var(--route)}
a:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:4px}
.nw{white-space:nowrap}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

/* page frame */
.top,main{max-width:1080px;margin:0 auto;padding:0 var(--sp-5)}
.top{padding-top:var(--sp-5);padding-bottom:var(--sp-4)}
.top h1{font-size:var(--t-lg)}.top p{font-size:var(--t-sm);color:var(--ink-2);margin-top:var(--sp-1)}
main{padding-top:var(--sp-6);padding-bottom:var(--sp-7)}
section+section,section+.alts,.alts+section{margin-top:var(--sp-7)}
h2{font-size:var(--t-h2);margin-bottom:var(--sp-2)}
.intro{font-size:var(--t-md);color:var(--ink-2);max-width:72ch;margin-bottom:var(--sp-4)}
.alert{margin-bottom:var(--sp-5);padding:var(--sp-3) var(--sp-4);border-left:4px solid var(--high);background:var(--surface)}

/* the route band: the one loud element */
.band{background:var(--sign);color:var(--sign-ink);padding:var(--sp-5) var(--sp-5)}
.band-route{max-width:1032px;margin:0 auto;display:grid;grid-template-columns:auto 1fr auto;gap:var(--sp-5);
align-items:center}
.place{display:flex;flex-direction:column;gap:var(--sp-1);line-height:1}.place.end{text-align:right}
.code{font-size:var(--t-code);font-weight:var(--w-bold);letter-spacing:-.02em}
.name{font-size:var(--t-md);font-weight:var(--w-mid)}
.flows{display:grid;gap:var(--sp-3)}
.flow{display:flex;align-items:center;gap:var(--sp-3);font-size:var(--t-lg);line-height:var(--lh-head)}
.flow small{display:block;margin-top:2px}.flow.home{flex-direction:row-reverse;text-align:right}
.people{display:inline-flex;gap:var(--sp-1);flex:none}.person{width:16px;height:26px;fill:currentColor}
.track{position:relative;height:3px;background:var(--sign-ink);border-radius:2px}
.plane{position:absolute;left:50%;top:50%;width:28px;height:28px;transform:translate(-50%,-50%) rotate(90deg);
fill:var(--sign-ink);background:var(--sign);border-radius:50%}

/* shared pieces */
.risk{display:flex;align-items:flex-start;gap:var(--sp-2);font-size:var(--t-md);font-weight:var(--w-mid)}
.dot{width:10px;height:10px;border-radius:50%;flex:none;margin-top:7px}
.r-low .dot{background:var(--low)}.r-medium .dot{background:var(--medium)}.r-high .dot{background:var(--high)}
.r-low .risk{color:var(--low)}.r-medium .risk{color:var(--medium)}.r-high .risk{color:var(--high)}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);padding:var(--pad)}
.book{display:flex;flex-wrap:wrap;align-items:center;gap:var(--sp-2) var(--sp-4);margin-top:var(--sp-3);
font-size:var(--t-md)}
.btn,.lnk{display:inline-flex;align-items:center;min-height:44px}
.btn{background:var(--ink);color:var(--surface);text-decoration:none;font-weight:var(--w-mid);
padding:0 var(--sp-4);border-radius:8px}
.btn:hover{background:var(--route)}.lnk{font-weight:var(--w-mid)}

/* risk legend */
.legend-risk{background:var(--surface);border:1px solid var(--hair);border-radius:var(--radius);
padding:0 var(--pad);margin-bottom:var(--sp-5);max-width:72ch}
.legend-risk>summary{cursor:pointer;padding:var(--sp-3) 0;min-height:44px}
.legend-risk .more{color:var(--route);font-weight:var(--w-mid);white-space:nowrap}
.legend-risk>p{padding-bottom:var(--sp-4)}

/* whole-trip receipts */
.cards{display:grid;gap:var(--sp-4)}
.tot{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);padding:var(--pad)}
.t-head h3{font-size:var(--t-lg)}
.t-meta{display:flex;flex-wrap:wrap;gap:var(--sp-1) var(--sp-4);align-items:flex-start;margin-top:var(--sp-2)}
.delta{font-size:var(--t-md);color:var(--ink-2)}
.receipt{margin-top:var(--sp-4)}
.r-line{display:grid;grid-template-columns:1fr auto;gap:var(--sp-3);padding:var(--sp-3) 0;border-top:1px solid var(--hair)}
.r-line dt{font-weight:var(--w-mid)}.r-line dt small{display:block;font-weight:var(--w-reg);color:var(--ink-2);margin-top:2px}
.r-line dd{font-weight:var(--w-bold);font-size:var(--t-num);line-height:var(--lh-num);text-align:right}
.plus{color:var(--ink-2);font-weight:var(--w-bold);margin-right:var(--sp-1)}
.r-total{background:var(--sign);color:var(--sign-ink);border-top:0;border-radius:8px;
padding:var(--sp-3) var(--sp-4);margin-top:var(--sp-1);align-items:center}
.r-total dt{font-weight:var(--w-bold)}.r-total dd{font-size:var(--t-total)}
.t-book{display:grid;gap:var(--sp-3);margin-top:var(--sp-4);padding-top:var(--sp-4);border-top:1px solid var(--hair)}
.t-book .book{margin-top:var(--sp-1)}
.t-k{display:block;font-size:var(--t-sm);color:var(--ink-2);font-weight:var(--w-mid)}
.same{margin-top:var(--sp-3);color:var(--ink-2)}
.split{display:block;color:var(--low);font-weight:var(--w-mid);margin-top:var(--sp-2)}
.upg{display:block;color:var(--route);font-weight:var(--w-reg);margin-top:var(--sp-1)}
.jt td.num .upg{max-width:30ch;margin-left:auto}
.deal{margin-top:var(--sp-4);border-top:1px dashed var(--rule)}
.deal>summary{cursor:pointer;min-height:44px;display:flex;flex-wrap:wrap;align-items:center;gap:var(--sp-1) var(--sp-2);
padding:var(--sp-2) 0;font-weight:var(--w-mid);color:var(--low)}
.deal>p{color:var(--ink-2);margin-bottom:var(--sp-3)}
.deal .ticket{grid-template-columns:1fr;border-radius:var(--radius)}

@media (min-width:981px){
 .tot{display:grid;grid-template-columns:200px minmax(0,1fr) 250px;column-gap:var(--sp-6);align-items:start}
 .tot>.receipt{margin-top:0}.tot>.receipt .r-line:first-child{border-top:0;padding-top:0}
 .tot>.t-book{margin-top:0;padding-top:0;border-top:0;padding-left:var(--sp-5);border-left:1px solid var(--hair)}
 .tot>.split,.tot>.deal,.tot>.same{grid-column:1/-1}.tot>.same{grid-column:2/-1;margin-top:0}
}
/* journey tables */
.jgrid{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-4);align-items:start}
.jcard{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
padding:var(--pad) var(--pad) var(--sp-2)}
.jcard h3{font-size:var(--t-lg)}.jsub{color:var(--ink-2);font-size:var(--t-sm);margin:var(--sp-1) 0 var(--sp-3)}
.jt{width:100%;border-collapse:collapse}
.jt th{font-size:var(--t-sm);color:var(--ink-2);font-weight:var(--w-mid);text-align:left;
padding:var(--sp-2) 0;border-bottom:1px solid var(--rule)}
.jt th.num{text-align:right}
.jt td{padding:var(--sp-4) 0 var(--sp-1);vertical-align:top}
.jt td+td,.jt th+th{padding-left:var(--sp-4)}
.jt td b{font-weight:var(--w-bold)}.jt td small{display:block;color:var(--ink-2);margin-top:2px}
.jt td.fl b{font-size:var(--t-md)}
.jt td.num{text-align:right}.jt td.num b{font-size:var(--t-num);line-height:var(--lh-num)}
.jt tr.bk td{padding:0 0 var(--sp-4);border-bottom:1px solid var(--hair)}.jt tr.bk .book{margin-top:var(--sp-1)}
.jt tr:last-child td{border-bottom:0}
.jt .grp th{padding:var(--sp-5) 0 var(--sp-2);font-size:var(--t-md);color:var(--ink);font-weight:var(--w-bold)}
.jt tbody tr.grp:first-child th{padding-top:var(--sp-3)}
.jt .risk{font-size:var(--t-sm)}.jt .risk .dot{margin-top:5px}

/* alternatives: round trip + one-way */
.alts>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--sp-1) var(--sp-4);
min-height:44px;padding-bottom:var(--sp-3);border-bottom:1px solid var(--rule)}
.alts>summary::-webkit-details-marker{display:none}
.alts>summary h2{display:inline;margin:0}.alts>summary span{color:var(--ink-2)}
.alts>summary::after{content:"Show";margin-left:auto;font-weight:var(--w-mid);color:var(--route)}
.alts[open]>summary::after{content:"Hide"}
.alts>.intro{margin-top:var(--sp-4)}
.opt{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);margin-bottom:var(--sp-3);overflow:hidden}
.opt>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:2fr 1fr 1.4fr 16px;gap:var(--sp-4);
align-items:center;padding:var(--sp-4) var(--pad);min-height:44px}
.opt>summary::-webkit-details-marker{display:none}
.opt>summary::after{content:"";width:8px;height:8px;border-right:2px solid var(--ink-2);border-bottom:2px solid var(--ink-2);
transform:rotate(45deg);justify-self:end;margin-top:-4px}
.opt[open]>summary::after{transform:rotate(-135deg);margin-top:4px}
.opt>summary>span{display:flex;flex-direction:column;gap:2px;line-height:1.3}.opt small{color:var(--ink-2)}
.opt>summary .risk{flex-direction:row}.o-price{text-align:right}
.o-price b{font-size:var(--t-num);line-height:var(--lh-num)}
.opt[open]>summary{border-bottom:1px solid var(--hair)}.opt>summary:hover{background:var(--paper)}
.opt .ticket{border:0;border-radius:0}

/* tickets (inside alternatives) */
.ticket{display:grid;grid-template-columns:1fr 240px;background:var(--surface);border:1px solid var(--rule);overflow:hidden}
.main{padding:var(--pad);min-width:0}
.ticket h3{font-size:var(--t-lg)}.ticket h3 small{font-weight:var(--w-mid);color:var(--ink-2)}
.ticket header .risk{margin-top:var(--sp-2)}
.leg{border-top:1px solid var(--hair);margin-top:var(--sp-4);padding-top:var(--sp-4)}
.leg-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--sp-1) var(--sp-3)}
.leg-head h4{font-size:var(--t-md)}
.who{font-size:var(--t-sm);font-weight:var(--w-mid);padding:0 var(--sp-2);border-radius:99px;background:var(--paper);
border:1px solid var(--rule)}
.airline{margin-left:auto;font-weight:var(--w-mid)}
.line{display:grid;grid-template-columns:auto 1fr auto;gap:var(--sp-3);align-items:center;margin:var(--sp-3) 0}
.pt{display:flex;flex-direction:column;gap:2px;line-height:1.2}.pt b{font-size:var(--t-num)}
.pt span{font-weight:var(--w-mid)}.pt small{color:var(--ink-2)}.pt.end{text-align:right}
.path{position:relative;display:flex;flex-direction:column;align-items:center;gap:var(--sp-1);padding:0 var(--sp-1)}
.path::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:2px dashed var(--rule)}
.dur,.stops{position:relative;background:var(--surface);padding:0 var(--sp-2);font-size:var(--t-sm);color:var(--ink-2)}
.stops{display:flex;gap:var(--sp-3);color:var(--ink);font-weight:var(--w-mid)}.stop small{font-weight:var(--w-reg);color:var(--ink-2)}
.fine{color:var(--ink-2);font-size:var(--t-sm);margin-top:var(--sp-2)}
.why{margin-top:var(--sp-3);font-size:var(--t-sm);color:var(--ink-2)}
.why summary{cursor:pointer;font-weight:var(--w-mid);min-height:44px;display:flex;align-items:center}
.why ul{padding-left:var(--sp-5)}
.stub{padding:var(--pad);display:flex;flex-direction:column;justify-content:center;gap:var(--sp-1);
border-left:2px dashed var(--rule);background:var(--paper)}
.stub-k{font-size:var(--t-sm);color:var(--ink-2)}
.total{font-size:var(--t-total);font-weight:var(--w-bold);line-height:var(--lh-num);letter-spacing:-.01em}
.stub dl{margin-top:var(--sp-3);display:grid;grid-template-columns:1fr auto;gap:var(--sp-2) var(--sp-4)}
.stub dt{font-weight:var(--w-mid)}.stub dt small{display:block;font-weight:var(--w-reg);color:var(--ink-2)}
.stub dd{font-weight:var(--w-bold);text-align:right}
.deal .stub,.opt .stub{border-left:0;border-top:2px dashed var(--rule)}

/* chart */
svg{max-width:100%}.grid{stroke:var(--hair);stroke-width:1}
.tick{fill:var(--ink-2);font-size:12px}.end-lbl{fill:var(--ink);font-size:13px;font-weight:var(--w-mid)}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.ln.s1{stroke:var(--s1)}.ln.s2{stroke:var(--s2)}
circle.pt{stroke:var(--paper);stroke-width:2}circle.pt.s1{fill:var(--s1)}circle.pt.s2{fill:var(--s2)}
.legend{font-size:var(--t-sm);color:var(--ink-2);margin-bottom:var(--sp-2)}
.key{display:inline-block;width:16px;height:3px;border-radius:2px;vertical-align:middle;margin-right:var(--sp-2)}
.key.s1{background:var(--s1)}.key.s2{background:var(--s2);margin-left:var(--sp-4)}

/* layout breakpoints */
@media (max-width:980px){.jgrid{grid-template-columns:1fr}}
@media (max-width:760px){
 .top,main{padding:0 var(--sp-4)}.top{padding-top:var(--sp-4);padding-bottom:var(--sp-3)}main{padding-top:var(--sp-5)}
 .band{padding:var(--sp-4)}.band-route{gap:var(--sp-2) var(--sp-3)}
 .flows{grid-column:1/-1;grid-row:2;gap:var(--sp-2)}.flows .track{display:none}.place.end{grid-column:3;grid-row:1}
 .flow,.flow.home{flex-direction:row;text-align:left;font-size:var(--t-md)}
 .flow small{display:inline;margin:0}.flow small::before{content:", "}.person{width:12px;height:20px}
 .ticket{grid-template-columns:1fr}.stub{border-left:0;border-top:2px dashed var(--rule)}
 .airline{margin-left:0;width:100%}
 .opt>summary{grid-template-columns:1fr auto 12px;gap:var(--sp-2) var(--sp-3)}.o-when,.opt>summary .risk{grid-column:1}
 .o-price{grid-column:2;grid-row:1/span 2;align-self:start}.opt>summary::after{grid-column:3;grid-row:1/span 2}
}
@media (max-width:600px){
 .jt thead{display:none}.jt,.jt tbody{display:block}
 .jt tr.fr{display:grid;grid-template-columns:1fr auto;grid-template-areas:"fl fl" "num rk";gap:var(--sp-2) var(--sp-3);
  padding-top:var(--sp-4)}
 .jt tr.grp{display:block;border-bottom:1px solid var(--rule)}.jt .grp th{display:block;padding:var(--sp-5) 0 var(--sp-2)}
 .jt tbody tr.grp:first-child th{padding-top:var(--sp-2)}
 .jt td{display:block;padding:0}.jt td+td{padding-left:0}
 .jt td.fl{grid-area:fl}.jt td.num{grid-area:num;text-align:left}.jt td.rk{grid-area:rk;justify-self:end}
 .jt tr.bk{display:block;border-bottom:1px solid var(--hair)}.jt tr.bk td{display:block;padding:0 0 var(--sp-4)}
}
@media (prefers-reduced-motion:no-preference){.plane{animation:fly 1.6s ease-out 1}
 @keyframes fly{from{left:8%}to{left:50%}}}
"""
