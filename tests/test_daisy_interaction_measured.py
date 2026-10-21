#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Check actual physical stimulus, target ownership and tracking under load."""
from bisect import bisect_left, bisect_right
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import load_capture

DATA = ROOT/'tests/measured/daisy/2026-10-18-interaction-load'
REPLAY = Path(sys.argv[1])


def sweep_indices(raw, cursor, up, count):
    """Last departure from one endpoint band, then arrival at the other."""
    legs = []
    for _ in range(count):
        end = next(i for i in range(cursor, len(raw))
                   if (raw[i] > .95 if up else raw[i] < .05))
        start = max(i for i in range(cursor, end)
                    if (raw[i] <= .05 if up else raw[i] >= .95)) + 1
        legs.append((start, end, up))
        cursor, up = end+1, not up
    return legs


# Brief chatter around 95% must not start the return leg before the stop.
assert sweep_indices([0, .04, .5, .96, .94, 1, .96, .94, .5, .04, 0], 0, True, 2) == [
    (2, 3, True), (7, 9, False)]

for name, target in [('moving-tap', 250000), ('paced-reversals', 250000),
                     ('quick-reversals', 750000), ('moving-hold', 750000)]:
    meta = json.loads((DATA/(name+'.json')).read_text())
    packed = (DATA/(name+'.txt.gz')).read_bytes()
    wire = gzip.decompress(packed)
    assert hashlib.sha256(packed).hexdigest() == meta['compressed_sha256']
    assert hashlib.sha256(wire).hexdigest() == meta['raw_sha256']
    writer = dict(meta['load']['host_writer'], error=None)
    with tempfile.TemporaryDirectory() as td:
        summary = load_capture.save_analysis(wire, Path(td), meta['firmware_build_id'], REPLAY, False, writer)
    assert summary['checks']['status'] == meta['load']['quality_status'] == 'pass'
    assert summary['checks']['failures'] == meta['load']['quality_failures'] == []
    assert summary['counters'] == meta['load']['counters']
    assert summary['configuration'] == meta['load']['configuration']
    config = summary['configuration']
    assert (config['mode'], config['duration_ms'], config['audio_permille'],
            config['block_size'], config['usb_hz']) == (0, 60000, 650, 16, 500)
    assert config['target_milli']*1000 == target and config['startup_held'] == 1
    assert meta['load']['stationary'] is False
    assert summary['counters']['samples'] == meta['samples'] == 60000
    assert '60000 samples replayed' in summary['replay']
    _, controls, _ = load_capture.parse(wire)
    _, run, rows = load_capture.capture.parse(controls)
    assert run['startup_held']
    assert all(r['adc_valid'] and r['cadence_valid'] and r['external_milli'] == -1 for r in rows)
    scope, align = meta['scope'], meta['scope']['alignment']
    assert scope['service_pulses'] == len(rows) and scope['sampled_button_disagreements'] == 0
    assert not scope['service_gaps'] and not scope['invalid_adc_windows_s']
    assert not align['pre_application_high_intervals_s']
    assert align['max_fit_residual_us'] < 5 and align['max_interval_error_us'] < 5
    assert align['max_work_width_error_us'] < 3
    outside = scope['outside_application_action_edges_s']
    # Collect() clears a latched high before its first service edge.
    assert len(outside) == int(scope['action_initial_high'])
    assert all(-10e-6 < t < 0 for t in outside)
    scale = 1+align['clock_scale_ppm']/1e6
    times = [(r['time_us']-rows[0]['time_us'])*1e-6*scale for r in rows]
    raw = [r['raw']/65535 for r in rows]
    analog = scope['analog']
    volts = analog['median_volts']
    voltage_times = [analog['first_center_s']+i*analog['period_s'] for i in range(len(volts))]
    assert len(volts) >= 5990

    def value_at(values, ts, center, half):
        selected = values[bisect_left(ts, center-half):bisect_right(ts, center+half)]
        assert selected
        return median(selected)

    def position(t, half=.05):
        return value_at(raw, times, t, half)

    def voltage(t):
        return value_at(volts, voltage_times, t, .015)

    initial_high = name in ('quick-reversals', 'moving-hold')
    final_high = 'reversals' in name
    assert (median(raw[:500]) > .98) if initial_high else (median(raw[:500]) < .02)
    assert (median(raw[-500:]) > .98) if final_high else (median(raw[-500:]) < .02)
    assert (median(volts[:50]) > 3.) if initial_high else (median(volts[:50]) < .15)
    assert (median(volts[-50:]) > 3.) if final_high else (median(volts[-50:]) < .15)
    assert rows[-1]['value_ppm'] == (1000000 if final_high else 0)
    edges, actions = scope['button_edges_s'], scope['action_edges_s']
    events = [r for r in rows if r['gesture']]
    assert not scope['button_initial_high'] and edges[0] >= 1
    assert len(actions) == len(events) == len(scope['action_service_windows_s'])
    assert all(lo <= t <= hi for t, (lo, hi) in zip(actions, scope['action_service_windows_s']))
    assert all(not r['gesture'] for r,t in zip(rows,times) if t < edges[0])
    epochs, targets = [0], [target]
    if name in ('moving-tap', 'moving-hold'):
        expected = [1, 2] if name == 'moving-tap' else [2]
        assert [r['gesture'] for r in events] == expected
        assert len(edges) == 1+2*len(expected)
        for i, (row, t) in enumerate(zip(events, actions)):
            press, release = edges[1+2*i:3+2*i]
            assert press > edges[0]+.1
            physical = position(t)
            movement = position(t+.25)-position(t-.25)
            voltage_change = voltage(t+.25)-voltage(t-.25)
            if row['gesture'] == 1:
                assert .020 <= release-press < .5 and .005 <= t-release <= .025
                assert .30 < physical < .65 and movement > .025 and voltage_change > .05
                assert row['target_ppm'] == 750000
            else:
                assert 2 <= release-press <= 10 and .605 <= t-press <= .625 and t < release
                assert row['target_ppm'] == 500000
                if name == 'moving-hold':
                    assert .55 < physical < .98 and movement < -.025 and voltage_change < -.05
                else:
                    # This earlier attempt is useful evidence of a moving tap,
                    # but its hold acted before motion. Do not qualify it as a
                    # hold during movement merely because replay passes.
                    assert physical > .98 and abs(movement) < .005 and abs(voltage_change) < .025
            assert row['state'] == 1 and abs(voltage(t)-physical*3.3) < .20
            epochs.append(row['seq'])
            targets.append(row['target_ppm'])
    else:
        assert not events and len(edges) == 1
        paced = name == 'paced-reversals'
        legs = sweep_indices(raw, bisect_right(times, edges[0]), paced, 5 if paced else 4)
        assert min(raw[legs[-1][1]+1:]) > .95
        for i, (start, end, up) in enumerate(legs):
            duration = times[end]-times[start]
            if not paced:
                assert .1 < duration < 2.
            # Compare physical voltage throughout each leg, not just endpoints.
            for seq in range(start+20, end-20, 100):
                assert abs(voltage(times[seq])-position(times[seq], .015)*3.3) < .20
            if i+1 < len(legs):
                next_start = legs[i+1][0]
                delay = times[next_start]-times[end]
                assert (max(raw[end:next_start+1]) > .98) if up else (min(raw[end:next_start+1]) < .02)
                if paced:
                    assert delay > 1., 'The paced attempt must not become immediate-reversal evidence'
                else:
                    assert delay < .5
    epochs.append(len(rows))
    for start, end, target in zip(epochs[:-1], epochs[1:], targets):
        assert all(r['target_ppm'] == target for r in rows[start:end])
        found = next(i for i in range(start, end) if rows[i]['state'] == 2)
        assert found > start
        assert all(r['state'] == 1 and r['value_ppm'] == target and not r['changed'] for r in rows[start:found])
        assert all(r['state'] == 2 and r['value_ppm'] == r['accepted_ppm'] for r in rows[found:end])
        before, current = rows[found-1]['accepted_ppm'], rows[found]['accepted_ppm']
        assert abs(current-target) < 5000 or (before-target)*(current-target) <= 0
        assert abs(voltage(times[found])-rows[found]['raw']/65535*3.3) < .20
    print('PASS:', name, '60000 observations replayed; actual physical sequence and ownership checked')
