#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Decode retained native MSO evidence; never connect to an instrument."""
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'examples/daisy'))
import jack_capture
from capture import require
from inspect_daisy_timing import read_digital
from review_daisy_jacks import review_timing


def extract(folder, *, output=None):
    require((folder / 'collection-complete.json').is_file(), 'incomplete collection')
    raw = (folder / 'fixture/raw.txt').read_bytes()
    channels = {}
    protocol = jack_capture.identity(raw.splitlines()[0])['protocol']
    for name, port, i in jack_capture.digital_layout(protocol):
        data = (folder / f'scope/digital_{port+1}_{i}.bin').read_bytes()
        initial, edges = read_digital(data)
        _, _, begin, end, _ = struct.unpack_from('<IdddQ', data, 24)
        channels[name] = dict(initial_high=initial, edges_s=list(edges), begin_s=begin, end_s=end)
    timing = review_timing(raw, channels)
    rises, falls = timing['rises'], timing['falls']
    data = (folder / 'scope/analog_0.bin').read_bytes()
    require(len(data) >= 64 and struct.unpack_from('<8siiQ', data) == (b'<SALEAE>', 1, 1, 1),
            'unexpected analog format')
    begin, trigger, rate, downsample, count = struct.unpack_from('<dddqQ', data, 24)
    require(all(math.isfinite(x) for x in (begin, trigger, rate)) and rate > 0
            and downsample == 1 and len(data) == 64 + count * 4, 'invalid analog record')
    v = np.frombuffer(data, dtype='<f4', offset=64)
    require(np.isfinite(v).all(), 'nonfinite analog sample')
    a = np.floor((np.asarray(rises) - begin) * rate).astype(np.int64)
    b = np.ceil((np.asarray(falls) - begin) * rate).astype(np.int64)
    require(np.all(a >= 0) and np.all(b < len(v)) and np.all(a < b), 'missing analog tail/aperture')
    bounds = np.empty(2 * len(a), dtype=np.int64)
    bounds[::2], bounds[1::2] = a, b + 1
    require(np.all(np.diff(bounds) > 0) and bounds[-1] < len(v), 'overlapping/incomplete apertures')
    analog = dict(sample_rate_hz=rate, begin_s=begin, end_s=begin + count / rate,
        samples=int(count), first_indices=a.tolist(), last_indices=b.tolist(),
        minimum_volts=np.minimum.reduceat(v, bounds)[::2].tolist(),
        maximum_volts=np.maximum.reduceat(v, bounds)[::2].tolist(),
        representation='Native extrema over each service aperture, including boundary samples')
    if protocol >= 4:
        # Independent source-phase evidence, not a replacement for the full
        # ADC aperture above. A long IRQ may leave its end adjacent to the next
        # probe bit, making boundary-inclusive extrema legitimately ambiguous.
        mid = np.floor(((np.asarray(rises)+np.asarray(falls))/2-begin)*rate).astype(np.int64)
        require(np.all(mid-1 > a) and np.all(mid+1 < b), 'source plateau too short')
        points = np.stack([v[mid-1], v[mid], v[mid+1]])
        analog['source_plateaus'] = dict(center_indices=mid.tolist(),
            minimum_volts=points.min(axis=0).tolist(), maximum_volts=points.max(axis=0).tolist(),
            representation='Three native samples centered at or before each service midpoint; source timing only')
    output = folder if output is None else output
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('channels', channels), ('analog-apertures', analog)]:
        require(not (output / (name + '.json')).exists(), 'derived evidence already exists')
        jack_capture.publish_json(output / (name + '.json'), value)
    return raw, channels, analog
