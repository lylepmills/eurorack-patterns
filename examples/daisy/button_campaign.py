#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Automate one button case on two explicitly identified Daisy boards.

This records software evidence only. Pair with a scope recording and physical
review before qualification. Explicit fault delays use the receiver's observed raw edge. Requested generator
phase is not a measured receiver phase; scope review supplies that evidence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import capture
import load_capture
import pulse_generator
from capture import require

CASES = ('baseline', 'press-stall', 'hold-stall', 'release-stall', 'press-adc-gap')


def timetable(case, phase_us=0):
    require(case in CASES and type(phase_us) is int and 0 <= phase_us < 1000,
            'invalid case or requested phase')
    if case == 'baseline':
        times = [1000000,1100000,2000000,2700000,3500000,3600000]
    elif case in ('press-stall', 'hold-stall'):
        times = [1000000,3000000,4000000,4100000]
    else:
        times = [1000000,1100000,3000000,3100000]
    return [t+phase_us for t in times]


def timed_expectations(rows, scenario, stimulus):
    """Boundary oracle from raw dwell intervals, independent of gesture flags.

    Restricted to the clean two-pair apparatus sequence. Integer milliseconds
    are part of this adapter's contract. Split a pending dwell at missing service;
    a role already qualified before that gap cannot become actionable again.
    """
    require(scenario in (5, 6, 7, 8), 'unsupported timed button case')
    times = [r['time_us'] for r in rows]
    edges = [i for i, r in enumerate(rows) if bool(r['pressed']) !=
             (bool(rows[i-1]['pressed']) if i else False)]
    require(len(edges) == 4 and not rows[-1]['pressed'], 'timed case needs two complete raw presses')
    gaps = [i for i in range(1, len(rows)) if times[i]-times[i-1] > 10000]
    require(len(gaps) == (0 if scenario == 8 else 1), 'unexpected raw service gap')
    # Dwell qualification is the first observation in the relevant millisecond.
    def eligible(start, stop, dwell_ms):
        deadline = (times[start]//1000 + dwell_ms)*1000
        return next((i for i in range(start, stop) if times[i] >= deadline), None)
    events, qualification = [], []
    for pair, (press, release) in enumerate(zip(edges[::2], edges[1::2])):
        stop = edges[2*pair+2] if pair == 0 else len(rows)
        candidate = press
        qualified = eligible(candidate, release, 10)
        # A gap before qualification invalidates only this candidate's dwell.
        for gap in gaps:
            if press < gap < release and (qualified is None or gap <= qualified):
                candidate = gap
                qualified = eligible(candidate, release, 10)
        require(qualified is not None, 'press too short for this boundary experiment')
        qualification.append(times[qualified])
        hold = eligible(qualified, release, 600)
        released = eligible(release, stop, 10)
        require(released is not None, 'missing settled release')
        event = hold if hold is not None else released
        # A cadence break consumes a qualified role before event processing,
        # including a break in the very observation that would emit its action.
        if any(qualified < gap <= event for gap in gaps):
            continue
        events.append(dict(pair=pair, gesture=2 if hold is not None else 1,
                           seq=event, time_us=times[event]))
    initial_qual = eligible(edges[0], edges[1], 10)
    threshold = ((times[edges[1]]//1000+10)*1000 if scenario == 7 else
                 (times[edges[0]]//1000+10)*1000 if scenario == 5 else
                 (times[initial_qual]//1000+600)*1000 if scenario == 6 else None)
    boundary = dict(expected_events=events, qualified_press_us=qualification,
                    threshold_us=threshold,
                    fault_begin_minus_threshold_us=None if threshold is None else stimulus['begin_us']-threshold)
    if gaps:
        gap = gaps[0]
        boundary.update(last_service_before_fault_us=times[gap-1], first_service_after_fault_us=times[gap])
    first = next((e for e in events if e['pair'] == 0), None)
    boundary['first_gesture_outcome'] = ('cancelled' if first is None else
        'requalified_after_gap' if qualification[0] > stimulus['end_us'] and scenario == 5 else
        'hold_before_gap' if first['gesture'] == 2 and scenario == 6 else
        'tap_before_gap' if scenario == 7 else 'retained')
    return boundary


def review_controls(summary, rows, case):
    """Expected outcomes derive from the prescribed sequence, not its replay."""
    require(summary['checks']['status'] == 'pass', 'load quality checks failed')
    c = summary['configuration']
    expected_scenario = 0 if case == 'baseline' else capture.SCENARIOS[case]
    require(c.get('scenario', 0) == expected_scenario and not c['startup_held'],
            'wrong case or button held at start')
    if c.get('fault_delay_us'):
        result = timed_expectations(rows, c['scenario'], summary['fault'])
        actual = [(r['seq'], r['gesture']) for r in rows if r['gesture']]
        expected = [(e['seq'], e['gesture']) for e in result['expected_events']]
        require(actual == expected, 'timed boundary actions/deadlines mismatch')
        return dict(status='pass', boundary=result,
                    expected_gestures=[e['gesture'] for e in result['expected_events']],
                    action_sequences=[e['seq'] for e in result['expected_events']], physical_review='pending')
    expected = [1,2,1] if case == 'baseline' else [1,1] if case == 'press-adc-gap' else [1]
    actions = [r for r in rows if r['gesture']]
    require([r['gesture'] for r in actions] == expected, 'unexpected actions/cancellation')
    # Each raw release is also checked against the physical input later.
    presses, releases = [], []
    previous = False
    for r in rows:
        if r['pressed'] and not previous: presses.append(r)
        if previous and not r['pressed']: releases.append(r)
        previous = bool(r['pressed'])
    expected_pairs = len(timetable(case))//2
    require(len(presses) == len(releases) == expected_pairs and not previous,
            'incomplete or extra observed button transition')
    if case == 'baseline':
        require(releases[0]['time_us'] < actions[0]['time_us'] < presses[1]['time_us']
                and presses[1]['time_us'] < actions[1]['time_us'] < releases[1]['time_us']
                and releases[2]['time_us'] < actions[2]['time_us'], 'baseline action placement')
    elif case == 'press-adc-gap':
        require(not actions[0]['adc_valid'] and actions[0]['injected']
                and actions[1]['adc_valid'] and not actions[1]['injected'],
                'ADC-only fault did not span first tap or recover before second')
        require(all(releases[i]['time_us'] < actions[i]['time_us'] for i in (0,1)),
                'tap before release')
    else:
        require(releases[-1]['time_us'] < actions[0]['time_us'],
                'cancelled first press produced an action')
    return dict(status='pass', expected_gestures=expected,
                action_sequences=[r['seq'] for r in actions],
                observed_presses=[r['time_us'] for r in presses],
                observed_releases=[r['time_us'] for r in releases],
                physical_review='pending')


def record(a):
    times = timetable(a.case, a.phase_us)
    fault_delay_us = getattr(a, 'fault_delay_us', 0)
    require(a.port != a.generator_port, 'fixture and generator ports must differ')
    fixture = capture.load_manifest(a.manifest)
    generator = pulse_generator.load_manifest(a.generator_manifest)
    require(fixture.get('load_faults') == 1 and a.replay.is_file(), 'loaded fault firmware/replay required')
    if fault_delay_us:
        require(fixture.get('fault_timing') == 1, 'fixture lacks configurable fault timing')
    a.out.mkdir(parents=True, exist_ok=False)
    meta = dict(schema=1, status='incomplete', case=a.case, times_us=times,
                requested_input_phase_us=a.phase_us,
                phase_note='Requested offset in the generator clock, not measured DUT service phase.',
                acquired_utc=datetime.now(timezone.utc).isoformat(),
                fixture_build=fixture, generator_build=generator)
    if fault_delay_us: meta['fault_delay_us'] = fault_delay_us
    path = a.out/'campaign.json'
    path.write_text(json.dumps(meta, indent=2)+'\n')
    (a.out/'generator').mkdir()
    args = SimpleNamespace(port=a.port, manifest=a.manifest, out=a.out/'fixture',
        mode='trace', seconds=8, target=.25, audio_permille=a.audio_permille,
        block_size=16, usb_hz=a.usb_hz, stationary=False, replay=a.replay,
        download_timeout=90, scenario='manual' if a.case == 'baseline' else a.case,
        fault_delay_us=fault_delay_us)
    # Validate load choices before opening either serial port.
    load_capture.validate_config(dict(mode=0, duration_ms=8000, target_milli=250,
        audio_permille=a.audio_permille, block_size=16, usb_hz=a.usb_hz, startup_held=0,
        scenario=capture.SCENARIOS[args.scenario], fault_delay_us=fault_delay_us))
    import serial
    port = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=2)
    port.dtr = False; port.rts = False
    if sys.platform != 'win32': port.exclusive = True
    port.port = a.generator_port
    with port, (a.out/'generator/raw.txt').open('wb') as raw:
        gen = pulse_generator.Generator(port, raw, generator)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = None
            def started():
                nonlocal pending
                gen.start()
                pending = pool.submit(gen.finish)
            try:
                gen.prepare(times)
                code = load_capture.record(args, on_started=started)
                require(pending is not None, 'fixture did not acknowledge a run')
                pending.result(timeout=15)
                require(code == 0, 'fixture acquisition/quality failed')
            except BaseException:
                if gen.identified:
                    try: gen.abort()
                    except Exception: pass
                raise
    # All evidence remains even when subsequent outcome or scope review fails.
    source = pulse_generator.parse((a.out/'generator/raw.txt').read_bytes(), generator['build_id'], times)
    (a.out/'generator/summary.json').write_text(json.dumps(source, indent=2)+'\n')
    summary = json.loads((a.out/'fixture/summary.json').read_text())
    _, controls, _ = load_capture.parse((a.out/'fixture/raw.txt').read_bytes(), fixture['build_id'])
    _, _, rows = capture.parse(controls, fixture['build_id'])
    review = review_controls(summary, rows, a.case)
    (a.out/'controls-review.json').write_text(json.dumps(review, indent=2)+'\n')
    meta['status'] = 'software checks passed; physical review pending'
    path.write_text(json.dumps(meta, indent=2)+'\n')
    print(meta['status'], flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', required=True)
    p.add_argument('--generator-port', required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--generator-manifest', type=Path, required=True)
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--case', choices=CASES, required=True)
    p.add_argument('--fault-delay-us', type=int, default=0)
    p.add_argument('--phase-us', type=int, default=0)
    p.add_argument('--audio-permille', type=int, default=650)
    p.add_argument('--usb-hz', type=int, default=500)
    record(p.parse_args())


if __name__ == '__main__': main()
