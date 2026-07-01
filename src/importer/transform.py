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

# Tier system eras (see AGENTS.md "Estimating Approximate Number of Competitors").
# Pre-ERA1_START rules are not publicly available.
ERA1_START = datetime.date(2007, 1, 1)   # 2007 rules: 3-tier, T1=8/6/4/2/1, T3=12/10/8/6/4; couple-based
ERA2_START = datetime.date(2008, 11, 1)  # 2009 rules (updated Nov 2008): 3-tier, T1=5/4/3/2/1; couple-based
ERA3_START = datetime.date(2011, 1, 1)   # 2011 rules: same points as Era 2, now per-role (not couples)
ERA4_START = datetime.date(2018, 1, 3)   # 6-tier rules

# Era 4 (2018-01-03+): 6-tier, per-role.
# Points are unique per (result, tier), so every result "1"-"5" is unambiguous.
# "F" (additional finalist) earns 1-2 pts depending on tier — ambiguous, excluded.
_ERA4 = {
    ("1",  3): "Tier 1, 5 - 10 competitors",
    ("1",  6): "Tier 2, 11 - 19 competitors",
    ("1", 10): "Tier 3, 20 - 39 competitors",
    ("1", 15): "Tier 4, 40 - 79 competitors",
    ("1", 20): "Tier 5, 80 - 129 competitors",
    ("1", 25): "Tier 6, 130+ competitors",
    ("2",  2): "Tier 1, 5 - 10 competitors",
    ("2",  4): "Tier 2, 11 - 19 competitors",
    ("2",  8): "Tier 3, 20 - 39 competitors",
    ("2", 12): "Tier 4, 40 - 79 competitors",
    ("2", 16): "Tier 5, 80 - 129 competitors",
    ("2", 22): "Tier 6, 130+ competitors",
    ("3",  1): "Tier 1, 5 - 10 competitors",
    ("3",  3): "Tier 2, 11 - 19 competitors",
    ("3",  6): "Tier 3, 20 - 39 competitors",
    ("3", 10): "Tier 4, 40 - 79 competitors",
    ("3", 14): "Tier 5, 80 - 129 competitors",
    ("3", 18): "Tier 6, 130+ competitors",
    ("4",  0): "Tier 1, 5 - 10 competitors",
    ("4",  2): "Tier 2, 11 - 19 competitors",
    ("4",  4): "Tier 3, 20 - 39 competitors",
    ("4",  8): "Tier 4, 40 - 79 competitors",
    ("4", 12): "Tier 5, 80 - 129 competitors",
    ("4", 15): "Tier 6, 130+ competitors",
    ("5",  0): "Tier 1, 5 - 10 competitors",
    ("5",  1): "Tier 2, 11 - 19 competitors",
    ("5",  2): "Tier 3, 20 - 39 competitors",
    ("5",  6): "Tier 4, 40 - 79 competitors",
    ("5", 10): "Tier 5, 80 - 129 competitors",
    ("5", 12): "Tier 6, 130+ competitors",
}

# Era 2 + Era 3 (2008-11-01 to 2018-01-02): 3-tier, same point values for both.
# Era 2 used couple-based counting (min of leaders/followers); Era 3 switched to
# per-role counting. The tier boundaries and point values are identical.
_ERA2_3 = {
    ("1",  5): "Tier 1, 5 - 15 competitors",
    ("1", 10): "Tier 2, 16 - 39 competitors",
    ("1", 15): "Tier 3, 40+ competitors",
    ("2",  4): "Tier 1, 5 - 15 competitors",
    ("2",  8): "Tier 2, 16 - 39 competitors",
    ("2", 12): "Tier 3, 40+ competitors",
    ("3",  3): "Tier 1, 5 - 15 competitors",
    ("3",  6): "Tier 2, 16 - 39 competitors",
    ("3", 10): "Tier 3, 40+ competitors",
    ("4",  2): "Tier 1, 5 - 15 competitors",
    ("4",  4): "Tier 2, 16 - 39 competitors",
    ("4",  8): "Tier 3, 40+ competitors",
    ("5",  1): "Tier 1, 5 - 15 competitors",
    ("5",  2): "Tier 2, 16 - 39 competitors",
    ("5",  6): "Tier 3, 40+ competitors",
}

# Era 1 (2007-01-01 to 2008-10-31): 3-tier, couple-based, DIFFERENT point values.
# T1: 8/6/4/2/1  T2: 10/8/6/4/2  T3: 12/10/8/6/4
# T2 values are identical to later eras but T1 and T3 are unique to this period.
_ERA1 = {
    ("1",  8): "Tier 1, 5 - 15 couples",
    ("1", 10): "Tier 2, 16 - 39 couples",
    ("1", 12): "Tier 3, 40+ couples",
    ("2",  6): "Tier 1, 5 - 15 couples",
    ("2",  8): "Tier 2, 16 - 39 couples",
    ("2", 10): "Tier 3, 40+ couples",
    ("3",  4): "Tier 1, 5 - 15 couples",
    ("3",  6): "Tier 2, 16 - 39 couples",
    ("3",  8): "Tier 3, 40+ couples",
    ("4",  2): "Tier 1, 5 - 15 couples",
    ("4",  4): "Tier 2, 16 - 39 couples",
    ("4",  6): "Tier 3, 40+ couples",
    ("5",  1): "Tier 1, 5 - 15 couples",
    ("5",  2): "Tier 2, 16 - 39 couples",
    ("5",  4): "Tier 3, 40+ couples",
}


def _tier_for_placement(result: str, points: int, date: datetime.date) -> str | None:
    """Infer the competition tier from placement result, points, and date.

    Returns None for "F" (finalist) results — those 1-2 pt values are ambiguous
    across tiers — and for pre-2007 data where the rules are not available.
    """
    if result not in ("1", "2", "3", "4", "5"):
        return None
    if date >= ERA4_START:
        return _ERA4.get((result, points))
    if date >= ERA2_START:   # Era 2 and Era 3 share the same lookup table
        return _ERA2_3.get((result, points))
    if date >= ERA1_START:
        return _ERA1.get((result, points))
    return None  # pre-2007: rules not available


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
    # (event_id, date, division_id, role_id, tier) — one entry per unique key
    tiers: list = field(default_factory=list)
    # internal: tracks which (event_id, date, div_id, role_id) keys are in tiers
    _tier_keys: set = field(default_factory=set)


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

            tier = _tier_for_placement(result, points, date)
            if tier is not None:
                tier_key = (event_id, date, division_id, role_id)
                if tier_key not in data._tier_keys:
                    data._tier_keys.add(tier_key)
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
