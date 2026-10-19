"""HTML for report.html. Pure functions: data in, one self-contained page out.

Design: the answer first. The whole trip is a receipt (1 person out + 2 people back = total) at three risk levels,
then the flights behind it, then the round-trip alternative, collapsed. One bold element: the airport-signage
yellow route band. Overpass (a highway-signage face) throughout. People are named by where they start
("person from Mumbai", "person from Boston"), never by number; everywhere else it is "person" / "people".
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
cap = lambda t: t[:1].upper() + t[1:]


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
            f"<small>{e(', '.join(f.airlines))}, {day(f.depart)}, {clock(f.depart)}, via {e(via_text(f))}{each}</small>"
            f"</dt><dd>{money(s['total'])}</dd></div>")


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
  <td class=num><b>{money(s['total'])}</b>{each}<small>{money(s['fare'])} fare + {bags}</small>{split_note(s)}</td>
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
def leg(cfg, r, i, name, pax, s):
    f = s["f"]
    p1, p2 = names(cfg)
    rt = name.startswith("Round trip")
    who = cap(p1) if i == 0 else (people(pax) if r["strategy"] == "A" else cap(p2))
    a, b = (cfg["outbound"]["from"], cfg["outbound"]["to"]) if i == 0 else (cfg["return"]["from"], cfg["return"]["to"])
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
    head = f"{r['risk'].capitalize()} risk"
    short = list(dict.fromkeys(short))
    return head + (": " + "; ".join(short) if short else ""), list(dict.fromkeys(full))


def ticket(cfg, geo, r):
    f_home = r["legs"][1][2]["f"]
    airlines = " and ".join(dict.fromkeys(s["f"].airlines[0] for _, _, s in r["legs"]))
    line, full = risk_line(r, geo)
    why = (f"<details class=why><summary>Why {r['risk']} risk, and other notes</summary><ul>"
           + "".join(f"<li>{e(n)}</li>" for n in full) + "</ul></details>") if full else ""
    (_, c1), (_, c2) = r["per_person"]
    p1, p2 = names(cfg)
    return f"""<article class="ticket r-{r['risk']}">
<div class=main>
  <header><h3>{e(airlines)}: leave {e(city(cfg, cfg['return']['from']))} {day(f_home.depart)}
    <small>(land in {e(city(cfg, cfg['return']['to']))} {day(f_home.arrive)})</small></h3>
    <p class=risk><span class="dot"></span>{e(line)}</p></header>
  {''.join(leg(cfg, r, i, n, p, s) for i, (n, p, s) in enumerate(r['legs']))}
  {why}
</div>
<aside class=stub>
  <span class=stub-k>Whole trip</span><b class=total>{money(r['total'])}</b><span class=stub-k>for {people(cfg['return']['adults'])}</span>
  <dl><dt>Round trip <small>{e(p1)}</small></dt><dd>{money(c1)}</dd>
      <dt>One-way home <small>{e(p2)}</small></dt><dd>{money(c2)}</dd></dl>
</aside>
</article>"""


def alt_row(cfg, geo, r):
    leave = day(r["legs"][1][2]["f"].depart)
    airlines = " and ".join(dict.fromkeys(s["f"].airlines[0] for _, _, s in r["legs"]))
    via = ", ".join(dict.fromkeys(n.split(", ")[-1] for _, _, s in r["legs"] for n in (s["f"].layover_names or s["f"].layovers)))
    (_, c1), (_, c2) = r["per_person"]
    return f"""<details class="opt r-{r['risk']}"><summary>
  <span class=o-when><b>Leave {e(city(cfg, cfg['return']['from']))} {leave}</b><small>{e(airlines)}, via {e(via) or 'nonstop'}</small></span>
  <span class=risk><span class=dot></span>{r['risk'].capitalize()} risk</span>
  <span class=o-price><b>{money(r['total'])}</b><small>round trip {money(c1)} + one-way {money(c2)}</small></span>
