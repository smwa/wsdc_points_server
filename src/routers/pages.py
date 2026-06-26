import re
import uuid
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from .. import charts, divisions
from ..session import current_user_id
from ..templates import templates

router = APIRouter(tags=["pages"])


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
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "dancers_count": dancers_count,
            "events_count": events_count,
            "last_updated": last_updated,
            "current_year": datetime.now().year,
            "favorites": favorites,
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
                   dv.name AS division, r.name AS role,
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

    # Cumulative total points over time (all roles/divisions), by month.
    monthly_points: dict = {}
    for p in placements:
        month = date(p["date"].year, p["date"].month, 1)
        monthly_points[month] = monthly_points.get(month, 0) + p["points"]
    chart = None
    if monthly_points:
        months = sorted(monthly_points)
        first, last = months[0], months[-1]
        series = []
        cumulative = 0
        year, month = first.year, first.month
        while (year, month) <= (last.year, last.month):
            cumulative += monthly_points.get(date(year, month, 1), 0)
            series.append((date(year, month, 1), cumulative))
            month += 1
            if month > 12:
                month, year = 1, year + 1
        chart = charts.line_chart(series)

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

    # Competitors-per-occurrence over time (chronological, true date spacing).
    # Skipped for events held only once — a single point isn't a useful chart.
    occ_asc = sorted(occurrences, key=lambda o: o["date"])
    chart = None
    if len(occ_asc) > 1:
        chart = charts.line_chart(
            [(o["date"], competitors.get(o["id"], 0)) for o in occ_asc]
        )

    return templates.TemplateResponse(
        request,
        "event.html",
        {
            "event": info,
            "tiered_occurrences": tiered_occurrences,
            "untiered_dates": untiered_dates,
            "chart": chart,
            "chart_label": "Competitors per occurrence over time",
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
