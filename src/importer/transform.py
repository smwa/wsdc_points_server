"""Flatten one raw WSDC dancer response into relational rows.

Ports the per-dancer core of ``points/fetch.py``: turns a single nested dancer
API response (West Coast Swing only) into that dancer's row plus the events,
event occurrences, placements and first-place tiers they appear in. The importer
then upserts each dancer independently. Division/role names map to
``divisions.id`` / ``roles.id`` via the seeded reference data (passed in as
resolvers) — the legacy ``DIVISIONS_MAP`` integers are *not* reused.
"""

import datetime
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

LIMIT_TO_DANCE_STYLE = "West Coast Swing"
# Tier info only applies to results under the post-2020 points rules.
RULE_CHANGE_DATE = datetime.date(2020, 1, 1)


@dataclass
class DancerData:
    dancer_id: int
    # (first_name, last_name, is_pro, primary_role_id)
    dancer: tuple
    # event_id -> {"name", "location", "url", "_date"} (info from newest occurrence)
    events: dict = field(default_factory=dict)
    # set of (event_id, date)
    occurrences: set = field(default_factory=set)
    # (event_id, date, role_id, division_id, result, points)
    placements: list = field(default_factory=list)
    # (event_id, date, division_id, role_id, tier) for this dancer's wins
    tiers: list = field(default_factory=list)


def _tier_for_points(points: int):
    """Map first-place points to a human-readable competition tier."""
    return {
        3: "Tier 1, 5 - 10 competitors",
        6: "Tier 2, 11 - 19 competitors",
        10: "Tier 3, 20 - 39 competitors",
        15: "Tier 4, 40 - 79 competitors",
        20: "Tier 5, 80 - 129 competitors",
        25: "Tier 6, 130+ competitors",
    }.get(points)


def _parse_event_date(raw: str) -> datetime.date:
    """Parse the API's 'Month YYYY' into a first-of-month date."""
    try:
        return datetime.datetime.strptime(raw, "%B %Y").date()
    except (ValueError, TypeError):
        return datetime.date(1970, 1, 1)


def _record_event(data: DancerData, event_obj: dict, date: datetime.date):
    """Track an event + occurrence, keeping the info from its newest date."""
    eid = event_obj["id"]
    existing = data.events.get(eid)
    if existing is None or date > existing["_date"]:
        data.events[eid] = {
            "name": event_obj.get("name"),
            "location": event_obj.get("location"),
            "url": event_obj.get("url"),
            "_date": date,
        }
    data.occurrences.add((eid, date))


def _flatten_role(data: DancerData, placements, resolve_division):
    """Append placements for one role's nested 'West Coast Swing' tree."""
    if not isinstance(placements, dict):
        return
    style = placements.get(LIMIT_TO_DANCE_STYLE)
    if not style:
        return
    for division in style.values():
        division_id = resolve_division(division["division"])
        if division_id is None:
            log.warning("Unmapped division: %s", division["division"])
            continue
        for competition in division["competitions"]:
            date = _parse_event_date(competition["event"].get("date"))
            points = competition["points"] or 0
            role_id = 1 if competition["role"] == "leader" else 2
            result = competition["result"]
            event_id = competition["event"]["id"]

            _record_event(data, competition["event"], date)
            data.placements.append(
                (event_id, date, role_id, division_id, result, points)
            )

            if result == "1" and date >= RULE_CHANGE_DATE:
                tier = _tier_for_points(points)
                if tier is not None:
                    data.tiers.append((event_id, date, division_id, role_id, tier))


def transform_dancer(datum: dict, resolve_division, resolve_role) -> DancerData | None:
    """Flatten one raw dancer response, or None if they have no WCS placements.

    ``resolve_division(div_obj)`` -> division id or None.
    ``resolve_role(name)`` -> role id or None.
    """
    dancer_id = datum["dancer_wsdcid"]
    data = DancerData(
        dancer_id=dancer_id,
        dancer=(
            datum["dancer_first"],
            datum["dancer_last"],
            datum.get("is_pro") == 1,
            resolve_role(datum.get("short_dominate_role")),
        ),
    )
    _flatten_role(data, datum["leader"]["placements"], resolve_division)
    _flatten_role(data, datum["follower"]["placements"], resolve_division)

    if not data.placements:
        return None  # no WCS placements -> skip, like the legacy pipeline
    return data
