"""Self-check: python3 test_tracker.py (also runs under pytest)."""
from pathlib import Path

import gflights
import render
import tracker
from gflights import Flight

ROW = ('<li><div aria-label="From {p} US dollars{rt}. {stops} flight with {al}. Leaves Boston Logan International '
       'Airport at 6:09 PM on Saturday, December 26 and arrives at Chhatrapati Shivaji Maharaj International '
       'Airport Mumbai at 2:50 AM on {arr}. Total duration 22 hr 11 min.  Layover (1 of 2) is a 1 hr 28 min '
       'layover at John F. Kennedy International Airport in New York. Layover (2 of 2) is a 9 hr layover at Hamad '
       'International Airport in Doha. Select flight"><span>{codes}</span>{badge}</div></li>')
PAGE = ("<div><h2>Travel update</h2><span>Air traffic disruptions may affect flights.</span></div>"
        "<div><span>Prices are currently </span><span>typical</span></div>"
        + ROW.format(p="1,807", rt="", stops="2 stops", al="JetBlue, Qatar Airways and IndiGo",
                     arr="Monday, December 28", codes="2 stops in JFK, DOH", badge="")
        + ROW.format(p="904", rt=" round trip total", stops="2 stops", al="Etihad", arr="Friday, January 1",
                     codes="2 stops in JFK, DOH", badge="<span>Self transfer</span>"))


def test_tfs_matches_known_good_query():
    # captured from a working Google Flights URL: BOS->BOM 2026-12-26, 2 adults, economy, one-way
    assert gflights.tfs([("2026-12-26", "BOS", "BOM")], 2) == "GhoSCjIwMjYtMTItMjZqBRIDQk9TcgUSA0JPTUICAQFIAZgBAg"


def test_parse():
    flights, level, notice = gflights.parse(PAGE, "2026-12-26")
    assert level == "typical" and notice == "Air traffic disruptions may affect flights."
    a, b = flights
    assert a.price == 1807 and a.airlines == ["JetBlue", "Qatar Airways", "IndiGo"]
    assert a.depart == "2026-12-26T18:09" and a.arrive == "2026-12-28T02:50"
    assert a.duration_min == 22 * 60 + 11 and a.stops == 2
    assert a.layovers == ["JFK", "DOH"] and a.layover_min == [88, 540] and a.flags == []
    assert a.layover_names == ["John F. Kennedy International Airport, New York", "Hamad International Airport, Doha"]
    assert b.arrive == "2027-01-01T02:50" and b.flags == ["self-transfer"]


def test_parse_real_google_page():
    # slice of a live results page (BOS->BOM 2026-12-26, 1 adult) saved 2026-10-19
    page = (Path(__file__).parent / "fixtures/bos_bom_2026-12-26_1pax.html").read_text()
    flights, level, notice = gflights.parse(page, "2026-12-26")
    assert level == "typical" and notice == "Air traffic disruptions may affect flights."
    assert [(f.price, f.stops, f.layovers) for f in flights] == [
        (904, 2, ["JFK", "DOH"]), (1002, 1, ["MUC"]), (1132, 1, ["IST"])]
    assert flights[1].airlines == ["Lufthansa"] and flights[1].arrive == "2026-12-27T23:55"
    assert flights[1].layover_names == ["Munich International Airport, Munich"]


def test_nonstop_never_inherits_layovers_or_flags():
    page = ROW.format(p="700", rt="", stops="Nonstop", al="United", arr="Monday, December 28",
                      codes="1 stop in LHR", badge="<span>Self transfer</span>")
    (f,), _, _ = gflights.parse(page, "2026-12-26")
    assert f.stops == 0 and f.layovers == [] and f.flags == []


def test_exclusions_hit_any_leg():
    cfg = {"prefs": {"exclude_airlines": ["Air India", "Turkish Airlines"]}}
    assert tracker.excluded(F(1, ["Lufthansa", "Air India"]), cfg)
    assert tracker.excluded(F(1, ["Air India Express"]), cfg)
    assert not tracker.excluded(F(1, ["Emirates", "British Airways"]), cfg)


def test_book_links_prefill_route_dates_and_travellers():
    s = {"f": F(1, ["JetBlue", "Emirates"]), "pax": 2, "url": "https://g", "search": [("2026-12-28", "BOS", "BOM")]}
    html = ''.join(u for _, u in render.book_links(s))
    assert render.book_links(s)[0] == ("Book on JetBlue", "https://www.jetblue.com/")   # first carrier we know
    assert "leg1=from%3ABOS%2Cto%3ABOM%2Cdeparture%3A12%2F28%2F2026TANYT" in html and "adults%3A2" in html
    assert "BOS.AIRPORT-BOM.AIRPORT/?type=ONEWAY&adults=2" in html and "depart=2026-12-28" in html
    s["search"] = [("2026-12-18", "BOM", "BOS"), ("2026-12-28", "BOS", "BOM")]
    html = ''.join(u for _, u in render.book_links(s))
    assert "trip=roundtrip" in html and "leg2=" in html and "type=ROUNDTRIP" in html and "return=2026-12-28" in html


