#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Recorded fault/startup inputs, checked against physical bench expectations."""
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
DATA = ROOT / 'tests/measured/daisy/2026-10-16'
REPLAY = Path(sys.argv[1])


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def voltage_points(scope, key='analog'):
    a = scope[key]
    return [(a['first_center_s'] + i*a['period_s'], v)
            for i, v in enumerate(a['median_volts'])]


expected = {'press-stall': (29974, 26, 1), 'hold-stall': (29974, 26, 1),
            'release-stall': (29975, 25, 1), 'press-adc-gap': (30000, 0, 2),
            'pickup-gap-up': (150000, 0, 0), 'pickup-gap-down': (150000, 0, 0),
            'moving-target': (150000, 0, 0), 'reset-released': (20000, 0, 0),
            'power-held': (20000, 0, 1)}

for name, (count, missed, taps) in expected.items():
    meta = json.loads((DATA / (name + '.json')).read_text())
    compressed = (DATA / (name + '.txt.gz')).read_bytes()
    raw = gzip.decompress(compressed)
    check(hashlib.sha256(compressed).hexdigest() == meta['compressed_sha256'], name + ' compressed hash')
    check(hashlib.sha256(raw).hexdigest() == meta['raw_sha256'], name + ' wire hash')
    with tempfile.TemporaryDirectory() as td:
        out = Path(td); (out / 'raw.txt').write_bytes(raw)
        summary = capture.save_analysis(raw, out, meta['firmware_build_id'], REPLAY)
    _, run, rows = capture.parse(raw)
    check(summary['samples'] == count and summary['taps'] == taps and summary['holds'] == 0, name + ' actions')
    check(run['missed'] == missed and all(run[k] == 0 for k in ('adc_failures', 'rx_dropped', 'buffer_overflow')), name + ' faults')
    scope = meta['scope']
    check(scope['service_pulses'] == count and scope['sampled_button_disagreements'] == 0, name + ' scope coverage')
    align = scope['alignment']
    check(align['max_fit_residual_us'] < 5 and align['max_work_width_error_us'] < 3, name + ' physical service timing')
    actions, windows, edges = scope['action_edges_s'], scope['action_service_windows_s'], scope['button_edges_s']
    check(len(actions) == len(windows) == taps, name + ' action markers')
    check(all(a <= t <= b for t, (a, b) in zip(actions, windows)), name + ' action timing')
    event_rows = [i for i, r in enumerate(rows) if r['gesture']]
    if name.endswith('-stall'):
        gaps = scope['service_gaps']
        check(len(gaps) == 1 and 25000 < gaps[0]['interval_us'] < 28000, name + ' physical gap')
        gap = gaps[0]; g = gap['after_seq']
        check(len(edges) == 4 and scope['button_initial_high'], name + ' two physical presses')
        check(all(r['value_ppm'] == 250000 for r in rows[:event_rows[0]]), name + ' cancelled gesture changed target')
        check(all(r['value_ppm'] == 750000 for r in rows[event_rows[0]:]), name + ' fresh tap target')
        check(.010 < actions[0]-edges[-1] < .012, name + ' fresh tap latency')
        check([i for i, r in enumerate(rows) if not r['cadence_valid']] == [g+1], name + ' one cadence break')
        if name == 'release-stall':
            check(edges[1] < gap['start_s'] < gap['end_s'] < edges[2], 'release inside interruption')
            released = next(r for r in rows[g+1:] if not r['debounced'])
            check(released['time_us']//1000 - rows[g+1]['time_us']//1000 == 10, 'fresh release qualification after gap')
        else:
            check(edges[0] < gap['start_s'] < gap['end_s'] < edges[1], name + ' held during gap')
            if name == 'hold-stall':
                pressed = next(r['time_us'] for r in rows if r['debounced'])
                threshold = (pressed//1000+600)*1000
                check(run['stimulus']['begin_us'] < threshold < run['stimulus']['end_us'], 'hold deadline inside interruption')
    elif name == 'press-adc-gap':
        invalid = [i for i, r in enumerate(rows) if not r['adc_valid']]
        check(len(invalid) == 250 and invalid == list(range(invalid[0], invalid[-1]+1)), 'ADC-only gap extent')
        check(all(rows[i]['injected'] and rows[i]['accepted_ppm'] == -1 and not rows[i]['changed'] for i in invalid), 'invalid values applied')
        check(all(r['cadence_valid'] for r in rows), 'ADC-only gap changed button cadence')
        check(event_rows[0] in invalid and event_rows[1] > invalid[-1], 'tap during ADC gap and after recovery')
        a, b = scope['invalid_adc_windows_s'][0]
        check(a < actions[0] < b < actions[1], 'independent action marker inside ADC gap')
    elif name.startswith('pickup-gap-'):
        invalid = [i for i, r in enumerate(rows) if not r['adc_valid']]
        check(len(invalid) == 1000 and invalid == list(range(invalid[0], invalid[-1]+1)), name + ' gap extent')
        check(all(rows[i]['injected'] and rows[i]['accepted_ppm'] == -1 and not rows[i]['changed'] for i in invalid), name + ' invalid application')
        acquired = next(i for i, r in enumerate(rows) if r['state'] == 2)
        check(acquired > invalid[-1]+1, name + ' inferred missing crossing')
        check(all(r['state'] == 1 and r['value_ppm'] == 250000 and not r['changed'] for r in rows[:acquired]), name + ' premature takeover')
        check(245000 <= rows[acquired]['value_ppm'] <= 255000 and all(r['state'] == 2 for r in rows[acquired:]), name + ' observed reacquisition')
        a, b = scope['invalid_adc_windows_s'][0]
        points = voltage_points(scope)
        before = next(v for t, v in reversed(points) if t < a)
        after = next(v for t, v in points if t > b)
        inside = [v for t, v in points if a < t < b]
        up = name.endswith('-up')
        check((before < .7 and after > 1.) if up else (before > 1. and after < .7), name + ' physical crossing direction')
        check(min(inside) < .825 < max(inside), name + ' nominal analog target crossed during invalidity')
    elif name == 'moving-target':
        changes = [i for i, r in enumerate(rows) if i == 0 or r['state'] != rows[i-1]['state']]
        check([rows[i]['state'] for i in changes] == [1, 2, 1, 2], 'ownership revoked and reacquired')
        _, first, edit, again = changes
        check([i for i, r in enumerate(rows) if r['external_milli'] >= 0] == [edit], 'one target edit')
        check(rows[edit]['external_milli'] == 750 and rows[edit-1]['raw'] < 32768 <= rows[edit]['raw'], 'raw midpoint trigger')
        check(all(r['value_ppm'] == 750000 and not r['changed'] for r in rows[edit:again]), 'new target retained')
        check(245000 <= rows[first]['value_ppm'] <= 255000 and 745000 <= rows[again]['value_ppm'] <= 755000, 'pickup neighborhoods')
        check(rows[again]['time_us']-rows[edit]['time_us'] > 3000000, 'observed waiting interval')
    else:
        check(run['scenario'] == 12 and all(r['state'] == 1 for r in rows), name + ' startup ownership')
        prefix = align['pre_application_high_intervals_s']
        check(len(prefix) == 1 and prefix[0][1] < -.010 and prefix[0][1]-prefix[0][0] > .010, name + ' preserved startup prefix')
        volts = [v for _, v in voltage_points(scope)]
        if name == 'reset-released':
            check(meta['startup_kind'] == 'reset' and not run['startup_held'] and not edges, 'released RESET')
            check(all(r['value_ppm'] == 250000 and r['raw'] > 60000 for r in rows) and min(volts) > 3., 'high endpoint waits')
        else:
            check(meta['startup_kind'] == 'usb-power-cycle' and run['startup_held'] and not scope['button_initial_high'], 'held power-on')
            check(len(edges) == 3 and edges[0] > .6 and .010 < actions[0]-edges[-1] < .012, 'only fresh tap acts after startup hold')
            check(all(r['value_ppm'] == 250000 for r in rows[:event_rows[0]]) and all(r['value_ppm'] == 750000 for r in rows[event_rows[0]:]), 'no held-release action')
            check(min(volts) > 1. and max(volts) < 2.5 and all(20000 < r['raw'] < 45000 for r in rows), 'midpoint agreement')
            before = scope['pre_application_analog']['median_volts']
            longest = streak = 0
            for v in before:
                streak = streak+1 if v < .15 else 0
                longest = max(longest, streak)
            check(longest*scope['pre_application_analog']['period_s'] >= 4 and before[0] > 1. and before[-1] > 1., 'physical low interval during USB power cycle')
    print('PASS:', name, count, 'recorded samples; physical expectations checked')
