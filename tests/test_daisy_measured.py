#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Replay recorded inputs and check expectations from the paired bench review."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture', ROOT / 'examples/daisy/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
REPLAY = Path(sys.argv[1])
DATA = ROOT / 'tests/measured/daisy/2026-10-14'

def check(condition, message):
    if not condition: raise AssertionError(message)

expected = {'tap-hold': (30000, 5, 1), 'pickup-up': (30000, 0, 0),
            'pickup-down': (30000, 0, 0), 'tracking-gap': (8000, 0, 0),
            'target-rearm': (8000, 0, 0), 'initial-held': (30000, 1, 0)}
for name, (count, taps, holds) in expected.items():
    metadata = json.loads((DATA / (name + '.json')).read_text())
    compressed = (DATA / (name + '.txt.gz')).read_bytes()
    raw = gzip.decompress(compressed)
    check(hashlib.sha256(compressed).hexdigest() == metadata['compressed_sha256'], name + ' compressed hash')
    check(hashlib.sha256(raw).hexdigest() == metadata['raw_sha256'], name + ' original hash')
    with tempfile.TemporaryDirectory() as td:
        out = Path(td); (out / 'raw.txt').write_bytes(raw)
        summary = capture.save_analysis(raw, out, metadata['firmware_build_id'], REPLAY)
    _, run, rows = capture.parse(raw)
    check(summary['samples'] == count and summary['taps'] == taps and summary['holds'] == holds, name + ' expected actions')
    check(all(run[k] == 0 for k in ('missed', 'adc_failures', 'rx_dropped', 'buffer_overflow')), name + ' unexpected faults')
    scope = metadata['scope']
    check(scope['service_pulses'] == count and scope['sampled_button_disagreements'] == 0, name + ' coverage')
    actions, windows = scope['action_edges_s'], scope['action_service_windows_s']
    check(len(actions) == len(windows) == taps + holds, name + ' physical action count')
    check(all(a <= t <= b for t, (a, b) in zip(actions, windows)), name + ' physical marker timing')
    if name == 'tap-hold':
        # Scope edge clusters correspond to five short presses and one ~2 s hold.
        # This only groups the recorded sub-ms bounce, not a universal bounce bound.
        clusters = []
        for t in scope['button_edges_s']:
            if not clusters or t - clusters[-1][-1] > 0.01: clusters.append([t])
            else: clusters[-1].append(t)
        check(scope['button_initial_high'] and len(clusters) == 12, 'six physical press/release pairs')
        for i in range(5):
            delay = actions[i] - clusters[2*i+1][-1]
            check(0.010 <= delay <= 0.012, 'observed tap release latency')
        check(0.600 <= actions[-1] - clusters[10][0] <= 0.625, 'observed hold latency')
        check(clusters[11][0] - clusters[10][0] > 2.0, 'observed long press')
    elif name.startswith('pickup-'):
        acquired = next(i for i, r in enumerate(rows) if r['state'] == 2)
        check(all(r['value_ppm'] == 250000 and not r['changed'] for r in rows[:acquired]), name + ' premature takeover')
        check(245000 <= rows[acquired]['value_ppm'] <= 255000, name + ' target neighborhood')
        check(all(r['state'] == 2 for r in rows[acquired:]), name + ' ownership retained')
        if name == 'pickup-down':
            check(all(r['value_ppm'] == 0 and not r['changed'] for r in rows[-5000:]), 'settled endpoint')
    elif name == 'tracking-gap':
        invalid = [r for r in rows if not r['adc_valid']]
        check(len(invalid) == 250, 'recorded deliberately invalid samples')
        check(all(r['value_ppm'] == 1000000 and not r['changed'] and r['accepted_ppm'] == -1 for r in invalid), 'invalid gap holds owned value')
        check(all(r['state'] == 2 for r in rows), 'tracking preserved')
    elif name == 'target-rearm':
        check(all(r['state'] == 2 for r in rows[:5000]), 'initial ownership')
        check(all(r['state'] == 1 and r['value_ppm'] == 750000 and not r['changed'] for r in rows[5000:]), 'external edit retained')
    else:
        edges = scope['button_edges_s']
        check(run['startup_held'] and not scope['button_initial_high'] and len(edges) == 3, 'initial hold then fresh tap')
        check(actions[0] > edges[-1] and 0.010 <= actions[0] - edges[-1] <= 0.012, 'only fresh tap acts')
    print('PASS:', name, count, 'measured samples replayed; physical expectations checked')
