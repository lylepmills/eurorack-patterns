#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Compare sampled clock voltages with separately recorded digital receivers.

Offline diagnostics only. No edge is deleted to make a receiver pass, and no
clock is treated as a calibrated reference. A short triggered window cannot
qualify the full run or identify the oscillator as the physical cause.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np

from inspect_daisy_timing import read_digital


def require(condition, message):
    if not condition:
        raise ValueError(message)


def analog(path):
    path = Path(path)
    with path.open('rb') as stream:
        header = stream.read(64)
    require(len(header) == 64 and struct.unpack_from('<8siiQ', header) ==
            (b'<SALEAE>', 1, 1, 1), 'unexpected analog format')
    begin, trigger, rate, downsample, count = struct.unpack_from('<dddqQ', header, 24)
    require(all(math.isfinite(v) for v in (begin, trigger, rate)) and rate > 0
            and downsample == 1 and count >= 3 and path.stat().st_size == 64 + count*4,
            'invalid or downsampled analog record')
    v = np.memmap(path, dtype='<f4', mode='r', offset=64, shape=(count,))
    require(np.isfinite(v).all(), 'nonfinite analog samples')
    return v, dict(begin_s=begin, end_s=begin+(count-1)/rate,
                   trigger_s=trigger, sample_rate_hz=rate, samples=count)


def crossings(v, rate, begin, threshold, rising=True):
    """Every directed threshold crossing, with linear interpolation only."""
    require(math.isfinite(rate) and rate > 0 and math.isfinite(begin)
            and math.isfinite(threshold), 'invalid crossing parameters')
    above = np.asarray(v) >= threshold
    indices = np.flatnonzero((~above[:-1] & above[1:]) if rising
                             else (above[:-1] & ~above[1:]))
    a, b = np.asarray(v[indices], dtype=float), np.asarray(v[indices+1], dtype=float)
    return begin + (indices + (threshold-a)/(b-a))/rate


def periods(rises, nominal_hz=16000000/15):
    rises = np.asarray(rises, dtype=float)
    require(math.isfinite(nominal_hz) and nominal_hz > 0 and len(rises) >= 3
            and np.isfinite(rises).all() and np.all(np.diff(rises) > 0),
            'insufficient or unordered rising edges')
    ns = np.diff(rises)*1e9
    nominal = 1e9/nominal_hz
    boundary = nominal/30  # Half a source-clock period for the /15 output.
    bins, counts = np.unique(np.rint(ns).astype(np.int64), return_counts=True)
    return dict(edges=len(rises), periods=len(ns), minimum_ns=float(ns.min()),
                maximum_ns=float(ns.max()), mean_ns=float(ns.mean()),
                nominal_ns=nominal, population_boundary_ns=boundary,
                short_periods=int(np.sum(ns < nominal-boundary)),
                long_periods=int(np.sum(ns > nominal+boundary)),
                histogram_ns={str(k): int(n) for k,n in zip(bins,counts)})


def match_edges(left, right, tolerance_ns=100):
    """Mutual nearest matches; keep unmatched/ambiguous edges in the report."""
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    require(math.isfinite(tolerance_ns) and tolerance_ns > 0 and
            np.isfinite(left).all() and np.isfinite(right).all() and
            np.all(np.diff(left)>0) and np.all(np.diff(right)>0), 'invalid edge match')
    if not len(left) or not len(right):
        return dict(matched=0, unmatched_left=len(left), unmatched_right=len(right))
    def nearest(a, b):
        j = np.searchsorted(b, a)
        lo, hi = np.maximum(j-1, 0), np.minimum(j, len(b)-1)
        return np.where(abs(a-b[lo]) <= abs(a-b[hi]), lo, hi)
    j = nearest(left, right)
    back = nearest(right, left)
    keep = (back[j] == np.arange(len(left))) & (abs(right[j]-left)*1e9 <= tolerance_ns)
    delta = (right[j[keep]]-left[keep])*1e9
    result = dict(matched=int(keep.sum()), unmatched_left=int((~keep).sum()),
                  unmatched_right=int(len(right)-keep.sum()), tolerance_ns=tolerance_ns)
    if len(delta):
        result.update(median_right_minus_left_ns=float(np.median(delta)),
                      minimum_ns=float(delta.min()), maximum_ns=float(delta.max()),
                      peak_to_peak_ns=float(np.ptp(delta)))
    return result


