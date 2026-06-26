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