def test_prune_keeps_only_recent_runs():
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE quotes(run_at TEXT, kind TEXT)")
    con.executemany("INSERT INTO quotes VALUES(?, 'out')", [("r1",), ("r2",), ("r2",), ("r3",)])
    tracker.prune(con, keep=2)
    assert sorted(r for (r,) in con.execute("SELECT run_at FROM quotes")) == ["r2", "r2", "r3"]


def test_render_page_says_who_flies_and_escapes_scraped_text():
    cfg = {"cities": {"BOM": "Mumbai", "BOS": "Boston"},
           "outbound": {"from": "BOM", "to": "BOS", "depart_dates": ["2026-12-18"], "arrive_on": "2026-12-18", "adults": 1},
           "return": {"from": "BOS", "to": "BOM", "depart_dates": ["2026-12-28"], "adults": 2},
           "prefs": {"bags_per_person": 2, "max_stops": 2, "max_risk": "high", "max_layover_hours": 3}}
    q = {("out", "2026-12-18"): ([F(500, ["Qatar Airways"])], 1, "https://g/out"),
         ("ret", "2026-12-28"): ([F(1800, ["<script>x</script>"])], 2, "https://g/ret")}
    opts = tracker.options(q, cfg, BAGS, GEO, "high")
    jr = tracker.journeys(q, cfg, BAGS, GEO)
    cheapest = jr["totals"][0]                                  # 1 person out + 2 people back
    assert (cheapest["out"]["total"], cheapest["ret"]["total"], cheapest["total"]) == (500, 2100, 2600)
    page = render.page(cfg, GEO, ("2026-10-19T19:45:48+00:00", q, {}, set(), opts, [], jr), [], [])
    assert "All flights by journey" in page and "Price for 1 person" in page and "Price for 2 people" in page
    assert page.index("Whole trip") < page.index("All flights by journey")     # the answer comes first
    assert "<b>1 person</b> to Boston" in page and "<b>2 people</b> home to Mumbai" in page
    assert "Mon 19 Oct, 3:45 pm" in page                       # UTC run time shown in Boston time
    assert "<dd>$2,600</dd>" in page and "$1,050 each" in page   # 500 out + (1800 + 1 missing bag x $150 x 2)
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page
    assert "Book on Qatar Airways" in page and "flights.booking.com" in page
    assert '<meta name=robots content="noindex, nofollow, noarchive">' in page     # keep it out of search engines


def test_split_fare_saving():
    together = [{"f": F(2070, ["Lufthansa"]), "pax": 2}, {"f": F(2394, ["Virgin Atlantic"]), "pax": 2}]
    alone = [F(929, ["Lufthansa"]), F(1197, ["Virgin Atlantic"])]          # same flights, 1 traveller
    tracker.mark_split_fares(together, alone, 1)
    assert together[0]["split"] == {"alone": 929, "each": 1035, "saving": 106}   # 1 seat left at the low fare
    assert "split" not in together[1]                                          # 2394 / 2 == 1197: no gain


def test_lookup_whole_words_only():
    t = {"Air Canada": 1, "American Airlines": 2}
    assert tracker.lookup(t, "ANA") is None and tracker.lookup(t, "American") == 2


BAGS = {"default": {"lowest_fare_pieces": 1, "extra_bag_usd": 150},
        "airlines": {"Qatar Airways": {"lowest_fare_pieces": 2, "extra_bag_usd": 200},
                     "Lufthansa": {"lowest_fare_pieces": 1, "extra_bag_usd": 100}}}
GEO = {"hubs": {"DOH": {"level": "medium", "note": "Gulf airspace watch"}},
       "airlines": {"Air India": {"level": "high", "note": "Pakistan airspace"}},
       "transit_visa": {"LHR": {"indian_passport": "DATV unless US visa", "us_visa_exempts": True},
                        "FRA": {"indian_passport": "ATV needed", "us_visa_exempts": False}}}


def F(price, airlines, layovers=(), mins=(), arrive="2026-12-18T14:00", flags=()):
    return Flight(price, list(airlines), "2026-12-17T04:00", arrive, 1200, len(layovers),
                  list(layovers), list(mins), list(flags))


def test_bags_use_first_known_carrier():
    assert tracker.bag_cost(F(900, ["JetBlue", "Qatar Airways"]), 2, 2, BAGS) == (0, "Qatar Airways")
    assert tracker.bag_cost(F(900, ["Lufthansa"]), 2, 2, BAGS, legs=2) == (400, "Lufthansa")
    assert tracker.bag_cost(F(900, ["Nowhere Air"]), 1, 2, BAGS) == (150, "unknown airline")


