"""Division-eligibility ("can compete") logic, ported from the legacy
``points/fetch.py`` (getCompetableDivisions / getSecondaryRoleCompetableDivisions).

Division ids are the seeded WSDC ids: only the skill ladder (Newcomer ->
Champions) participates. Given a dancer's total points per division for a role,
these functions return the division ids that role may compete in.
"""

NEWCOMER, NOVICE, INTERMEDIATE, ADVANCED, ALLSTARS, CHAMPIONS = 3, 4, 5, 6, 7, 8

PROGRESSION = [NEWCOMER, NOVICE, INTERMEDIATE, ADVANCED, ALLSTARS, CHAMPIONS]

DIVISION_NAMES = {
    NEWCOMER: "Newcomer",
    NOVICE: "Novice",
    INTERMEDIATE: "Intermediate",
    ADVANCED: "Advanced",
    ALLSTARS: "All-Stars",
    CHAMPIONS: "Champions",
}

# (can_compete_at, must_leave_at, min_pts_for_secondary) per division.
LIMITS = {
    CHAMPIONS: (1, 10, 10),
    ALLSTARS: (150, 225, 1),
    ADVANCED: (60, 90, 1),
    INTERMEDIATE: (30, 45, 1),
    NOVICE: (16, 30, 1),
    NEWCOMER: (0, 1, 1),
}


def competable_divisions(points_per_division: dict) -> list[int]:
    """Divisions a dancer's *primary* role may compete in."""
    p = points_per_division
    comp: list[int] = []

    if CHAMPIONS in p:
        comp.append(CHAMPIONS)
        if p[CHAMPIONS] < LIMITS[CHAMPIONS][1]:
            comp.append(ALLSTARS)
    elif ALLSTARS in p:
        if p[ALLSTARS] >= LIMITS[ALLSTARS][0]:
            comp.append(CHAMPIONS)
        if p[ALLSTARS] < LIMITS[ALLSTARS][1]:
            comp.append(ALLSTARS)
    elif ADVANCED in p:
        if p[ADVANCED] >= LIMITS[ADVANCED][0]:
            comp.append(ALLSTARS)
        if p[ADVANCED] < LIMITS[ADVANCED][1]:
            comp.append(ADVANCED)
    elif INTERMEDIATE in p:
        if p[INTERMEDIATE] >= LIMITS[INTERMEDIATE][0]:
            comp.append(ADVANCED)
        if p[INTERMEDIATE] < LIMITS[INTERMEDIATE][1]:
            comp.append(INTERMEDIATE)
    elif NOVICE in p:
        if p[NOVICE] >= LIMITS[NOVICE][0]:
            comp.append(INTERMEDIATE)
        if p[NOVICE] < LIMITS[NOVICE][1]:
            comp.append(NOVICE)
    elif NEWCOMER in p:
        comp.append(NOVICE)
    else:
        comp.append(NOVICE)
        comp.append(NEWCOMER)

    return comp


def secondary_competable_divisions(
    points_per_division: dict, primary_competable: list[int]
) -> list[int]:
    """Divisions a dancer's *secondary* role may compete in, given the primary
    role's eligibility (a dancer can dance down a level or two in their off
    role, bounded by points)."""
    points = {d: 0 for d in PROGRESSION}
    for division, pts in points_per_division.items():
        points[division] = points.get(division, 0) + pts

    comp: list[int] = []

    highest = primary_competable[0]
    for division in PROGRESSION:
        if division in primary_competable:
            highest = division

    idx = PROGRESSION.index(highest)
    two_down = PROGRESSION[idx - 2] if idx - 2 >= 0 else None
    one_down = PROGRESSION[idx - 1] if idx - 1 >= 0 else None
    zero_down = highest

    # zero down
    if (
        points[zero_down] >= LIMITS[zero_down][2]
        or one_down is None
        or points[one_down] >= LIMITS[one_down][1]
    ):
        comp.append(zero_down)

    # one down
    if points[zero_down] < LIMITS[zero_down][2]:
        if one_down is not None and points[one_down] < LIMITS[one_down][1]:
            comp.append(one_down)

    # two down
    if (
        one_down is not None
        and points[one_down] < LIMITS[one_down][2]
        and points[zero_down] < LIMITS[zero_down][2]
    ):
        if two_down is not None and points[two_down] < LIMITS[two_down][0]:
            comp.append(two_down)

    return comp


def can_compete_by_role(points_by_role: dict, primary_role_id: int | None) -> dict:
    """Map role_id (1 Leader, 2 Follower) -> ordered list of division names.

    ``points_by_role`` is ``{role_id: {division_id: total_points}}``. Mirrors
    fetch.py: the primary role uses the direct rule, the other role dances off
    the primary's eligibility.
    """
    primary = primary_role_id if primary_role_id in (1, 2, 3) else 1
    primary_competable = competable_divisions(points_by_role.get(primary, {}))

    result: dict = {}
    for role in (1, 2):
        if role == primary:
            ids = primary_competable
        else:
            ids = secondary_competable_divisions(
                points_by_role.get(role, {}), primary_competable
            )
        ordered = [d for d in PROGRESSION if d in ids]
        result[role] = [DIVISION_NAMES[d] for d in ordered]
    return result