def transition_times(v, rate, begin, low, high):
    """Adjacent 10/90 crossings; ringing or incomplete transitions remain counted."""
    result = {}
    for rising, name in ((True, 'rise'), (False, 'fall')):
        a = crossings(v, rate, begin, low if rising else high, rising)
        b = crossings(v, rate, begin, high if rising else low, rising)
        j = np.searchsorted(b, a)
        keep = j < len(b)
        # A subsequent starting crossing before the ending crossing is ambiguous.
        indices = np.flatnonzero(keep)
        if len(indices):
            ends = b[j[indices]]
            next_start = np.r_[a[1:], np.inf][indices]
            valid = (ends < next_start) & (ends-a[indices] < 250e-9)
            indices = indices[valid]
        ns = (b[j[indices]]-a[indices])*1e9
        result[name] = dict(start_crossings=len(a), end_crossings=len(b),
                            paired=len(ns), unpaired_starts=len(a)-len(ns),
                            unpaired_ends=len(b)-len(np.unique(j[indices])))
        if len(ns):
            result[name].update(minimum_ns=float(ns.min()), median_ns=float(np.median(ns)),
                                maximum_ns=float(ns.max()))
    return result


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def inspect(path, digital_paths, *, nominal_hz=16000000/15):
    v, meta = analog(path)
    rate, begin, end = meta['sample_rate_hz'], meta['begin_s'], meta['end_s']
    require(rate >= 100_000_000, 'edge waveform requires at least 100 MS/s')
    low, high = map(float, np.quantile(v, [.1, .9]))
    require(high-low >= 1 and low < 1.2 < 2.0 < high, 'missing logic-level clock swing')
    thresholds = (1.2, 1.65, 2.0)
    analog_edges = {level:crossings(v, rate, begin, level) for level in thresholds}
    result = dict(schema=1, status='diagnostic only', analog=meta, analog_sha256=sha(path),
                  voltage=dict(minimum=float(v.min()), maximum=float(v.max()),
                               p10=low, p90=high),
                  transitions_10_90=transition_times(v, rate, begin, low+.1*(high-low),
                                                    low+.9*(high-low)),
                  thresholds={str(level):periods(edges, nominal_hz)
                              for level,edges in analog_edges.items()}, receivers={})
    for name, digital in digital_paths.items():
        data = Path(digital).read_bytes()
        initial, edges = read_digital(data)
        _, _, dbegin, dend, _ = struct.unpack_from('<IdddQ', data, 24)
        require(dbegin <= begin+1/rate and dend >= end-1/rate, 'receiver lacks analog coverage')
        rises = np.asarray(edges[1::2] if initial else edges[::2], dtype=float)
        # A fixed boundary margin prevents one receiver's propagation delay from
        # creating artificial unmatched endpoints. Counts outside stay explicit.
        margin = 200e-9
        a, b = begin+margin, end-margin
        dr = rises[(rises >= a) & (rises <= b)]
        receiver = dict(sha256=sha(digital), initial_high=initial, total_transitions=len(edges),
                        total_rises=len(rises), compared_rises=len(dr),
                        excluded_boundary_rises=len(rises)-len(dr),
                        comparison_begin_s=a, comparison_end_s=b,
                        full_analog_window_periods=periods(rises[(rises>=begin)&(rises<=end)],nominal_hz),
                        matches={})
        for level, ar in analog_edges.items():
            ac = ar[(ar>=a)&(ar<=b)]
            receiver['matches'][str(level)] = dict(
                excluded_boundary_rises=len(ar)-len(ac), **match_edges(ac,dr))
        result['receivers'][name] = receiver
    result['limitation'] = ('All crossings retained, no pulse filtering. Analog threshold timing uses '
        'linear interpolation between native samples; values below sampling/probe bandwidth are not '
        'resolved. Matches permit constant path delay but never remove unmatched edges from counts. '
        'This is a short window of the MCO output and measurement chain, not full-run qualification, '
        'absolute time calibration, or proof of an oscillator fault.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analog', type=Path, required=True)
    p.add_argument('--digital', type=Path, required=True)
    p.add_argument('--derived', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = inspect(a.analog, dict(raw=a.digital, derived=a.derived))
    with a.out.open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')


if __name__ == '__main__': main()