def test_bag_fees_priced_by_bag_number():
    bags = {"default": {"lowest_fare_pieces": 1, "extra_bag_usd": 150},
            "airlines": {"Virgin Atlantic": {"lowest_fare_pieces": 0, "extra_bag_usd": [75, 100]},
                         "Lufthansa": {"lowest_fare_pieces": 1, "extra_bag_usd": [90, 90]},
                         "Emirates": {"lowest_fare_pieces": 2, "extra_bag_usd": [212, 212]}}}
    assert tracker.bag_cost(F(1, ["Virgin Atlantic"]), 1, 2, bags) == (175, "Virgin Atlantic")   # 1st $75 + 2nd $100
    assert tracker.bag_cost(F(1, ["Virgin Atlantic"]), 2, 2, bags, legs=2) == (700, "Virgin Atlantic")
    assert tracker.bag_cost(F(1, ["Lufthansa"]), 2, 2, bags) == (180, "Lufthansa")             # only the 2nd bag
    assert tracker.bag_cost(F(1, ["Emirates"]), 2, 2, bags) == (0, "Emirates")                  # both included


def test_risk():
    assert tracker.risk(F(1, ["Emirates"], ["LHR"], [120]), GEO) == ("low", [])
    lvl, notes = tracker.risk(F(1, ["Air India"], ["FRA"], [45]), GEO)
    assert lvl == "high" and any("FRA transit" in n for n in notes) and any("tight" in n for n in notes)
    assert tracker.risk(F(1, ["Etihad"], flags=["self-transfer"]), GEO)[0] == "high"
    assert tracker.risk(F(1, ["Qatar Airways"], ["DOH"], [120]), GEO)[0] == "medium"
    f = F(1, ["Emirates"], ["LHR"], [120]); f.stops = 2      # one hub unparsed -> fail closed
    assert tracker.risk(f, GEO)[0] == "medium"


def test_options_pick_cheapest_per_strategy_and_date():
    cfg = {"outbound": {"from": "BOM", "to": "BOS", "depart_dates": ["2026-12-17"], "arrive_on": "2026-12-18", "adults": 1},
           "return": {"from": "BOS", "to": "BOM", "depart_dates": ["2026-12-26"], "adults": 2},
           "prefs": {"bags_per_person": 2, "max_stops": 2, "max_risk": "high"}}
    q = {("out", "2026-12-17"): ([F(400, ["Qatar Airways"], arrive="2026-12-17T13:00"),    # lands a day early
                                   F(500, ["Qatar Airways"]), F(450, ["Lufthansa"])], 1, "u"),
         ("ret", "2026-12-26"): ([F(1800, ["Qatar Airways"])], 2, "u"),
         ("rt", "2026-12-17>2026-12-26"): ([F(1200, ["Qatar Airways"])], 1, "u"),
         ("ret_extra", "2026-12-26"): ([F(950, ["Qatar Airways"]), F(800, ["Lufthansa"])], 1, "u")}
    a, b = sorted(tracker.options(q, cfg, BAGS, GEO, "high"), key=lambda r: r["strategy"])
    assert a["total"] == 500 + 1800                 # Lufthansa 450 + 100 bag fee loses to Qatar 500
    assert a["per_person"] == [("Both ways", 500 + 900), ("Return only", 900)]   # sums back to the total
    # B: Qatar round trip 1200 + same-airline Qatar one-way 950 (preferred over cheaper Lufthansa 800+100)
    assert b["total"] == 1200 + 950 and "different airline" not in b["note"]
    assert b["per_person"] == [("Both ways", 1200), ("Return only", 950)]
    cfg["prefs"]["max_layover_hours"] = 1                      # every fixture flight has 0 layovers
    assert len(tracker.options(q, cfg, BAGS, GEO, "high")) == 2
    q[("ret_extra", "2026-12-26")] = ([F(800, ["Lufthansa"])], 1, "u")
    assert [r["strategy"] for r in tracker.options(q, cfg, BAGS, GEO, "high")] == ["A"]   # B can't fly together
    cfg["prefs"]["return_together"] = False
    assert "different airline" in tracker.options(q, cfg, BAGS, GEO, "high")[0]["note"]
    cfg["prefs"]["exclude_airlines"] = ["Qatar Airways"]
    assert tracker.options(q, cfg, BAGS, GEO, "high") == []     # every return option flies Qatar
    cfg["prefs"]["exclude_airlines"] = []
    low = tracker.options(q, cfg, BAGS, {"hubs": {}, "airlines": {"Qatar Airways": {"level": "high", "note": "x"}}}, "low")
    assert [r["total"] for r in low] == []          # every return option is Qatar -> filtered out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
