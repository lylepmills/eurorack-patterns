#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Electrical clamp evidence: independent voltage, timing and detector checks.

The open-drain generator shares the sense node with the probe waveform. Its
edges cannot be individually measured whenever the probe is already low.
Report bounded transition intervals, never invented exact mechanical timings.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'examples/daisy'))
from capture import require
import pulse_generator
from review_daisy_jacks import review_motion, review_fault_motion, review_timing


def review(raw, channels, analog, generator_raw, generator_build, times):
    source = pulse_generator.parse(generator_raw, generator_build, times)
    require(len(times) == 2, 'one complete electrical clamp required')
    timing = review_timing(raw, channels)
    rows, run = timing['rows'], timing['run']
    result = (review_fault_motion if run['fault'] else review_motion)(raw, channels, analog, cycles=1)
    # Probe-high apertures independently distinguish normal-following from
    # clamped-low. Keep ambiguous voltage samples out of the timing brackets.
    observed = []
    for i, r in enumerate(rows):
        if not r['probe']: continue
        low = analog['maximum_volts'][i] <= .85
        high = analog['minimum_volts'][i] >= 2.4
        if low or high: observed.append((i, low))
    groups = []
    for i, low in observed:
        if not groups or groups[-1][0] != low: groups.append((low, []))
        groups[-1][1].append(i)
    require([g[0] for g in groups] == [False, True, False], 'unexpected electrical clamp sequence')
    before, during, after = (g[1] for g in groups)
    rises, falls = timing['rises'], timing['falls']
    onset = [falls[before[-1]], rises[during[0]]]
    release = [falls[during[-1]], rises[after[0]]]
    require(all(0 <= b-a < .01 for a,b in (onset, release)), 'unbounded electrical transition')
    duration_bounds = [release[0] - onset[1], release[1] - onset[0]]
    edges = source['edges']
    generator_bounds = [(edges[1]['before_us'] - edges[0]['after_us']) / 1e6,
                        (edges[1]['after_us'] - edges[0]['before_us']) / 1e6]
    # Allow 1000 ppm relative oscillator difference, as in the original source
    # checker, without fitting away extra transitions or shortening a dwell.
    require(duration_bounds[0] <= generator_bounds[1] * 1.001 + 5e-6 and
            duration_bounds[1] >= generator_bounds[0] * .999 - 5e-6,
            'generator/physical clamp duration disagreement')
    result.update(case='automated electrical clamp', generator=source,
        clamp_onset_bounds_s=onset, clamp_release_bounds_s=release,
        physical_clamp_duration_bounds_s=duration_bounds,
        limitation='Open-drain electrical substitution on one passive fixture; no mechanical insertion, contact bounce, powered-module input, audio-load or exact generator-edge jitter qualification. Transitions hidden by low probe voltage are bounded by independent high-probe voltage apertures. Relative clocks are not calibrated absolute time.')
    return result
