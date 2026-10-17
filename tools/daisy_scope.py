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


def inspect_aggregate_service(buckets, transitions, initial_high=False):
    """Inspect every pulse against complete 1 kHz, one-second soak buckets.

    This validates aggregate counts and extrema, not individual sample replay.
    Fit clocks within each second so slow oscillator drift over a long soak is
    visible without treating it as service jitter. Missing/extra pulses fail.
    Failed or partial acquisition buckets require separate review and raise.
    Local timing disagreements are returned explicitly for diagnostic reporting;
    match_aggregate_service rejects any such disagreement.
    """
    edges = [float(t) for t in transitions]
    if (initial_high or not buckets or len(edges) != 2000 * len(buckets)
            or any(not math.isfinite(t) for t in edges)
            or any(a >= b for a, b in zip(edges, edges[1:]))):
        raise ValueError('Incomplete aggregate service edges')
    rises, falls = edges[::2], edges[1::2]
    scales, interval_errors, width_errors, mismatches = [], [], [], []
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
            mismatches.append(dict(second=i, interval_error_us=interval_error,
                                   work_width_error_us=width_error))
        scales.append((scale-1)*1e6)
        interval_errors.append(interval_error); width_errors.append(width_error)
        maximum_interval = max(maximum_interval, interval)
        maximum_width = max(maximum_width, width)
    return dict(samples=len(rises), seconds=len(buckets),
                clock_scale_ppm_min=min(scales), clock_scale_ppm_max=max(scales),
                max_interval_error_us=max(interval_errors), max_work_width_error_us=max(width_errors),
                max_service_interval_us=maximum_interval, max_service_width_us=maximum_width,
                mismatched_buckets=mismatches,
                representation='All physical service pulses; per-second counts and extrema checked, no individual sample replay')


def match_aggregate_service(buckets, transitions, initial_high=False):
    report = inspect_aggregate_service(buckets, transitions, initial_high)
    if report['mismatched_buckets']:
        first = report['mismatched_buckets'][0]
        raise ValueError('Aggregate interval/work maxima disagree with scope: '
                         f"{len(report['mismatched_buckets'])} bucket(s), first second {first['second']}, "
                         f"interval error {first['interval_error_us']:.3f} us, "
                         f"width error {first['work_width_error_us']:.3f} us")
    return report


def inspect_timing_service(buckets, transitions, timer_hz, initial_high=False):
    """Correlate selected raw-tick witnesses with the SAME physical pulses.

    The original aggregate acceptance is returned unchanged. CPU GPIO brackets
    aid diagnosis; they do not prove pad timing or authorize wider tolerances.
    Requires parse-validated diagnostic buckets and full nominal slot coverage.
    """
    aggregate = inspect_aggregate_service(buckets, transitions, initial_high)
    if timer_hz <= 0 or any('timing' not in b for b in buckets):
        raise ValueError('Missing validated timing diagnostics')
    edges = [float(t) for t in transitions]
    rise, fall = edges[::2], edges[1::2]
    tick_us = 1e6/timer_hz

    def extended(t, field):
        return t['begin_elapsed'] + ((t[field]-t['begin_tick']) & 0xffffffff)

    def outside(value, lo, hi):
        return max(lo-value, value-hi, 0.)

    details = []
    max_interval_error = max_width_error = 0.
    for b in buckets:
        d = b['timing']; ws = d['witnesses']
        if d['samples'] != 1000 or len(ws) != 10:
            raise ValueError('Incomplete timing witnesses')
        first, last = ws[0]['current'], ws[1]['current']
        begin, end = b['second']*1000, (b['second']+1)*1000
        if first['seq'] != begin or last['seq'] != end-1:
            raise ValueError('Timing sequence does not align with scope')
        scale = ((rise[end-1]-rise[begin])*1e6 /
                 ((extended(last,'rise_before')-extended(first,'rise_before'))*tick_us))
        if abs(scale-1) >= .001:
            raise ValueError('Raw diagnostic clock scale outside bound')
        interval_seq = max(range(max(1,begin),end), key=lambda j: rise[j]-rise[j-1])
        width_seq = max(range(begin,end), key=lambda j: fall[j]-rise[j])
        reviewed = []
        for w in ws:
            p, t = w['previous'], w['current']; seq = t['seq']
            width = (fall[seq]-rise[seq])*1e6/scale
            lo = (extended(t,'fall_before')-extended(t,'rise_after'))*tick_us
            hi = (extended(t,'fall_after')-extended(t,'rise_before'))*tick_us
            width_error = outside(width,lo,hi)
            interval = interval_error = None
            # First/last repeat the sample in the predecessor slot. Only peak
            # records retain the actual preceding observation.
            if seq and p['seq']+1 == seq:
                interval = (rise[seq]-rise[seq-1])*1e6/scale
                ilo = (extended(t,'rise_before')-extended(p,'rise_after'))*tick_us
                ihi = (extended(t,'rise_after')-extended(p,'rise_before'))*tick_us
                interval_error = outside(interval,ilo,ihi)
                max_interval_error = max(max_interval_error,interval_error)
            max_width_error = max(max_width_error,width_error)
            reviewed.append(dict(kind=w['kind'],seq=seq,previous_seq=p['seq'],
                scope_width_us=width,firmware_work_us=t['work_us'],
                cpu_width_bracket_us=[lo,hi],width_outside_cpu_bracket_us=width_error,
                scope_interval_us=interval,interval_outside_cpu_bracket_us=interval_error,
                begin_guard_us=(extended(t,'rise_after')-t['begin_elapsed'])*tick_us,
                end_guard_us=(extended(t,'fall_after')-t['end_elapsed'])*tick_us))
        retained = {w['current']['seq'] for w in ws}
        details.append(dict(second=b['second'],raw_clock_scale_ppm=(scale-1)*1e6,
            scope_max_interval_seq=interval_seq,scope_max_width_seq=width_seq,
            scope_interval_peak_retained=interval_seq in retained,
            scope_width_peak_retained=width_seq in retained,witnesses=reviewed,
            max_bookkeeping_us=d['max_bookkeeping_ticks']*tick_us,
            bookkeeping_seq=d['bookkeeping_seq']))
    return dict(aggregate=aggregate,
        original_acceptance='fail' if aggregate['mismatched_buckets'] else 'pass',
        max_witness_interval_outside_cpu_bracket_us=max_interval_error,
        max_witness_width_outside_cpu_bracket_us=max_width_error,buckets=details,
        limitation='Selected witnesses only. CPU brackets are diagnostic evidence, not physical-pad guarantees; original acceptance limits remain unchanged.')
