#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Complete loaded fault recordings; physical cancellation and input independence."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import load_capture

def load_recording(name, scenario, missed, cadence, duration_ms=60000):
    prefix = ROOT/'tests/measured/daisy/2026-10-18-fault-load'/name
    count = duration_ms-missed
    meta = json.loads(prefix.with_suffix('.json').read_text())
    compressed = prefix.with_suffix('.txt.gz').read_bytes()
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == meta['raw_sha256']
    assert hashlib.sha256(compressed).hexdigest() == meta['compressed_sha256']
    with tempfile.TemporaryDirectory() as td:
        summary = load_capture.save_analysis(raw, Path(td), meta['firmware_build_id'],
            Path(sys.argv[1]), False, dict(meta['load']['host_writer'], error=None))
    assert summary['checks']['status'] == meta['load']['quality_status'] == 'pass'
    assert summary['checks']['failures'] == meta['load']['quality_failures'] == []
    assert summary['counters'] == meta['load']['counters']
    assert summary['configuration'] == meta['load']['configuration']
    c = summary['configuration']
    assert (c['mode'], c['scenario'], c['duration_ms'], c['target_milli'],
            c['audio_permille'], c['block_size'], c['usb_hz'], c['startup_held']) == (0, scenario, duration_ms, 250, 650, 16, 500, 1)
    assert summary['counters']['samples'] == meta['samples'] == count
    assert summary['counters']['missed'] == summary['fault']['allowed_missed'] == missed
    assert summary['cadence_breaks'] == summary['fault']['allowed_cadence_breaks'] == cadence
    assert f'{count} samples replayed' in summary['replay']
    _, controls, _ = load_capture.parse(raw)
    _, run, rows = load_capture.capture.parse(controls)
    assert run['startup_held'] and run['stimulus_status'] == 'completed'
    return meta, run, rows


