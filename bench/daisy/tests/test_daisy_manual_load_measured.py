#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Replay measured loaded controls and check independently observed behavior."""
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import load_capture

DATA = ROOT/'bench/daisy/measured/daisy/2026-10-18-manual-load'
REPLAY = Path(sys.argv[1])

for name, seconds, target in [('gestures', 150, 250000),
                              ('pickup-up', 150, 250000), ('pickup-down', 60, 750000)]:
    meta = json.loads((DATA/(name+'.json')).read_text())
    compressed = (DATA/(name+'.txt.gz')).read_bytes()
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(compressed).hexdigest() == meta['compressed_sha256']
    assert hashlib.sha256(raw).hexdigest() == meta['raw_sha256']
    assert meta['load']['stationary'] is False
    writer = dict(meta['load']['host_writer'], error=None)
    with tempfile.TemporaryDirectory() as td:
        summary = load_capture.save_analysis(raw, Path(td), meta['firmware_build_id'], REPLAY, False, writer)
    assert summary['checks']['status'] == meta['load']['quality_status'] == 'pass'
    assert summary['checks']['failures'] == meta['load']['quality_failures'] == []
    assert summary['counters'] == meta['load']['counters']
    assert summary['configuration'] == meta['load']['configuration']
    c = summary['configuration']
    assert (c['mode'], c['duration_ms'], c['audio_permille'], c['block_size'], c['usb_hz']) == (0, seconds*1000, 650, 16, 500)
    assert c['target_milli']*1000 == target and c['startup_held'] == 1
    assert summary['counters']['samples'] == meta['samples'] == seconds*1000
    assert f'{seconds*1000} samples replayed' in summary['replay']
    _, control_data, _ = load_capture.parse(raw)
    _, run, rows = load_capture.capture.parse(control_data)
    assert run['startup_held'] and all(r['adc_valid'] and r['cadence_valid'] for r in rows)
    scope = meta['scope']
    assert scope['service_pulses'] == len(rows) and scope['sampled_button_disagreements'] == 0
    assert not scope['service_gaps'] and not scope['invalid_adc_windows_s']
    alignment = scope['alignment']
    assert alignment['max_fit_residual_us'] < 5 and alignment['max_interval_error_us'] < 5
    assert alignment['max_work_width_error_us'] < 3 and not alignment['pre_application_high_intervals_s']
    outside = scope['outside_application_action_edges_s']
    if name == 'pickup-down':
        # The preceding run left the marker high. Collect() clears it before
        # sampling: retain the measured setup falling edge, never an action.
        assert scope['action_initial_high'] and len(outside) == 1
        assert -10e-6 < outside[0] < 0
    else:
        assert not scope['action_initial_high'] and not outside
    actions, windows, edges = scope['action_edges_s'], scope['action_service_windows_s'], scope['button_edges_s']
    event_rows = [r for r in rows if r['gesture']]
    assert len(actions) == len(windows) == len(event_rows)
    assert all(a <= t <= b for t, (a, b) in zip(actions, windows))
    # The operator's starting hold was already down when acquisition began.
    # Its release must not become an action; it is not a power/reset test.
    assert not scope['button_initial_high'] and edges[0] >= 1
    assert all(not r['gesture'] for r in rows if r['time_us'] < edges[0]*1e6)
    analog = scope['analog']
    points = [(analog['first_center_s']+i*analog['period_s'], v)
              for i, v in enumerate(analog['median_volts'])]
    assert len(points) >= seconds*99
    if name == 'gestures':
        assert [r['gesture'] for r in event_rows] == [1, 1, 1, 1, 1, 2, 1]
        assert len(edges) == 15 and actions[0] > edges[0]+.1
        assert all(r['state'] == 1 and r['value_ppm'] == r['target_ppm'] for r in rows)
        assert [r['target_ppm'] for r in event_rows] == [750000, 250000, 750000, 250000, 750000, 500000, 250000]
        for i, row in enumerate(event_rows):
            press, release = edges[1+2*i:3+2*i]
            assert press > (edges[0] if i == 0 else edges[2*i])+.1
            if row['gesture'] == 1:
                assert .020 <= release-press < .5
                assert .005 <= actions[i]-release <= .025
            else:
                assert 1.5 <= release-press <= 4
                assert .605 <= actions[i]-press <= .625 and actions[i] < release
        assert abs(statistics.median(v for _, v in points[:50])-
                   statistics.median(v for _, v in points[-50:])) < .1
    else:
        assert len(edges) == 1 and not actions
        assert all(r['target_ppm'] == target and r['external_milli'] == -1 for r in rows)
        acquired = next(i for i, r in enumerate(rows) if r['state'] == 2)
        assert acquired > 0
        assert all(r['state'] == 1 and r['value_ppm'] == target and not r['changed'] for r in rows[:acquired])
        assert target-5000 <= rows[acquired]['value_ppm'] <= target+5000
        assert all(r['state'] == 2 and r['value_ppm'] == r['accepted_ppm'] for r in rows[acquired:])
        up = name == 'pickup-up'
        initial = statistics.median(r['raw'] for r in rows[:500])/65535
        final = statistics.median(r['raw'] for r in rows[-500:])/65535
        assert (initial < .02 and final > .98) if up else (initial > .98 and final < .02)
        assert rows[-1]['value_ppm'] == (1000000 if up else 0)
        initial_v = statistics.median(v for _, v in points[:50])
        final_v = statistics.median(v for _, v in points[-50:])
        assert (initial_v < .15 and final_v > 3.) if up else (initial_v > 3. and final_v < .15)
        scale = 1+alignment['clock_scale_ppm']/1e6
        catch_s = (rows[acquired]['time_us']-rows[0]['time_us'])*1e-6*scale
        catch_v = statistics.median(v for t, v in points if abs(t-catch_s) < .020)
        assert abs(catch_v-rows[acquired]['raw']/65535*3.3) < .15
    print('PASS:', name, len(rows), 'loaded observations replayed; physical actions/pickup checked')
