"""Tiny server-rendered SVG line-chart helper.

`line_chart` takes a time series — a list of ``(date, value)`` points — and
returns the geometry the `_line_chart.html` partial draws: a polyline, a filled
area, and y/x tick marks. No JavaScript or chart library.

- x is positioned by **true date** (year + month fraction), so gaps in time
  show as gaps on the axis.
- the x-axis always labels the **first and last** points, plus nice year ticks
  in between.
- the y-axis uses several **nice round** ticks from 0 to the max, and also marks
  the series' **first value** when it's distinct from those.
"""

import math

WIDTH, HEIGHT = 860, 320
PAD_L, PAD_R, PAD_T, PAD_B = 56, 16, 16, 30


def _year_frac(d) -> float:
    return d.year + (d.month - 1) / 12.0


def _nice_step(span: float, target: int) -> int:
    """A 1/2/5 x 10^k step that splits ``span`` into roughly ``target`` parts."""
    if span <= 0:
        return 1
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5):
        if raw <= m * mag:
            return max(1, int(round(m * mag)))
    return max(1, int(round(10 * mag)))


def _empty():
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "pad_l": PAD_L,
        "points": "",
        "area": "",
        "yticks": [],
        "xticks": [],
    }


def line_chart(series) -> dict:
    """Build chart geometry from a list of ``(date, value)`` points."""
    series = list(series)
    n = len(series)
    if n == 0:
        return _empty()

    plot_w = WIDTH - PAD_L - PAD_R
    plot_h = HEIGHT - PAD_T - PAD_B

    xs = [_year_frac(d) for d, _ in series]
    ys = [v for _, v in series]
    minx, maxx = min(xs), max(xs)
    spanx = (maxx - minx) or 1
    maxv = max(ys) or 1

    def xf(x: float) -> float:
        return PAD_L + plot_w * ((x - minx) / spanx)

    def yf(v: float) -> float:
        return PAD_T + plot_h * (1 - v / maxv)

    points = " ".join(f"{xf(x):.1f},{yf(y):.1f}" for x, y in zip(xs, ys))
    area = (
        f"{xf(minx):.1f},{yf(0):.1f} {points} {xf(maxx):.1f},{yf(0):.1f}"
        if n > 1
        else ""
    )

    # --- y ticks: nice round 0..max, keep 0 and max, add the first value ------
    step = _nice_step(maxv, 7)
    nice = list(range(0, int(maxv) + 1, step))
    first_value = ys[0]
    keep_first = abs(yf(first_value) - yf(0)) > 12 and abs(yf(first_value) - yf(maxv)) > 12

    yvals = {0, int(maxv)}
    if keep_first:
        yvals.add(first_value)
    for t in nice:
        if not keep_first or abs(yf(t) - yf(first_value)) > 12:
            yvals.add(t)
    yticks = [{"y": f"{yf(v):.1f}", "label": f"{int(round(v)):,}"} for v in sorted(yvals)]

    # --- x ticks: nice years, always including the first and last point -------
    endpoints = [(minx, str(series[0][0].year)), (maxx, str(series[-1][0].year))]
    if minx == maxx:
        ordered = [endpoints[0]]
    else:
        end_labels = {label for _, label in endpoints}
        year_step = max(1, round((maxx - minx) / 8))
        years = range(math.ceil(minx), math.floor(maxx) + 1, year_step)
        middles = [
            (float(y), str(y))
            for y in years
            if str(y) not in end_labels
            and all(abs(xf(y) - xf(ex)) > 26 for ex, _ in endpoints)
        ]
        ordered = [endpoints[0]] + sorted(middles) + [endpoints[1]]
    xticks = [{"x": f"{xf(x):.1f}", "label": label} for x, label in ordered]

    return {
        "width": WIDTH,
        "height": HEIGHT,
        "pad_l": PAD_L,
        "points": points,
        "area": area,
        "yticks": yticks,
        "xticks": xticks,
    }


def multi_line_chart(named_series) -> dict:
    """Build chart geometry for several series that share one pair of axes.

    ``named_series`` is a list of ``(name, series, markers)`` triples, each
    ``series`` a list of ``(date, value)`` points and ``markers`` a list of
    ``(date, value, label)`` points to draw as labelled dots on the line.
    Series with no points are dropped. Axes are scaled to the combined extent so
    the lines line up; the result has a ``lines`` list (one polyline plus its
    ``dots`` per remaining series, in input order) instead of the single
    ``points``/``area`` that `line_chart` returns.
    """
    named_series = [(name, list(s), list(m)) for name, s, m in named_series if s]
    if not named_series:
        return {**_empty(), "lines": []}

    plot_w = WIDTH - PAD_L - PAD_R
    plot_h = HEIGHT - PAD_T - PAD_B

    all_dates = [d for _, s, _ in named_series for d, _ in s]
    all_xs = [_year_frac(d) for d in all_dates]
    all_ys = [v for _, s, _ in named_series for _, v in s]
    minx, maxx = min(all_xs), max(all_xs)
    spanx = (maxx - minx) or 1
    maxv = max(all_ys) or 1
    # Scale y to a round multiple of the tick step so every gridline — including
    # the top one — is evenly spaced (the data peak sits just under the top).
    step = _nice_step(maxv, 7)
    axis_max = math.ceil(maxv / step) * step

    def xf(x: float) -> float:
        return PAD_L + plot_w * ((x - minx) / spanx)

    def yf(v: float) -> float:
        return PAD_T + plot_h * (1 - v / axis_max)

    lines = [
        {
            "name": name,
            "points": " ".join(
                f"{xf(_year_frac(d)):.1f},{yf(v):.1f}" for d, v in s
            ),
            "dots": [
                {
                    "cx": f"{xf(_year_frac(d)):.1f}",
                    "cy": f"{yf(v):.1f}",
                    "label": label,
                }
                for d, v, label in markers
            ],
        }
        for name, s, markers in named_series
    ]

    # --- y ticks: uniform 0..axis_max in equal steps -------------------------
    yticks = [
        {"y": f"{yf(v):.1f}", "label": f"{v:,}"}
        for v in range(0, axis_max + 1, step)
    ]

    # --- x ticks: whole years at a fixed step, so gaps are evenly spaced ------
    if minx == maxx:
        ordered = [(minx, min(all_dates).year)]
    else:
        year_step = max(1, round((maxx - minx) / 8))
        years = list(range(math.ceil(minx), math.floor(maxx) + 1, year_step))
        if years:
            ordered = [(float(y), y) for y in years]
        else:  # span under a year: no whole year falls inside, label the ends
            first_year, last_year = min(all_dates).year, max(all_dates).year
            if first_year == last_year:
                ordered = [((minx + maxx) / 2, first_year)]
            else:
                ordered = [(minx, first_year), (maxx, last_year)]
    xticks = [{"x": f"{xf(x):.1f}", "label": str(label)} for x, label in ordered]

    return {
        "width": WIDTH,
        "height": HEIGHT,
        "pad_l": PAD_L,
        "lines": lines,
        "yticks": yticks,
        "xticks": xticks,
    }
