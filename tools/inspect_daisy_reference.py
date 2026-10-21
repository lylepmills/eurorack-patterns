#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Diagnostic relative-clock comparison with a partially occluded pulse source.

An open-drain generator and the fixture probe share a sense node. A generator
edge is visible only while the probe is high. Match the nonuniform timetable
uniquely, account for every hidden edge and check the entire wired-AND waveform.
This does not qualify DUT behavior or identify an absolutely calibrated clock.
"""
from bisect import bisect_left, bisect_right
import math


def fit(x, y):
    """One affine fit across all supplied observations; units are seconds."""
    if (len(x) != len(y) or len(x) < 3 or
            any(not math.isfinite(t) for t in (*x, *y)) or
            any(a >= b for a, b in zip(x, x[1:])) or
            any(a >= b for a, b in zip(y, y[1:]))):
        raise ValueError('Incomplete or unordered clock pairs')
    a, b = [v-x[0] for v in x], [v-y[0] for v in y]
    mx, my = math.fsum(a)/len(a), math.fsum(b)/len(b)
    slope = math.fsum((u-mx)*(v-my) for u, v in zip(a, b))/math.fsum((u-mx)**2 for u in a)
    offset = y[0]+my-slope*(x[0]+mx)
    residual = max(abs(v-(slope*u+my-slope*mx)) for u, v in zip(a, b))*1e6
    interval = max(abs((b[i]-b[i-1])-slope*(a[i]-a[i-1])) for i in range(1, len(a)))*1e6
    failures = []
    if abs(slope-1) >= .001: failures.append('clock_scale')
    if residual >= 5: failures.append('global_fit')
    if interval >= 5: failures.append('interval')
    return dict(status='fail' if failures else 'pass', failures=failures,
                pairs=len(x), scale=slope, offset_s=offset,
                clock_scale_ppm=(slope-1)*1e6,
                max_residual_us=residual, max_interval_error_us=interval)


def nearest(edges, t):
    i = bisect_left(edges, t)
    return min((j for j in (i-1, i) if 0 <= j < len(edges)),
               key=lambda j: abs(edges[j]-t))


def timeline(channel):
    e = list(channel['edges_s'])
    if (type(channel['initial_high']) is not bool or not e or
            any(not math.isfinite(t) for t in e) or
            any(a >= b for a, b in zip(e, e[1:]))):
        raise ValueError('Invalid digital timeline')
    return e


def inspect(generator, sense, probe, origin_bounds):
    """Return all observed/missing-edge accounting, never silently trim edges.

    The 1 ms bound identifies nonuniform schedule positions only. Final clock
    diagnostics retain the original 5 us residual/interval limits. Ambiguous
    mappings and hidden edges near a probe transition are rejected.
    """
    se, pe = timeline(sense), timeline(probe)
    if sense['initial_high'] or probe['initial_high'] or len(pe) % 2:
        raise ValueError('Require initially/finally low empty-jack probe')
    if not (len(origin_bounds) == 2 and all(math.isfinite(v) for v in origin_bounds)
            and origin_bounds[0] < origin_bounds[1]):
        raise ValueError('Invalid generator start bounds')
    x = [(e['before_us']+e['after_us'])/2e6 for e in generator['edges']]
    if len(x) < 6 or len(x) % 2 or any(a >= b for a, b in zip(x, x[1:])):
        raise ValueError('Incomplete generator schedule')
    candidates = [(t, bool((i+1) % 2)) for i, t in enumerate(se)
                  if abs(pe[nearest(pe, t)]-t) > 5e-6]
    if len(candidates) < 6:
        raise ValueError('Insufficient visible independent edges')
    y = [t for t, _ in candidates]
    mappings = set()
    for first in range(len(x)):
        if bool(first % 2) != candidates[0][1]: continue
        for last in range(first+1, len(x)):
            if bool(last % 2) != candidates[-1][1]: continue
            scale = (y[-1]-y[0])/(x[last]-x[first])
            offset = y[0]-scale*x[first]
            if abs(scale-1) >= .001 or not origin_bounds[0] <= offset <= origin_bounds[1]:
                continue
            pred = [offset+scale*t for t in x]
            ids = tuple(nearest(pred, t) for t in y)
            if (len(set(ids)) == len(ids) and
                    all(bool(i % 2) == level and abs(pred[i]-t) < .001
                        for i, (t, level) in zip(ids, candidates))):
                mappings.add(ids)
    if len(mappings) != 1:
        raise ValueError('Independent edge mapping is missing or ambiguous')
    ids, = mappings
    result = fit([x[i] for i in ids], y)
    predicted = [result['offset_s']+result['scale']*v for v in x]
    if not origin_bounds[0] <= result['offset_s'] <= origin_bounds[1]:
        raise ValueError('Fitted start outside recorded bounds')
    guard = (result['max_residual_us']+5)*1e-6
    hidden = []
    visible = dict(zip(ids, y))
    for i, t in enumerate(predicted):
        if i in visible: continue
        distance = abs(pe[nearest(pe, t)]-t)
        high = bool(bisect_right(pe, t) % 2)
        if t <= pe[0] or t >= pe[-1] or high or distance <= guard:
            raise ValueError('Hidden edge lacks unambiguous probe-low coverage')
        hidden.append(dict(seq=i, predicted_s=t, nearest_probe_edge_us=distance*1e6))
    # Visible edges retain their measured times; only hidden edges use the
    # global prediction, safely within a low probe interval. Every sense edge,
    # including ordinary probe edges, must then be explained.
    events = sorted([(t, 'probe', bool((i+1) % 2)) for i, t in enumerate(pe)] +
                    [(visible.get(i, t), 'generator', bool(i % 2))
                     for i, t in enumerate(predicted)])
    levels = dict(probe=False, generator=True)
    previous = False
    expected = []
    for t, role, value in events:
        levels[role] = value
        high = levels['probe'] and levels['generator']
        if high != previous:
            expected.append(t)
            previous = high
    if len(expected) != len(se):
        raise ValueError('Unexplained or missing sense transitions')
    waveform_error = max(abs(a-b)*1e6 for a, b in zip(expected, se))
    if waveform_error >= 5:
        raise ValueError('Sense waveform differs from complete wired-AND prediction')
    return dict(status='diagnostic only; no behavior qualification',
                generator_vs_scope=result, visible_edges=len(ids), hidden_edges=hidden,
                matched=[dict(seq=i, physical_s=t) for i, t in zip(ids, y)],
                complete_sense_edges=len(se), max_waveform_error_us=waveform_error,
                limitation='Relative clocks only. All hidden edges accounted for; no absolute accuracy or physical cause established.')
