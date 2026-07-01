import json
import re
import uuid
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse

from .. import charts, divisions
from ..session import current_user_id
from ..templates import templates

router = APIRouter(tags=["pages"])

_TIER_RANGE_RE = re.compile(r'(\d+)\s*-\s*(\d+)')
_TIER_OPEN_RE  = re.compile(r'(\d+)\+')


def _tier_midpoint(tier: str) -> int:
    """Return the midpoint of a tier's competitor-count range.

    For bounded ranges ("5 - 10 competitors") returns the integer midpoint.
    For open-ended ranges ("130+ competitors") returns the lower bound.
    """
    m = _TIER_RANGE_RE.search(tier)
    if m:
        return (int(m.group(1)) + int(m.group(2))) // 2
    m = _TIER_OPEN_RE.search(tier)
    if m:
        return int(m.group(1))
    return 0


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user_id: uuid.UUID = Depends(current_user_id)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        dancers_count = await conn.fetchval("SELECT COUNT(*) FROM dancers")
        events_count = await conn.fetchval("SELECT COUNT(*) FROM events")
        last_updated = await conn.fetchval("SELECT MAX(completed_at) FROM data_refreshes")
        favorites = await conn.fetch(
            """
            SELECT d.id,
                   d.first_name || ' ' || d.last_name AS name,
                   MAX(eo.date) AS last_placed
            FROM favorite_dancers fd
            JOIN dancers d ON d.id = fd.dancer_id
            LEFT JOIN placements p ON p.dancer_id = d.id
            LEFT JOIN event_occurrences eo ON eo.id = p.event_occurrence_id
            WHERE fd.user_id = $1
            GROUP BY d.id, name
            ORDER BY last_placed DESC NULLS LAST, name
            """,
            user_id,
        )
        feed_token = await conn.fetchval(
            "SELECT feed_token FROM users WHERE id = $1", user_id
        )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "dancers_count": dancers_count,
            "events_count": events_count,
            "last_updated": last_updated,
            "current_year": datetime.now().year,
            "favorites": favorites,
            "feed_token": feed_token,
            "is_app": request.state.is_app,
        },
    )


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {})


