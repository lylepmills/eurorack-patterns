# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Match recorded service edges to a complete firmware window, without hardware."""
import math


def match_service(rows, transitions, initial_high=False, startup=False):
    if len(rows) < 2:
        raise ValueError('Incomplete application window')
    edges = [float(t) for t in transitions]
    if initial_high or len(edges) % 2 or not all(math.isfinite(t) for t in edges):
        raise ValueError('Incomplete service edges')
    if any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError('Unordered service edges')
    rises, falls = edges[::2], edges[1::2]
    prefix = []
    extra = len(rises) - len(rows)
    if extra:
        # Observed startup instrumentation: one long high level before the
        # application configures its marker. Preserve it explicitly. Unknown
        # prefixes, short extra pulses and missing application pulses fail.
        if not (startup and extra == 1 and falls[0] - rises[0] > .010
                and rises[1] - falls[0] > .010):
            raise ValueError('Service count mismatch or unsupported startup prefix')
        prefix = [[rises[0], falls[0]]]
        rises, falls = rises[1:], falls[1:]
    if len(rises) != len(rows):
        raise ValueError('Incomplete application window')
    x = [float(r['time_us'] - rows[0]['time_us']) for r in rows]
    y = [(t - rises[0]) * 1e6 for t in rises]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    variance = sum((t - mx) ** 2 for t in x)
    if not variance or any(a >= b for a, b in zip(x, x[1:])):
        raise ValueError('Invalid firmware timeline')
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / variance
    intercept = my - slope * mx
    residual = max(abs(b - (slope * a + intercept)) for a, b in zip(x, y))
    interval_error = max(abs((y[i] - y[i-1]) - slope * (x[i] - x[i-1]))
                         for i in range(1, len(x)))
    width_error = max(abs((b - a) * 1e6 - r['work_us'])
                      for a, b, r in zip(rises, falls, rows))
    if abs(slope - 1) >= .001 or residual >= 5 or interval_error >= 5 or width_error >= 3:
        raise ValueError('Application edges do not match firmware timestamps/work widths')
    return rises, falls, dict(
        clock_scale_ppm=(slope - 1) * 1e6,
        max_fit_residual_us=residual, max_interval_error_us=interval_error,
        max_work_width_error_us=width_error,
        pre_application_high_intervals_s=[[a-rises[0], b-rises[0]] for a, b in prefix])


def match_aggregate_service(buckets, transitions, initial_high=False):
    """Check every pulse against complete 1 kHz, one-second soak buckets.

    This validates aggregate counts and extrema, not individual sample replay.
    Fit clocks within each second so slow oscillator drift over a long soak is
    visible without treating it as service jitter. Missing/extra pulses fail.
    Failed or partial buckets require separate review and are not accepted here.
    """
    edges = [float(t) for t in transitions]
    if (initial_high or not buckets or len(edges) != 2000 * len(buckets)
            or any(not math.isfinite(t) for t in edges)
            or any(a >= b for a, b in zip(edges, edges[1:]))):
        raise ValueError('Incomplete aggregate service edges')
    rises, falls = edges[::2], edges[1::2]
    scales, interval_errors, width_errors = [], [], []
    maximum_interval = maximum_width = 0.
    for i, b in enumerate(buckets):
        if (b['second'] != i or b['samples'] != 1000 or b['missed']
                or b['adc_failures'] or b['cadence_breaks']
                or not i*1000000 <= b['first_us'] < b['last_us'] < (i+1)*1000000):
            raise ValueError('Incomplete or failed aggregate bucket')
        begin, end = i*1000, (i+1)*1000
        scale = (rises[end-1]-rises[begin])*1e6 / (b['last_us']-b['first_us'])
        if abs(scale-1) >= .001:
            raise ValueError('Aggregate clock scale outside bound')
        interval = max((rises[j]-rises[j-1])*1e6 for j in range(max(1, begin), end))
        width = max((falls[j]-rises[j])*1e6 for j in range(begin, end))
        interval_error = abs(interval/scale-b['max_interval_us'])
        width_error = abs(width/scale-b['max_work_us'])
        if interval_error >= 5 or width_error >= 3:
            raise ValueError('Aggregate interval/work maxima disagree with scope')
        scales.append((scale-1)*1e6)
        interval_errors.append(interval_error); width_errors.append(width_error)
        maximum_interval = max(maximum_interval, interval)
        maximum_width = max(maximum_width, width)
    return dict(samples=len(rises), seconds=len(buckets),
                clock_scale_ppm_min=min(scales), clock_scale_ppm_max=max(scales),
                max_interval_error_us=max(interval_errors), max_work_width_error_us=max(width_errors),
                max_service_interval_us=maximum_interval, max_service_width_us=maximum_width,
                representation='All physical service pulses; per-second counts and extrema checked, no individual sample replay')