def check_recording(name, scenario, missed):
    meta, run, rows = load_recording(name, scenario, missed, 1)
    assert all(r['adc_valid'] and not r['injected'] for r in rows)
    assert all(r['state'] == 1 and not r['changed'] and r['raw'] < 2000 for r in rows)
    events = [r for r in rows if r['gesture']]
    assert len(events) == 1 and events[0]['gesture'] == 1
    event = events[0]
    assert all(r['value_ppm'] == 250000 for r in rows[:event['seq']])
    assert all(r['value_ppm'] == 750000 for r in rows[event['seq']:])

    scope = meta['scope']
    assert scope['service_pulses'] == len(rows) and scope['sampled_button_disagreements'] == 0
    assert not scope['invalid_adc_windows_s'] and not scope['button_initial_high']
    alignment = scope['alignment']
    assert alignment['max_fit_residual_us'] < 5 and alignment['max_interval_error_us'] < 5
    assert alignment['max_work_width_error_us'] < 3
    assert not alignment['pre_application_high_intervals_s']
    outside = scope['outside_application_action_edges_s']
    if scenario in (5, 7):
        assert not scope['action_initial_high'] and not outside
    else:
        # The arming poll left the action marker high; Collect clears it before
        # the first sample. Preserve this setup edge, never count it as an action.
        assert scope['action_initial_high'] and len(outside) == 1
        assert -10e-6 < outside[0] < 0
    edges, actions, windows = [scope[k] for k in ('button_edges_s', 'action_edges_s', 'action_service_windows_s')]
    assert edges[0] >= 1 and edges[1] > edges[0] + .1
    if scenario == 7:
        # Initial held release; first tap's press bounces closed/open/closed;
        # first release; second tap/release. Keep all seven physical edges.
        assert len(edges) == 7
        assert 0 < edges[2]-edges[1] < .001 and 0 < edges[3]-edges[2] < .001
        assert .020 <= edges[4]-edges[3] < .5
        assert edges[5] > edges[4] + 1 and .020 <= edges[6]-edges[5] < .5
    else:
        # Initial held release, fresh hold/release, fresh tap/release.
        assert len(edges) == (7 if scenario == 5 else 5)
        assert edges[2]-edges[1] >= 1.5
        assert edges[3] > edges[2] + .1 and .020 <= edges[4]-edges[3] < .5
        # The press-stall tap release bounced once. Keep all physical edges.
        if scenario == 5:
            assert edges[2]-edges[1] <= 4
            assert 0 < edges[5]-edges[4] < .010 and 0 < edges[6]-edges[5] < .010
    assert len(actions) == len(windows) == 1 and windows[0][0] <= actions[0] <= windows[0][1]
    assert .005 <= actions[0]-edges[-1] <= .025
    assert all(-.15 < v < .15 for v in scope['analog']['median_volts'])

    assert len(scope['service_gaps']) == 1
    gap = scope['service_gaps'][0]
    assert 25000 < gap['interval_us'] < 28000
    if scenario == 7:
        assert 0 < gap['start_s']-edges[4] < .001
        assert gap['end_s'] < edges[5]
    else:
        assert edges[1] < gap['start_s'] < gap['end_s'] < edges[2]
    recovery = gap['after_seq']+1
    assert [r['seq'] for r in rows if not r['cadence_valid']] == [recovery]
    assert all(r['missed'] == 0 for r in rows[:recovery])
    assert all(r['missed'] == missed for r in rows[recovery:])
    stimulus = run['stimulus']
    if scenario == 5:
        assert stimulus['begin_us']-stimulus['trigger_us'] == 100204
        assert stimulus['end_us']-stimulus['begin_us'] == 25992
        assert rows[recovery]['time_us']-stimulus['end_us'] == 1
        # This is the real counterexample to requiring the due instant itself to be
        # inside the stall. The first missed slot was still serviceable at entry.
        first_lost = (rows[recovery-1]['time_us']//1000+1)*1000
        assert stimulus['begin_us']-first_lost == 204
        assert first_lost//1000 == stimulus['begin_us']//1000
    elif scenario == 6:
        # The actual deadline starts on qualified press, not the raw input edge.
        qualified = next(r for i, r in enumerate(rows) if i and r['debounced'] and
                         not rows[i-1]['debounced'] and r['time_us'] >= stimulus['trigger_us'])
        deadline_us = (qualified['time_us']//1000 + 600)*1000
        assert stimulus['begin_us'] < deadline_us < stimulus['end_us']
        # Map the qualified deadline into the independent scope clock, anchored
        # to the last matched service edge before the interruption.
        clock_scale = 1 + alignment['clock_scale_ppm'] / 1e6
        deadline_s = gap['start_s'] + (deadline_us-rows[recovery-1]['time_us']) * clock_scale / 1e6
        assert gap['start_s'] + 5e-6 < deadline_s < gap['end_s'] - 5e-6
        assert rows[recovery-1]['time_us'] < deadline_us < rows[recovery]['time_us']
        assert rows[recovery]['time_us'] < event['time_us']
        assert stimulus['begin_us']-stimulus['trigger_us'] == 605165
        assert stimulus['end_us']-stimulus['begin_us'] == 25646
        assert rows[recovery]['time_us'] == stimulus['end_us']
    else:
        # The first raw release starts the pause while the qualified input is
        # still pressed. Cadence invalidation must cancel this pending tap.
        trigger = rows[recovery-1]
        assert trigger['time_us'] == stimulus['trigger_us']
        assert rows[recovery-2]['pressed'] and not trigger['pressed']
        assert trigger['debounced'] and rows[recovery]['debounced']
        assert stimulus['begin_us']-stimulus['trigger_us'] == 335
        assert stimulus['end_us']-stimulus['begin_us'] == 25323
        assert rows[recovery]['time_us'] == stimulus['end_us']
        release = next(r for r in rows[recovery:] if not r['debounced'])
        second_press = next(r for r in rows[release['seq']:] if r['pressed'])
        assert not release['gesture'] and release['time_us'] < second_press['time_us'] < event['time_us']
    print('PASS:', name, len(rows), 'loaded observations; physical cancellation, recovery and slot accounting checked')


def check_adc_gap():
    meta, run, rows = load_recording('press-adc-gap', 8, 0, 0)
    assert all(r['cadence_valid'] and not r['missed'] for r in rows)
    assert all(r['state'] == 1 and not r['changed'] and r['raw'] < 2000 for r in rows)
    invalid = [i for i, r in enumerate(rows) if not r['adc_valid']]
    # A duration in microseconds need not contain exactly 250 scheduled samples.
    # The first invalid observation is 29 us into its slot; the final one falls
    # just before expiry, and the next observation is the first valid one.
    assert invalid == list(range(4369, 4620))
    stimulus = run['stimulus']
    begin, end = stimulus['begin_us'], stimulus['end_us']
    assert begin-stimulus['trigger_us'] == 20994
    assert end-begin == 250971
    assert rows[invalid[0]]['time_us'] == begin
    assert rows[invalid[-1]]['time_us'] < begin+250000 <= rows[invalid[-1]+1]['time_us'] == end
    assert end-(begin+250000) < 1000
    assert all(bool(r['injected']) == (i in invalid) for i, r in enumerate(rows))
    assert all(rows[i]['accepted_ppm'] == -1 for i in invalid)
    events = [r for r in rows if r['gesture']]
    assert len(events) == 2 and all(r['gesture'] == 1 for r in events)
    first, second = events
    assert first['seq'] in invalid and second['seq'] > invalid[-1]
    first_release = next(r for r in rows[invalid[0]:] if not r['pressed'])
    assert begin < first_release['time_us'] < first['time_us'] < end < second['time_us']
    assert all(r['value_ppm'] == 250000 for r in rows[:first['seq']])
    assert all(r['value_ppm'] == 750000 for r in rows[first['seq']:second['seq']])
    assert all(r['value_ppm'] == 250000 for r in rows[second['seq']:])

    scope = meta['scope']
    assert scope['service_pulses'] == len(rows) and scope['sampled_button_disagreements'] == 0
    assert not scope['service_gaps'] and not scope['button_initial_high']
    assert not scope['action_initial_high'] and not scope['outside_application_action_edges_s']
    alignment = scope['alignment']
    assert alignment['max_fit_residual_us'] < 5 and alignment['max_interval_error_us'] < 5
    assert alignment['max_work_width_error_us'] < 3 and not alignment['pre_application_high_intervals_s']
    edges, actions, windows = [scope[k] for k in ('button_edges_s', 'action_edges_s', 'action_service_windows_s')]
    # Initial held release; a bounced first press/release; second press/release.
    assert len(edges) == 7 and edges[0] >= 1 and edges[1] > edges[0]+.1
    assert 0 < edges[2]-edges[1] < .001 and 0 < edges[3]-edges[2] < .001
    assert .020 <= edges[4]-edges[3] < .5
    assert edges[5] > edges[4]+1 and .020 <= edges[6]-edges[5] < .5
    assert len(actions) == len(windows) == 2
    assert all(a <= t <= b for t, (a, b) in zip(actions, windows))
    assert all(.005 <= t-release <= .025 for t, release in zip(actions, (edges[4], edges[6])))
    assert len(scope['invalid_adc_windows_s']) == 1
    start, finish = scope['invalid_adc_windows_s'][0]
    assert start < edges[4] < actions[0] < finish < edges[5] < actions[1]
    assert .250 <= finish-start < .252
    assert all(-.15 < v < .15 for v in scope['analog']['median_volts'])
    print('PASS: press-adc-gap 60000 loaded observations; rejected knob samples and both independent taps checked')


def check_pickup_gap(name):
    upward = name == 'pickup-gap-up'
    duration = 150000 if upward else 60000
    meta, run, rows = load_recording(name, 9 if upward else 10, 0, 0, duration)
    assert all(r['cadence_valid'] and not r['missed'] and not r['gesture'] and not r['actions'] for r in rows)
    assert all(r['target_ppm'] == 250000 for r in rows)
    invalid = [i for i, r in enumerate(rows) if not r['adc_valid']]
    assert invalid == list(range(5338, 6338) if upward else range(13655, 14655))
    first, last = invalid[0], invalid[-1]
    stimulus = run['stimulus']
    begin, end = stimulus['begin_us'], stimulus['end_us']
    assert begin-stimulus['trigger_us'] == (1007 if upward else 1000)
    assert end-begin == (1000035 if upward else 1000000)
    assert rows[first]['time_us'] == begin and rows[last+1]['time_us'] == end
    assert rows[last]['time_us'] < begin+1000000 <= end < begin+1001000
    assert all(bool(r['injected']) == (first <= i <= last) for i, r in enumerate(rows))
    assert all(rows[i]['accepted_ppm'] == -1 and not rows[i]['changed'] for i in invalid)
    if upward:
        assert rows[first-2]['raw'] < 9831 <= rows[first-1]['raw']
        assert rows[last+1]['raw'] > 32768
    else:
        assert rows[first-2]['raw'] > 22937 >= rows[first-1]['raw']
        assert rows[last+1]['raw'] < 2000
    assert rows[first-1]['time_us'] == stimulus['trigger_us']
    assert rows[last+1]['value_ppm'] == 250000
    acquired = next(i for i, r in enumerate(rows) if r['state'] == 2)
    assert acquired == (11135 if upward else 21162) and rows[acquired]['time_us']-end > 1000000
    assert all(r['state'] == 1 and r['value_ppm'] == 250000 and not r['changed'] for r in rows[:acquired])
    assert 245000 <= rows[acquired]['value_ppm'] == rows[acquired]['accepted_ppm'] <= 255000
    if upward:
        assert rows[acquired-1]['accepted_ppm'] > 255000
    else:
        assert rows[acquired-1]['accepted_ppm'] < 245000
    assert rows[acquired]['changed']
    assert all(r['state'] == 2 for r in rows[acquired:])
    assert all(r['value_ppm'] == (0 if upward else 451713) and not r['changed'] for r in rows[-20000:])

    scope = meta['scope']
    assert scope['service_pulses'] == len(rows) and scope['sampled_button_disagreements'] == 0
    assert not scope['service_gaps'] and not scope['button_initial_high']
    assert len(scope['button_edges_s']) == 1 and 1 < scope['button_edges_s'][0] < begin/1e6
    assert not scope['action_edges_s'] and not scope['action_service_windows_s']
    assert not scope['action_initial_high'] and not scope['outside_application_action_edges_s']
    alignment = scope['alignment']
    assert alignment['max_fit_residual_us'] < 5 and alignment['max_interval_error_us'] < 5
    assert alignment['max_work_width_error_us'] < 3 and not alignment['pre_application_high_intervals_s']
    assert len(scope['invalid_adc_windows_s']) == 1
    start, finish = scope['invalid_adc_windows_s'][0]
    assert 1 <= finish-start < 1.002
    analog = scope['analog']
    points = [(analog['first_center_s']+i*analog['period_s'], v) for i, v in enumerate(analog['median_volts'])]
    before = next(v for t, v in reversed(points) if t < start)
    after = next(v for t, v in points if t > finish)
    inside = [v for t, v in points if start < t < finish]
    if upward:
        assert before < .7 and after > 1.6
    else:
        assert before > 1.1 and -.15 < after < .15
    assert min(inside) < .825 < max(inside)
    # The independent voltage path crosses the nominal target while readings
    # are invalid, then returns near that voltage when valid pickup acquires.
    acquired_s = (rows[acquired]['time_us']-rows[0]['time_us'])/1e6 * (1+alignment['clock_scale_ppm']/1e6)
    nearest = min(points, key=lambda p: abs(p[0]-acquired_s))
    assert abs(nearest[0]-acquired_s) <= .01 and .75 < nearest[1] < .9
    low, high = (-.15, .15) if upward else (1.4, 1.6)
    assert all(low < v < high for t, v in points if t > duration/1000-20)
    print('PASS:', name, len(rows), 'loaded observations; unseen crossing ignored, observed return acquires and settles')


check_recording('press-stall', 5, 26)
check_recording('hold-stall', 6, 24)
check_recording('release-stall', 7, 24)
check_adc_gap()
check_pickup_gap('pickup-gap-up')
check_pickup_gap('pickup-gap-down')