@router.get("/dancers", response_class=HTMLResponse)
async def dancers(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id,
                   first_name || ' ' || last_name AS name
            FROM dancers
            ORDER BY id DESC
            """
        )
    # The whole list is sent to the page (as [id, name] pairs) and rendered
    # client-side in chunks; see static/js/dancers-list.js.
    dancers_data = [[r["id"], r["name"]] for r in rows]
    return templates.TemplateResponse(
        request, "dancers.html", {"dancers_data": dancers_data}
    )


@router.get("/dancer/{dancer_id}", response_class=HTMLResponse)
async def dancer(
    dancer_id: int,
    request: Request,
    user_id: uuid.UUID = Depends(current_user_id),
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        info = await conn.fetchrow(
            """
            SELECT d.id, d.first_name, d.last_name, d.is_pro,
                   d.primary_role_id, r.name AS primary_role
            FROM dancers d
            LEFT JOIN roles r ON r.id = d.primary_role_id
            WHERE d.id = $1
            """,
            dancer_id,
        )
        if info is None:
            raise HTTPException(status_code=404, detail="Dancer not found")

        role_points = await conn.fetch(
            """
            SELECT role_id, division_id, SUM(points) AS pts
            FROM placements
            WHERE dancer_id = $1
            GROUP BY role_id, division_id
            """,
            dancer_id,
        )

        points = await conn.fetch(
            """
            SELECT dv.name AS division, r.name AS role,
                   SUM(p.points) AS total_points
            FROM placements p
            JOIN divisions dv ON dv.id = p.division_id
            JOIN roles r ON r.id = p.role_id
            WHERE p.dancer_id = $1
            GROUP BY dv.id, dv.name, r.name
            ORDER BY dv.id, r.name
            """,
            dancer_id,
        )
        placements = await conn.fetch(
            """
            SELECT eo.date,
                   e.id AS event_id, e.name AS event_name,
                   dv.id AS division_id, dv.name AS division, r.name AS role,
                   p.result, p.points
            FROM placements p
            JOIN event_occurrences eo ON eo.id = p.event_occurrence_id
            JOIN events e ON e.id = eo.event_id
            JOIN divisions dv ON dv.id = p.division_id
            JOIN roles r ON r.id = p.role_id
            WHERE p.dancer_id = $1
            ORDER BY eo.date DESC
            """,
            dancer_id,
        )
        is_favorite = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM favorite_dancers "
            "WHERE user_id = $1 AND dancer_id = $2)",
            user_id,
            dancer_id,
        )

    # Pivot points into one row per division with leader/follower columns
    # (insertion order follows the query's ORDER BY dv.id = ladder order).
    points_by_division: dict = OrderedDict()
    for row in points:
        points_by_division.setdefault(row["division"], {})[row["role"]] = row["total_points"]
    point_rows = [
        {"division": name, "leader": roles.get("Leader"), "follower": roles.get("Follower")}
        for name, roles in points_by_division.items()
    ]

    # "Can compete" eligibility per role (ported logic in src/divisions.py).
    points_by_role: dict = {}
    for row in role_points:
        points_by_role.setdefault(row["role_id"], {})[row["division_id"]] = row["pts"]
    eligibility = divisions.can_compete_by_role(points_by_role, info["primary_role_id"])
    can_compete = [
        {"role": "Leader", "divisions": eligibility.get(1, [])},
        {"role": "Follower", "divisions": eligibility.get(2, [])},
    ]

    # Cumulative points over time, one line per role, sharing a month axis.
    monthly_by_role: dict = {"Leader": {}, "Follower": {}}
    for p in placements:
        month = date(p["date"].year, p["date"].month, 1)
        by_month = monthly_by_role.setdefault(p["role"], {})
        by_month[month] = by_month.get(month, 0) + p["points"]
    # Earliest month each role first scored in each laddered (skill-ladder)
    # division, to mark on the line with a labelled dot.
    first_ladder_month: dict = {}
    for p in placements:
        if p["division_id"] not in divisions.DIVISION_NAMES:
            continue
        month = date(p["date"].year, p["date"].month, 1)
        key = (p["role"], p["division_id"])
        if key not in first_ladder_month or month < first_ladder_month[key]:
            first_ladder_month[key] = month

    chart = None
    all_months = [m for by_month in monthly_by_role.values() for m in by_month]
    if all_months:
        first, last = min(all_months), max(all_months)
        # Start a month before the first points so every line rises from the
        # 0 baseline instead of beginning mid-air at its first value.
        start = date(first.year - 1, 12, 1) if first.month == 1 \
            else date(first.year, first.month - 1, 1)

        def cumulative_series(by_month: dict) -> list:
            if not by_month:
                return []
            series = []
            cumulative = 0
            year, month = start.year, start.month
            while (year, month) <= (last.year, last.month):
                cumulative += by_month.get(date(year, month, 1), 0)
                series.append((date(year, month, 1), cumulative))
                month += 1
                if month > 12:
                    month, year = 1, year + 1
            return series

        def ladder_markers(role: str, series: list) -> list:
            value_at = dict(series)
            markers = []
            for div_id in divisions.PROGRESSION:
                month = first_ladder_month.get((role, div_id))
                if month in value_at:
                    markers.append((month, value_at[month], divisions.DIVISION_NAMES[div_id]))
            return markers

        series_by_role = {r: cumulative_series(monthly_by_role[r]) for r in ("Leader", "Follower")}
        chart = charts.multi_line_chart(
            [(role, series_by_role[role], ladder_markers(role, series_by_role[role]))
             for role in ("Leader", "Follower")]
        )

    return templates.TemplateResponse(
        request,
        "dancer.html",
        {
            "dancer": info,
            "can_compete": can_compete,
            "point_rows": point_rows,
            "placements": placements,
            "is_favorite": is_favorite,
            "chart": chart,
            "chart_label": "Total points over time",
        },
    )


@router.get("/events", response_class=HTMLResponse)
async def events(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, location FROM events ORDER BY name"
        )
    return templates.TemplateResponse(request, "events.html", {"events": rows})


@router.get("/event/{event_id}", response_class=HTMLResponse)
async def event(event_id: int, request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        info = await conn.fetchrow(
            "SELECT id, name, location, url FROM events WHERE id = $1",
            event_id,
        )
        if info is None:
            raise HTTPException(status_code=404, detail="Event not found")

        occurrences = await conn.fetch(
            "SELECT id, date FROM event_occurrences "
            "WHERE event_id = $1 ORDER BY date DESC",
            event_id,
        )
        occ_ids = [o["id"] for o in occurrences]
        tier_rows = await conn.fetch(
            """
            SELECT eot.event_occurrence_id,
                   dv.name AS division, r.name AS role, eot.tier
            FROM event_occurrence_tiers eot
            JOIN divisions dv ON dv.id = eot.division_id
            JOIN roles r ON r.id = eot.role_id
            WHERE eot.event_occurrence_id = ANY($1::int[])
            ORDER BY dv.id, r.name
            """,
            occ_ids,
        )
        # Total competitor placements per occurrence (across all roles/divisions).
        count_rows = await conn.fetch(
            "SELECT event_occurrence_id, COUNT(*) AS n FROM placements "
            "WHERE event_occurrence_id = ANY($1::int[]) "
            "GROUP BY event_occurrence_id",
            occ_ids,
        )
    competitors = {r["event_occurrence_id"]: r["n"] for r in count_rows}

    # occurrence id -> {division name -> {role name -> tier}} (insertion order
    # follows the query's ORDER BY dv.id, so divisions come out in ladder order)
    by_occurrence: dict = defaultdict(OrderedDict)
    for row in tier_rows:
        by_occurrence[row["event_occurrence_id"]].setdefault(row["division"], {})[
            row["role"]
        ] = row["tier"]

    # Split occurrences: those with tier data get a pivoted table; the rest are
    # just listed by date. Both carry the occurrence id (for the competitors
    # link) and a total competitor count.
    tiered_occurrences = []
    untiered_dates = []
    for occ in occurrences:
        occ_divisions = by_occurrence.get(occ["id"])
        count = competitors.get(occ["id"], 0)
        if occ_divisions:
            rows = [
                {"division": name, "leader": roles.get("Leader"), "follower": roles.get("Follower")}
                for name, roles in occ_divisions.items()
            ]
            tiered_occurrences.append(
                {"id": occ["id"], "date": occ["date"], "rows": rows, "competitors": count}
            )
        else:
            untiered_dates.append(
                {"id": occ["id"], "date": occ["date"], "competitors": count}
            )

    # Sum tier midpoints per occurrence → estimated total competitors across all
    # divisions and roles. Each tier row covers one role of one division, so
    # summing them gives a reasonable estimate of total competitors at the event.
    # Era 1 (couple-based) tiers produce one row per role, both with the couple-
    # count range, so summing leaders + followers gives the total competitor count.
    estimated_by_occ: dict = {}
    for row in tier_rows:
        oid = row["event_occurrence_id"]
        estimated_by_occ[oid] = estimated_by_occ.get(oid, 0) + _tier_midpoint(row["tier"])

    # Chart: two series over time. "Competitors" uses tier-derived estimates where
    # available; "Pointed" counts everyone who placed in that occurrence (always
    # available). Skipped when the event has only one occurrence.
    occ_asc = sorted(occurrences, key=lambda o: o["date"])
    chart = None
    if len(occ_asc) > 1:
        est_series = [
            (o["date"], estimated_by_occ[o["id"]])
            for o in occ_asc
            if o["id"] in estimated_by_occ
        ]
        chart = charts.line_chart(est_series) if len(est_series) > 1 else None

    return templates.TemplateResponse(
        request,
        "event.html",
        {
            "event": info,
            "tiered_occurrences": tiered_occurrences,
            "untiered_dates": untiered_dates,
            "chart": chart,
            "chart_label": "Estimated total competitors per occurrence over time",
        },
    )


@router.get("/event-competitors/{occurrence_id}", response_class=HTMLResponse)
async def event_competitors(occurrence_id: int, request: Request):
    """Competitors at one event occurrence, grouped by division then role."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        occ = await conn.fetchrow(
            """
            SELECT eo.id, eo.date, e.id AS event_id, e.name AS event_name
            FROM event_occurrences eo
            JOIN events e ON e.id = eo.event_id
            WHERE eo.id = $1
            """,
            occurrence_id,
        )
        if occ is None:
            raise HTTPException(status_code=404, detail="Event occurrence not found")

        rows = await conn.fetch(
            """
            SELECT dv.id AS division_id, dv.name AS division, r.name AS role,
                   p.result, p.points,
                   d.id AS dancer_id,
                   d.first_name || ' ' || d.last_name AS dancer_name
            FROM placements p
            JOIN dancers d ON d.id = p.dancer_id
            JOIN divisions dv ON dv.id = p.division_id
            JOIN roles r ON r.id = p.role_id
            WHERE p.event_occurrence_id = $1
            ORDER BY dv.id, r.name,
                     CASE WHEN p.result ~ '^[0-9]+$' THEN p.result::int ELSE 99 END,
                     p.points DESC
            """,
            occurrence_id,
        )

    # Group by (division, role), preserving the query order (ladder, then role).
    groups: dict = OrderedDict()
    for row in rows:
        groups.setdefault((row["division"], row["role"]), []).append(row)
    sections = [
        {"division": div, "role": role, "competitors": members}
        for (div, role), members in groups.items()
    ]

    return templates.TemplateResponse(
        request,
        "event_competitors.html",
        {"occ": occ, "sections": sections, "total": len(rows)},
    )


