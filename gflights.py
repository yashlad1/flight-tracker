"""Google Flights scraper, stdlib only.

Builds the protobuf `tfs` query Google Flights uses, fetches the server-rendered
results page and parses each result's aria-label. Prices are USD totals for all
passengers in the search.
"""
import base64
import html
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
# Google's "Reject all" consent cookie (value from Firefox's cookie-banner tests), so a runner on an EU-style IP
# gets results instead of the consent wall.
SOCS = "CAESHAgBEhJnd3NfMjAyNDAzMjUtMF9SQzEaAmVuIAEaBgiAw42wBg"


class Blocked(Exception):
    """Google answered with a block page instead of results."""


@dataclass
class Flight:
    price: int                      # USD, total for all passengers searched
    airlines: list[str]
    depart: str                     # local ISO datetime
    arrive: str
    duration_min: int
    stops: int
    layovers: list[str] = field(default_factory=list)       # IATA codes
    layover_min: list[int] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)          # e.g. "self-transfer"
    layover_names: list[str] = field(default_factory=list)  # "Zayed International Airport, Abu Dhabi"


# --- protobuf encoding of the tfs param (schema as reverse-engineered by fast-flights) ---
def _varint(n):
    out = b""
    while True:
        b, n = n & 0x7F, n >> 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _ld(fieldno, payload):          # length-delimited field
    return _varint(fieldno << 3 | 2) + _varint(len(payload)) + payload


def _vi(fieldno, n):                # varint field
    return _varint(fieldno << 3) + _varint(n)


def tfs(legs, adults):
    """legs: [(date 'YYYY-MM-DD', from IATA, to IATA), ...]; one leg = one-way, two = round trip."""
    msg = b""
    for d, src, dst in legs:
        msg += _ld(3, _ld(2, d.encode()) + _ld(13, _ld(2, src.encode())) + _ld(14, _ld(2, dst.encode())))
    msg += _ld(8, _varint(1) * adults)              # passengers: ADULT=1, packed
    msg += _vi(9, 1)                                # seat: ECONOMY
    msg += _vi(19, 2 if len(legs) == 1 else 1)      # trip: ONE_WAY=2, ROUND_TRIP=1
    return base64.urlsafe_b64encode(msg).decode().rstrip("=")


def search_url(legs, adults):
    q = {"tfs": tfs(legs, adults), "hl": "en", "gl": "us", "curr": "USD"}
    return "https://www.google.com/travel/flights?" + urllib.parse.urlencode(q)


# --- parsing ---
LABEL = re.compile(r'aria-label="(From [\d,]+ US dollars[^"]*)"')
DETAIL = re.compile(
    r"From (?P<price>[\d,]+) US dollars(?: round trip total)?\. "
    r"(?P<stops>Nonstop|\d+ stops?) flight with (?P<airlines>.+?)\. "
    r"Leaves .+? at (?P<dt>\d{1,2}:\d{2}\s?[AP]M) on \w+, (?P<dd>\w+ \d{1,2}) "
    r"and arrives at .+? at (?P<at>\d{1,2}:\d{2}\s?[AP]M) on \w+, (?P<ad>\w+ \d{1,2})\. "
    r"Total duration (?P<dur>[^.]+)\.")
LAYOVER = re.compile(r"Layover \(\d+ of \d+\) is a (.+?) layover at (.+?) in ([^.]+)\.")
STOP_CODES = re.compile(r"\d+ stops? in ([A-Z]{3}(?:, [A-Z]{3})*)")
PRICE_LEVEL = re.compile(r"Prices are currently \|?(low|typical|high)")
NOTICE = re.compile(r"Travel update\|([^|]{5,300})")        # Google's live disruption banner


def _minutes(s):
    h = re.search(r"(\d+) hr", s)
    m = re.search(r"(\d+) min", s)
    return (int(h[1]) if h else 0) * 60 + (int(m[1]) if m else 0)


def _when(day, clock, search_day):
    clock = re.sub(r"\s", " ", clock).replace("  ", " ")
    if " " not in clock:
        clock = clock[:-2] + " " + clock[-2:]
    dt = datetime.strptime(f"{day} {search_day.year} {clock}", "%B %d %Y %I:%M %p")
    if dt.month < search_day.month:                 # Dec search landing in Jan
        dt = dt.replace(year=dt.year + 1)
    return dt.isoformat(timespec="minutes")


def parse(page, search_day):
    """Return (flights, google_price_level, travel_notice) from a results page."""
    if isinstance(search_day, str):
        search_day = date.fromisoformat(search_day)
    hits = list(LABEL.finditer(page))
    flights, seen = [], set()
    for i, m in enumerate(hits):
        label = html.unescape(m[1])
        d = DETAIL.search(label)
        if not d or label in seen:
            continue
        seen.add(label)
        end = hits[i + 1].start() if i + 1 < len(hits) else m.end() + 16000
        row = re.sub(r"<[^>]+>", "|", page[m.end():end])
        stops = 0 if d["stops"] == "Nonstop" else int(d["stops"].split()[0])
        codes = STOP_CODES.search(row) if stops else None
        flags = [f for f, needle in (("self-transfer", "Self transfer"),
                                     ("separate tickets", "Separate tickets")) if stops and needle in row]
        flights.append(Flight(
            price=int(d["price"].replace(",", "")),
            airlines=[a.strip() for a in re.split(r", | and ", d["airlines"]) if a.strip()],
            depart=_when(d["dd"], d["dt"], search_day),
            arrive=_when(d["ad"], d["at"], search_day),
            duration_min=_minutes(d["dur"]),
            stops=stops,
            layovers=codes[1].split(", ") if codes else [],
            layover_min=[_minutes(dur) for dur, _, _ in LAYOVER.findall(label)],
            layover_names=[f"{airport}, {city}" for _, airport, city in LAYOVER.findall(label)],
            flags=flags,
        ))
    text = re.sub(r"\|+", "|", re.sub(r"<[^>]+>", "|", page))
    level, notice = PRICE_LEVEL.search(text), NOTICE.search(text)
    return flights, (level[1] if level else None), (html.unescape(notice[1]).strip() if notice else None)


def blocked(url, status, page):
    """Name the block page Google served instead of results, or None (e.g. an empty shell).

    Only call it on pages without results: normal pages mention reCAPTCHA in their scripts."""
    if "consent.google." in url or "Before you continue" in page:
        return "consent page (consent.google.com)"
    if status == 429 or "unusual traffic" in page:
        return '429 "unusual traffic" page (rate limit or flagged IP)'
    if "/sorry/" in url or "g-recaptcha" in page:
        return "CAPTCHA page"
    return None


def fetch(url, tries=3):
    """GET a results page. Google occasionally serves an empty shell, so retry; raise Blocked on a block page,
    where retrying would only dig the hole deeper."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                                               "Cookie": f"SOCS={SOCS}"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                page = r.read().decode("utf-8", "replace")
            if LABEL.search(page):
                return page
            if why := blocked(r.url, r.status, page):
                raise Blocked(why)
        except urllib.error.HTTPError as e:         # the 429 page arrives as an HTTP error; status + URL name it
            if why := blocked(e.url, e.code, ""):
                raise Blocked(why) from None
            if attempt == tries - 1:
                raise
        except OSError:
            if attempt == tries - 1:
                raise
        if attempt < tries - 1:
            time.sleep(4 + attempt * 6 + random.random() * 3)
    return ""


def search(legs, adults):
    url = search_url(legs, adults)
    return *parse(fetch(url), legs[0][0]), url
