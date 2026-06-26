"""Fetch raw data from WSDC (or load it from the legacy raw files for testing).

In normal operation nothing is cached to disk: every dancer is fetched fresh
from the WSDC API and upserted immediately, and geocoded event locations live in
the ``geocode_cache`` table (see ``run.refresh_upcoming_events``).

For offline testing (``IMPORTER_OFFLINE=1``) the importer instead reads the
legacy cached files so it never touches WSDC:

- dancers: ``raw_responses.json.gz`` (gzip JSON dict keyed by ``str(wsdc_id)``)
- events:  ``raw_events.html.gz`` (gzip HTML of the events page)
"""

import datetime
import gzip
import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# --- Dancers ---------------------------------------------------------------

DANCER_API_URL = "https://points.worldsdc.com/lookup2020/find"


def fetch_dancer(wsdc_id: int):
    """Fetch one dancer's raw response from WSDC, or None if missing."""
    try:
        r = requests.post(DANCER_API_URL, data={"num": str(wsdc_id)}, timeout=30)
    except requests.RequestException as e:
        log.warning("Request error for dancer %s: %s", wsdc_id, e)
        return None
    if r.status_code != 200:
        log.warning("Bad status code %s for dancer %s", r.status_code, wsdc_id)
        return None
    data = r.json()
    return data or None


def load_raw_dancers(path: str) -> dict:
    """Load the legacy ``raw_responses.json.gz`` cache (offline mode)."""
    with open(path, "rb") as f:
        dancers = json.loads(gzip.decompress(f.read()).decode("utf-8"))
    log.info("Loaded %s raw dancers from %s", len(dancers), path)
    return dancers


# --- Upcoming events -------------------------------------------------------

EVENTS_PAGE_URL = "https://www.worldsdc.com/events/"

# WSDC sometimes ships events with missing/ambiguous location strings.
LOCATION_PATCHES = {
    "Swing Fling": "Washington, D.C., US",
    "Monterey Swing Fest": "Monterey, CA",
}


def geocode_location(location: str, api_key: str):
    """Geocode a location string via OpenWeatherMap.

    Returns ``(lat, lon)`` on success or ``None`` for a confirmed miss. Caching
    is the caller's job (the ``geocode_cache`` table); this is a pure network
    call. Blocking — call it via ``asyncio.to_thread``.
    """
    time.sleep(1.1)  # OpenWeatherMap free-tier rate limit
    splits = [s.strip() for s in location.split(",")]
    if len(splits) > 1 and len(splits[1]) == 2 and splits[1].isupper() and splits[1] != "UK":
        if len(splits) < 3:
            splits.append("US")
        else:
            splits[2] = "US"
    url = "http://api.openweathermap.org/geo/1.0/direct?q={}&limit=1&appid={}".format(
        ",".join(splits), api_key
    )
    try:
        r = requests.get(url, timeout=30)
    except requests.RequestException as e:
        log.warning("Geocoding request failed for '%s': %s", location, e)
        return None
    if not r.ok or len(r.json()) < 1:
        log.warning("No geocoding results for '%s'", location)
        return None
    result = r.json()[0]
    return (result["lat"], result["lon"])


def _parse_date_range(text):
    """Parse the events-page date cell into (start, end) datetimes."""
    year = re.findall(r"\d{4}", text)[0]
    month = re.findall(r"[a-zA-Z]{3}", text)[0]
    day = re.findall(r"\d{1,2}", text)[0]
    start = datetime.datetime(int(year), datetime.datetime.strptime(month, "%b").month, int(day))

    year = re.findall(r"\d{4}", text)[-1]
    month = re.findall(r"[a-zA-Z]{3}", text)[-1]
    day = re.findall(r"\s(\d{1,2})[,\s]", text)[-1]
    end = datetime.datetime(int(year), datetime.datetime.strptime(month, "%b").month, int(day))
    return start, end


def parse_events_html(html: str) -> list[dict]:
    """Parse the events-page HTML into event dicts (no lat/lon yet).

    Geocoding is done separately (see ``run.refresh_upcoming_events``); each dict
    here has a patched ``location`` string so callers only deal with the result.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        log.warning("No events table found in events page")
        return []

    events = []
    for row in table.find_all("tr")[1:]:
        tds = row.find_all("td")
        if len(tds) < 3:
            continue
        date_text = tds[0].get_text()
        location = tds[2].get_text()
        name = tds[1].find("div", class_="event_name").get_text().strip()
        url = tds[1].find("a")["href"]
        event_type = tds[1].find("div", class_="event_type").get_text()

        if (location == "" or location is None) and name in LOCATION_PATCHES:
            location = LOCATION_PATCHES[name]

        try:
            start_date, end_date = _parse_date_range(date_text)
        except (IndexError, ValueError):
            log.warning("Could not parse event date '%s' for %s", date_text, name)
            continue

        events.append(
            {
                "name": name,
                "location": location,
                "url": url,
                "event_type": event_type,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    log.info("Parsed %s upcoming events", len(events))
    return events


def fetch_events_page() -> list[dict]:
    """Scrape the WSDC events page. Best-effort; returns [] on failure."""
    try:
        resp = requests.get(EVENTS_PAGE_URL, timeout=30)
    except requests.RequestException as e:
        log.warning("Could not fetch events page: %s", e)
        return []
    if resp.status_code != 200:
        log.warning("Events page returned %s", resp.status_code)
        return []
    return parse_events_html(resp.text)


def load_events_page(path: str) -> list[dict]:
    """Load and parse the legacy ``raw_events.html.gz`` cache (offline mode)."""
    with open(path, "rb") as f:
        html = gzip.decompress(f.read()).decode("utf-8")
    return parse_events_html(html)