@router.get("/dancers-over-time", response_class=HTMLResponse)
async def dancers_over_time(request: Request):
    """Line chart of the cumulative number of dancers with >= 1 point, by month."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT first_month, COUNT(*) AS n FROM (
                SELECT p.dancer_id, MIN(eo.date) AS first_month
                FROM placements p
                JOIN event_occurrences eo ON eo.id = p.event_occurrence_id
                WHERE p.points >= 1
                GROUP BY p.dancer_id
            ) firsts
            GROUP BY first_month
            """
        )

    start = date(2000, 1, 1)
    today = date.today()
    monthly: dict = {}
    baseline = 0  # dancers who reached a point before 2000
    for r in rows:
        fm = date(r["first_month"].year, r["first_month"].month, 1)
        if fm < start:
            baseline += r["n"]
        else:
            monthly[fm] = monthly.get(fm, 0) + r["n"]

    series = []
    cumulative = baseline
    year, month = start.year, start.month
    while (year, month) <= (today.year, today.month):
        cumulative += monthly.get(date(year, month, 1), 0)
        series.append((date(year, month, 1), cumulative))
        month += 1
        if month > 12:
            month, year = 1, year + 1

    return templates.TemplateResponse(
        request,
        "dancers_over_time.html",
        {
            "chart": charts.line_chart(series),
            "chart_label": "Dancers with at least one point per month, 2000 to now",
            "latest": series[-1][1] if series else 0,
        },
    )