</summary>{ticket(cfg, geo, r)}</details>"""


def chart(history):
    rows = [(r, s, t) for r, s, t, _ in history]
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
    run_at, _, _, notices, any_opts, low_opts, jr = ev
    trend = chart(history)
    cheapest = jr["totals"][0]["total"] or 0
    seen = {}
    cards = "".join(trip_card(cfg, geo, t, cheapest, seen) for t in jr["totals"])
    alts = [o for o in any_opts if o["strategy"] == "B"]
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
<p>Last checked {checked(run_at)} (Boston time). Prices update every 6 hours{'' if trend else
'; a price trend chart appears once there are 2 days of checks'}.</p></header>
{band(cfg)}
<main>
{warn}
<section aria-labelledby=h-trip><h2 id=h-trip>Whole trip</h2>
<p class=intro>The cheapest flight to {e(city(cfg, cfg['outbound']['to']))} for {people(cfg['outbound']['adults'])}, plus the
cheapest flight home for {people(cfg['return']['adults'])}. Every price includes {cfg['prefs']['bags_per_person']} bags of
23&nbsp;kg per person.</p>
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
small{font-size:14px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.top,main{max-width:1080px;margin:0 auto;padding:0 20px}
.top{padding-top:20px;padding-bottom:14px}.top h1{font-size:20px;font-weight:800}.top p{color:var(--ink-2);font-size:15px}
/* the route band: the one loud element */
.band{background:var(--sign);color:var(--sign-ink);padding:22px 20px}
.band-route{max-width:1040px;margin:0 auto;display:grid;grid-template-columns:auto 1fr auto;gap:24px;align-items:center}
.place{display:flex;flex-direction:column;line-height:1}.place.end{text-align:right}
.code{font-size:56px;font-weight:800;letter-spacing:-.02em}.name{font-size:17px;font-weight:600;margin-top:6px}
.flows{display:grid;gap:10px}
.flow{display:flex;align-items:center;gap:12px;font-size:18px;line-height:1.25}
.flow small{display:block;font-size:15px}.flow.home{flex-direction:row-reverse;text-align:right}
.people{display:inline-flex;gap:4px;flex:none}.person{width:18px;height:29px;fill:currentColor}
.track{position:relative;height:3px;background:var(--sign-ink);border-radius:2px}
.plane{position:absolute;left:50%;top:50%;width:28px;height:28px;transform:translate(-50%,-50%) rotate(90deg);
fill:var(--sign-ink);background:var(--sign);border-radius:50%}
main{padding-top:26px;padding-bottom:48px}
section,.alts{margin-top:44px}section:first-of-type{margin-top:0}
h2{font-size:24px;font-weight:800;margin-bottom:10px}
.intro{color:var(--ink-2);font-size:15px;margin:-2px 0 12px;max-width:80ch}
.alert{margin:0 0 18px;padding:10px 14px;border-left:4px solid var(--high);background:var(--surface)}
.legend-risk{font-size:15px;background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:0 14px;
margin-bottom:16px;max-width:90ch}.legend-risk>summary{cursor:pointer;padding:10px 0;min-height:44px}
.legend-risk .more{color:var(--route);font-weight:600;white-space:nowrap}.legend-risk>p{padding:0 0 12px}
.risk{display:flex;align-items:flex-start;gap:8px;font-size:15px;font-weight:600}
.dot{width:10px;height:10px;border-radius:50%;flex:none;margin-top:.45em}
.r-low .dot{background:var(--low)}.r-medium .dot{background:var(--medium)}.r-high .dot{background:var(--high)}
.r-low .risk{color:var(--low)}.r-medium .risk{color:var(--medium)}.r-high .risk{color:var(--high)}
/* whole-trip receipts */
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;align-items:start}
.tot{background:var(--surface);border:1px solid var(--rule);border-radius:14px;padding:16px 18px}
.t-head h3{font-size:19px;font-weight:800}.t-meta{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center;margin-top:2px}
.delta{font-size:15px;color:var(--ink-2)}
.receipt{margin:14px 0 0}.r-line{display:grid;grid-template-columns:1fr auto;gap:12px;padding:8px 0;
border-top:1px solid var(--hair)}
.r-line dt{font-weight:600;position:relative}.r-line dt small{display:block;font-weight:400;color:var(--ink-2)}
.r-line dd{margin:0;font-weight:800;font-size:20px;text-align:right}
.plus{color:var(--ink-2);font-weight:800;margin-right:4px}
.r-total{border-top:2px solid var(--ink);margin-top:2px;background:var(--sign);color:var(--sign-ink);
border-radius:0 0 8px 8px;padding:10px 12px;margin:2px -12px 0}
.r-total dt{font-weight:800}.r-total dd{font-size:28px}
.t-book{display:grid;gap:8px;margin-top:14px}.t-k{display:block;font-size:14px;color:var(--ink-2);font-weight:600}
.same{margin-top:12px;color:var(--ink-2)}
.split{display:block;color:var(--low);font-weight:600;margin-top:4px}
.deal{margin-top:14px;border-top:1px dashed var(--rule);padding-top:4px}
.deal>summary{cursor:pointer;min-height:44px;display:flex;align-items:center;gap:6px;font-weight:600;color:var(--low)}
.deal>p{font-size:15px;color:var(--ink-2);margin:2px 0 10px}
.deal .ticket{grid-template-columns:1fr;border-radius:10px}
/* journey tables */
.jgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
.jcard{background:var(--surface);border:1px solid var(--rule);border-radius:14px;padding:16px 18px 6px}
.jcard h3{font-size:21px;font-weight:800}.jsub{color:var(--ink-2);font-size:15px;margin-bottom:8px}
.jt{width:100%;border-collapse:collapse}.jt th{font-size:14px;color:var(--ink-2);font-weight:600;text-align:left;
padding:6px 0;border-bottom:1px solid var(--rule)}.jt th.num{text-align:right}
.jt td{padding:12px 0;border-bottom:1px solid var(--hair);vertical-align:top}.jt tr:last-child td{border-bottom:0}
.jt tr.fr td{border-bottom:0;padding-bottom:2px}.jt tr.bk td{padding-top:0}.jt tr.bk .book{margin-top:0}
.jt td+td,.jt th+th{padding-left:14px}
.jt td b{font-weight:800}.jt td small{display:block;color:var(--ink-2);line-height:1.35}
.jt td.num{text-align:right}.jt td.num b{font-size:20px}
.jt .grp th{padding-top:16px;font-size:16px;color:var(--ink);font-weight:800}
.jt .risk{margin:0;font-size:15px}
/* buttons and links */
.book{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin-top:8px;font-size:15px}
.btn,.lnk{display:inline-flex;align-items:center;min-height:44px}
.btn{background:var(--ink);color:var(--surface);text-decoration:none;font-weight:700;padding:0 16px;border-radius:8px}
.btn:hover{background:var(--route)}.lnk{font-weight:600;padding:0 4px}
/* alternatives: round trip + one-way */
.alts>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 14px;
min-height:44px;padding:10px 0;border-bottom:1px solid var(--rule)}
.alts>summary::-webkit-details-marker{display:none}
.alts>summary h2{display:inline;margin:0}.alts>summary span{color:var(--ink-2);font-size:15px}
.alts>summary::after{content:"Show";margin-left:auto;font-weight:600;color:var(--route)}
.alts[open]>summary::after{content:"Hide"}.alts[open]>summary{margin-bottom:12px}
.opt{background:var(--surface);border:1px solid var(--rule);border-radius:12px;margin-bottom:10px;overflow:hidden}
.opt>summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:2fr 1fr 1.4fr 20px;gap:14px;
align-items:center;padding:14px 18px;min-height:44px}
.opt>summary::-webkit-details-marker{display:none}
.opt>summary::after{content:"";width:9px;height:9px;border-right:2px solid var(--ink-2);border-bottom:2px solid var(--ink-2);
transform:rotate(45deg);justify-self:end;margin-top:-4px}
.opt[open]>summary::after{transform:rotate(-135deg);margin-top:4px}
.opt>summary>span{display:flex;flex-direction:column;line-height:1.3}.opt small{color:var(--ink-2)}
.opt>summary .risk{flex-direction:row;margin:0}.o-price{text-align:right}.o-price b{font-size:22px;font-weight:800}
.opt[open]>summary{border-bottom:1px solid var(--hair)}.opt>summary:hover{background:var(--paper)}
.opt .ticket{border:0;border-radius:0}
/* tickets (inside alternatives) */
.ticket{display:grid;grid-template-columns:1fr 230px;background:var(--surface);border:1px solid var(--rule);overflow:hidden}
.main{padding:16px 20px;min-width:0}
.ticket h3{font-size:18px;font-weight:800}.ticket h3 small{font-weight:600;color:var(--ink-2)}
.ticket .risk{margin-top:6px}
.leg{border-top:1px solid var(--hair);margin-top:14px;padding-top:14px}
.leg-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}
.leg-head h4{font-size:16px;font-weight:800}.who{font-size:14px;font-weight:600;padding:0 9px;border-radius:99px;
background:var(--paper);border:1px solid var(--rule)}.airline{margin-left:auto;font-weight:600}
.line{display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:center;margin:10px 0 8px}
.pt{display:flex;flex-direction:column;line-height:1.2}.pt b{font-size:22px;font-weight:800}
.pt span{font-weight:600}.pt small{color:var(--ink-2)}.pt.end{text-align:right}
.path{position:relative;display:flex;flex-direction:column;align-items:center;gap:4px;padding:0 4px}
.path::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:2px dashed var(--rule)}
.dur,.stops{position:relative;background:var(--surface);padding:0 8px;font-size:14px;color:var(--ink-2)}
.stops{display:flex;gap:10px;color:var(--ink);font-weight:600}.stop small{font-weight:400;color:var(--ink-2)}
.sum{font-size:15px}.sum b{font-weight:800}.fine{color:var(--ink-2);font-size:14px;margin-top:6px}
.why{margin-top:8px;font-size:14px;color:var(--ink-2)}.why summary{cursor:pointer;font-weight:600;padding:12px 0}
.why ul{margin:0;padding-left:18px}
.stub{position:relative;padding:18px 20px;display:flex;flex-direction:column;justify-content:center;
border-left:2px dashed var(--rule);background:var(--paper)}
.stub-k{font-size:14px;color:var(--ink-2)}.total{font-size:36px;font-weight:800;line-height:1.05;letter-spacing:-.02em}
.stub dl{margin:12px 0 0;display:grid;grid-template-columns:1fr auto;gap:6px 14px;font-size:15px}
.stub dt{font-weight:600}.stub dt small{display:block;font-weight:400;color:var(--ink-2)}
.stub dd{margin:0;font-weight:800;text-align:right}
.deal .stub,.opt .stub{border-left:0;border-top:2px dashed var(--rule)}
/* chart */
svg{max-width:100%}.grid{stroke:var(--hair);stroke-width:1}
.tick{fill:var(--ink-2);font-size:12px}.end-lbl{fill:var(--ink);font-size:13px;font-weight:600}
.ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.ln.s1{stroke:var(--s1)}.ln.s2{stroke:var(--s2)}
circle.pt{stroke:var(--paper);stroke-width:2}circle.pt.s1{fill:var(--s1)}circle.pt.s2{fill:var(--s2)}
.legend{font-size:14px;color:var(--ink-2);margin-bottom:6px}.key{display:inline-block;width:16px;height:3px;
border-radius:2px;vertical-align:middle;margin:0 6px 0 0}.key.s1{background:var(--s1)}.key.s2{background:var(--s2);margin-left:18px}
@media (max-width:980px){.cards{grid-template-columns:1fr}.jgrid{grid-template-columns:1fr}}
@media (max-width:760px){
 .band{padding:14px 16px}.band-route{grid-template-columns:auto 1fr auto;gap:10px}
 .code{font-size:30px}.name{font-size:14px;margin-top:2px}.flows{grid-column:1/-1;grid-row:2;gap:6px}
 .flow,.flow.home{flex-direction:row;text-align:left;font-size:16px}.flow small{display:inline;font-size:14px}
 .flow small::before{content:", "}.person{width:13px;height:21px}.track{grid-column:2;grid-row:1;align-self:center}
 .flows .track{display:none}.place.end{grid-column:3;grid-row:1}
 .top,main{padding:0 16px}.tot,.jcard{padding:14px}.r-total{margin:2px -14px 0;padding:10px 14px}
 .ticket{grid-template-columns:1fr}.stub{border-left:0;border-top:2px dashed var(--rule)}
 .main{padding:14px}.pt b{font-size:19px}.airline{margin-left:0;width:100%}
 .opt>summary{grid-template-columns:1fr auto 14px;gap:6px 12px}.o-when{grid-column:1}.opt>summary .risk{grid-column:1}
 .o-price{grid-column:2;grid-row:1/span 2;align-self:start}.opt>summary::after{grid-column:3;grid-row:1/span 2}
}
@media (max-width:600px){
 .jt thead{display:none}.jt,.jt tbody{display:block}
 .jt tr{display:grid;grid-template-columns:1fr auto;grid-template-areas:"fl fl" "num rk";gap:4px 12px;
  padding:12px 0;border-bottom:1px solid var(--hair)}
 .jt tr.grp{display:block;padding:14px 0 4px;border-bottom:1px solid var(--rule)}.jt .grp th{padding:0}
 .jt tr.fr{border-bottom:0;padding-bottom:0}.jt tr.bk{display:block;padding:0 0 10px;border-bottom:1px solid var(--hair)}
 .jt td{display:block;padding:0;border:0}.jt td+td{padding-left:0}
 .jt td.fl{grid-area:fl}.jt td.num{grid-area:num;text-align:left}.jt td.rk{grid-area:rk;justify-self:end}
}
@media (prefers-reduced-motion:no-preference){.plane{animation:fly 1.6s ease-out 1}
 @keyframes fly{from{left:8%}to{left:50%}}}
"""
