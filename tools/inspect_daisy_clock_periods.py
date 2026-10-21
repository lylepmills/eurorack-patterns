#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Describe every full clock period, retaining rare short/long populations.

Histograms are diagnostics, not an acceptance filter. Averages alone can hide
discrete phase advances. The caller must first validate the complete waveform
with inspect_clock; a separate clock cannot establish calibrated accuracy.
"""
from bisect import bisect_left
from collections import Counter
import math


def summarize(rises, ranges, nominal_hz=16000000/15, divider=15):
    if (not math.isfinite(nominal_hz) or nominal_hz <= 0 or
            type(divider) is not int or divider < 1):
        raise ValueError('Invalid clock configuration')
    nominal_ns = 1e9/nominal_hz
    half_source_period_ns = nominal_ns/divider/2
    blocks = []
    for begin, end in ranges:
        if not (math.isfinite(begin) and math.isfinite(end) and
                rises[1] <= begin < end <= rises[-1]):
            raise ValueError('Range lacks complete ungated clock coverage')
        # Only whole periods contained in the interval; report exact bounds
        # and counts so the small boundary exclusions are explicit.
        first = bisect_left(rises, begin)
        last = bisect_left(rises, end)
        if rises[last] > end: last -= 1
        if last <= first: raise ValueError('Insufficient full clock periods')
        hist = Counter()
        short, long = [], []
        smallest, largest = math.inf, -math.inf
        for i in range(first, last):
            ns = (rises[i+1]-rises[i])*1e9
            if not math.isfinite(ns) or ns <= 0:
                raise ValueError('Invalid clock period')
            hist[round(ns)] += 1
            smallest, largest = min(smallest, ns), max(largest, ns)
            if ns < nominal_ns-half_source_period_ns: short.append(ns)
            elif ns > nominal_ns+half_source_period_ns: long.append(ns)
        count = last-first
        duration_ns = (rises[last]-rises[first])*1e9
        ordinary = count-len(short)-len(long)
        blocks.append(dict(begin_s=rises[first], end_s=rises[last],
            periods=count, min_period_ns=smallest, max_period_ns=largest,
            mean_period_ns=duration_ns/count,
            short_periods=len(short), long_periods=len(long),
            short_mean_ns=math.fsum(short)/len(short) if short else None,
            long_mean_ns=math.fsum(long)/len(long) if long else None,
            ordinary_mean_ns=(duration_ns-math.fsum(short)-math.fsum(long))/ordinary if ordinary else None,
            short_deficit_us=math.fsum(nominal_ns-v for v in short)/1000,
            histogram_ns={str(k): v for k,v in sorted(hist.items())}))
    return dict(status='diagnostic only', nominal_period_ns=nominal_ns,
        population_boundary_ns=half_source_period_ns, blocks=blocks,
        limitation='Every contained full period counted; histogram rounded to 1 ns for display only. Short/long mean more than half a nominal source-clock period from nominal; no periods removed from timing acceptance and no physical cause assigned.')