async def _fetch_upcoming(conn):
    return await conn.fetch(
        """
        SELECT id, name, location, latitude, longitude, url,
               event_type, start_date, end_date
        FROM upcoming_events
        ORDER BY start_date
        """
    )


@router.get("/upcoming-events", response_class=HTMLResponse)
async def upcoming_events(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await _fetch_upcoming(conn)
    return templates.TemplateResponse(
        request,
        "upcoming_events.html",
        {
            "events": rows,
            "webcal_url": f"webcal://{request.url.netloc}/wsdc_events.ics",
        },
    )


def _ics_escape(text: str) -> str:
    """Escape a value for an iCalendar text field (RFC 5545)."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


@router.get("/wsdc_events.ics")
async def upcoming_events_ics(request: Request):
    """Serve the upcoming events as a subscribable iCalendar feed."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await _fetch_upcoming(conn)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WSDC Points//Events//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:WSDC Events - Mechstack",
    ]
    see_all = "https://wsdc.mechstack.dev/upcoming-events to see all events."
    for e in rows:
        if not e["start_date"]:
            continue
        summary = e["name"]
        if e["event_type"]:
            summary = f"{summary} ({e['event_type']})"
        slug = re.sub(r"[^a-z0-9]+", "-", (e["name"] or "").lower()).strip("-")
        end = e["end_date"] or e["start_date"]
        description = _ics_escape(e["url"] or "") + "\\n\\n" + _ics_escape(see_all)
        lines += [
            "BEGIN:VEVENT",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DTSTART;VALUE=DATE:{e['start_date'].strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
            f"LOCATION:{_ics_escape(e['location'])}",
            f"DESCRIPTION:{description}",
            f"UID:{e['start_date'].strftime('%Y%m%d')}-{slug}@wsdc.mechstack.dev",
            f"DTSTAMP:{stamp}",
            "ORGANIZER:mailto:wsdc@mechstack.dev",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar")


_RESULT_LABELS = {"1": "1st", "2": "2nd", "3": "3rd", "4": "4th", "5": "5th", "F": "Finalist"}


@router.get("/feed/{feed_token}.xml")
async def favorites_feed(feed_token: str, request: Request):
    """RSS feed of the newest placements of a user's favorited dancers.

    The opaque ``feed_token`` (a per-user UUID, see migration 007) identifies
    the user without a cookie, so an RSS reader can subscribe. Fetching the feed
    also bumps the user's last_seen so an active subscriber isn't pruned as
    stale even if they never open the site in a browser.
    """
    try:
        token = uuid.UUID(feed_token)
    except ValueError:
        raise HTTPException(status_code=404, detail="Feed not found")

    pool = request.app.state.pool
    async with pool.acquire() as conn:
        user_id = await conn.fetchval(
            "UPDATE users SET last_seen = now() WHERE feed_token = $1 RETURNING id",
            token,
        )
        if user_id is None:
            raise HTTPException(status_code=404, detail="Feed not found")

        items = await conn.fetch(
            """
            SELECT d.id AS dancer_id,
                   d.first_name || ' ' || d.last_name AS dancer_name,
                   e.name AS event_name, e.location,
                   eo.id AS occurrence_id, eo.date,
                   dv.id AS division_id, dv.name AS division,
                   r.id AS role_id, r.name AS role,
                   p.result, p.points
            FROM favorite_dancers fd
            JOIN dancers d ON d.id = fd.dancer_id
            JOIN placements p ON p.dancer_id = fd.dancer_id
            JOIN event_occurrences eo ON eo.id = p.event_occurrence_id
            JOIN events e ON e.id = eo.event_id
            JOIN divisions dv ON dv.id = p.division_id
            JOIN roles r ON r.id = p.role_id
            WHERE fd.user_id = $1
            ORDER BY eo.date DESC, p.id DESC
            LIMIT 50
            """,
            user_id,
        )

    base = str(request.base_url).rstrip("/")
    feed_url = f"{base}/feed/{token}.xml"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        "<title>WSDC Points — Your favorite dancers</title>",
        f"<link>{escape(base)}/</link>",
        f'<atom:link href="{escape(feed_url)}" rel="self" type="application/rss+xml"/>',
        "<description>Newest competition placements for the dancers you have starred.</description>",
    ]
    for it in items:
        place = _RESULT_LABELS.get(it["result"], it["result"])
        when = it["date"].strftime("%B %Y")
        where = it["location"] or it["event_name"]
        title = (
            f"{it['dancer_name']} — {place}, {it['division']} {it['role']} "
            f"at {it['event_name']}"
        )
        description = (
            f"{it['dancer_name']} placed {place} in {it['division']} {it['role']} "
            f"at {it['event_name']} ({where}) in {when}, earning {it['points']} "
            f"point{'s' if it['points'] != 1 else ''}."
        )
        # First-of-the-month dates; publish at midnight UTC for that month.
        pub = datetime(it["date"].year, it["date"].month, it["date"].day, tzinfo=timezone.utc)
        # Derive the guid from the placement's stable natural key, not its
        # surrogate id: the importer deletes and reinserts a dancer's placements
        # on every run, so p.id changes each import and a guid keyed on it would
        # make every item look new to RSS readers every time the importer runs.
        guid = (
            f"wsdc-placement-{it['dancer_id']}-{it['occurrence_id']}"
            f"-{it['division_id']}-{it['role_id']}"
        )
        lines += [
            "<item>",
            f"<title>{escape(title)}</title>",
            f"<link>{escape(base)}/dancer/{it['dancer_id']}</link>",
            f'<guid isPermaLink="false">{guid}</guid>',
            f"<pubDate>{format_datetime(pub)}</pubDate>",
            f"<description>{escape(description)}</description>",
            "</item>",
        ]
    lines += ["</channel>", "</rss>"]

    return Response("\n".join(lines) + "\n", media_type="application/rss+xml")


def _sql_quote(text: str) -> str:
    """Quote a string as a SQL literal (single quotes doubled)."""
    return "'" + (text or "").replace("'", "''") + "'"


@router.get("/geocode-fixups.sql")
async def geocode_fixups_sql(request: Request):
    """Download a SQL script with one UPDATE per un-geocoded location.

    The latitude/longitude are left blank on purpose: edit them in, then run the
    file (`psql "$DATABASE_URL" -f geocode_fixups.sql`) and re-run the importer
    so `upcoming_events` picks up the coordinates.
    """
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT location FROM geocode_cache "
            "WHERE latitude IS NULL OR longitude IS NULL "
            "ORDER BY location"
        )

    lines = [
        "-- Geocode fix-ups for locations that failed to geocode.",
        "-- Fill in latitude/longitude for each row below, then apply with:",
        '--   psql "$DATABASE_URL" -f geocode_fixups.sql',
        "-- Afterwards re-run the importer so upcoming_events picks up the coords.",
        "",
    ]
    if not rows:
        lines.append("-- No NULL geocode_cache rows. Nothing to fix.")
    for r in rows:
        lines.append(
            "UPDATE geocode_cache SET latitude = , longitude = , updated_at = now() "
            f"WHERE location = {_sql_quote(r['location'])};"
        )

    return Response(
        "\n".join(lines) + "\n",
        media_type="application/sql",
        headers={"Content-Disposition": 'attachment; filename="geocode_fixups.sql"'},
    )


@router.get("/robots.txt")
async def robots(request: Request):
    base = str(request.base_url).rstrip("/")
    body = f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
    return Response(body, media_type="text/plain")


@router.get("/sitemap.xml")
async def sitemap(request: Request):
    """Sitemap of the top-level pages plus every event and dancer."""
    base = str(request.base_url).rstrip("/")
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        event_ids = await conn.fetch("SELECT id FROM events ORDER BY id")
        dancer_ids = await conn.fetch("SELECT id FROM dancers ORDER BY id")

    locs = [base + p for p in (
        "/", "/about", "/dancers", "/events", "/upcoming-events", "/dancers-over-time"
    )]
    locs += [f"{base}/event/{r['id']}" for r in event_ids]
    locs += [f"{base}/dancer/{r['id']}" for r in dancer_ids]

    urls = "".join(f"<url><loc>{escape(u)}</loc></url>" for u in locs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>\n"
    )
    return Response(xml, media_type="application/xml")


# Self-destroying service worker. The legacy Jekyll site registered a SW at this
# same path (/service-worker.js, root scope) whose fetch handler re-issued every
# navigation as `fetch(request.url)` — dropping the method and body, so a form
# POST (e.g. starring a dancer) became a GET and hit our POST-only route as a
# 405. It lingers in installed-app (TWA) webviews. Serving a new SW here makes
# the webview pick it up on its next update check; on activate it unregisters
# itself, clears the old caches, and reloads open windows. After that no SW
# controls the page and POSTs work. This app otherwise uses no service worker.
_KILL_SERVICE_WORKER = """\
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try { await self.registration.unregister(); } catch (e) {}
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const client of clients) { client.navigate(client.url); }
  })());
});
"""


@router.get("/service-worker.js")
async def service_worker():
    return Response(
        _KILL_SERVICE_WORKER,
        media_type="text/javascript",
        headers={"Cache-Control": "no-cache"},
    )


# Digital Asset Links for the Android app. The TWA only runs chrome-less (no URL
# bar / share / close UI) when this verifies the app's package + signing-key
# fingerprint against the domain; without it the app falls back to a Custom Tab.
# Must be served at exactly /.well-known/assetlinks.json as application/json,
# 200, no redirect. Same content the legacy site served.
_ASSETLINKS_PATH = Path(__file__).resolve().parent.parent / "static" / "assetlinks.json"


@router.get("/.well-known/assetlinks.json")
async def assetlinks():
    return FileResponse(_ASSETLINKS_PATH, media_type="application/json")


# Tables kept out of the public data dump: the private ones (users, favorites)
# plus operational/derived tables that aren't part of the dataset people want.
_PRIVATE_TABLES = {
    "users",
    "favorite_dancers",
    "schema_migrations",
    "geocode_cache",
    "event_occurrence_tiers",
    "data_refreshes",
}


def _json_default(obj):
    """JSON-encode the Postgres types asyncpg hands back that json can't."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return str(obj)


@router.get("/data.json")
async def data_export(request: Request):
    """Stream every table's rows as JSON so the whole dataset can be downloaded.

    The response is a JSON object keyed by table name, each value the list of
    that table's rows. Private tables (users, favorites) are excluded. Rows are
    streamed straight from server-side cursors so even the large tables
    (placements) don't have to be buffered in memory.
    """
    pool = request.app.state.pool

    async def stream():
        async with pool.acquire() as conn:
            tables = await conn.fetch(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
            names = [t["table_name"] for t in tables if t["table_name"] not in _PRIVATE_TABLES]

            yield "{\n"
            for ti, name in enumerate(names):
                yield f'{"," if ti else ""}{json.dumps(name)}: [\n'
                # Server-side cursor: requires a transaction, streams in chunks.
                async with conn.transaction():
                    first = True
                    async for row in conn.cursor(f'SELECT * FROM "{name}"'):
                        prefix = "" if first else ",\n"
                        first = False
                        yield prefix + json.dumps(dict(row), default=_json_default)
                yield "\n]"
            yield "\n}\n"

    return StreamingResponse(stream(), media_type="application/json")
