#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Review a stationary switched-jack trace and independent scope evidence.

This narrow preflight is not an insertion/withdrawal or production-input test.
All digital transitions are required; analog evidence covers one plateau sample
per observation, with the full native waveform retained by the operator.
"""
from bisect import bisect_right
import hashlib
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'examples/daisy'))
import jack_capture
from capture import require
from daisy_scope import match_service


CASES = {'empty': 'empty jack', 'inserted-open': 'inserted cable, far end open',
         'inserted-silent': 'inserted cable, far-end tip through 1k to ground'}


def review_presence(rows, rises, falls, presence, scale):
    """Match every output transition, including a retained-state command reset."""
    reset = int(presence['initial_high'])
    transitions, previous = [], False
    for i, r in enumerate(rows):
        current = bool(r['ready'] and r['patched'])
        if current != previous:
            transitions.append(i)
        previous = current
    require(len(presence['edges_s']) == reset + len(transitions),
            'unexpected qualified patched output')
    if reset:
        start = rises[0] - rows[0]['sample_us'] * scale / 1e6
        require(abs(presence['edges_s'][0]-start) < 5e-6, 'presence reset timing disagreement')
    for i, edge in zip(transitions, presence['edges_s'][reset:]):
        adc_end = rises[i] + (rows[i]['adc_end_us']-rows[i]['sample_us']) * scale / 1e6
        require(adc_end - 2e-6 <= edge <= falls[i], 'presence qualification timing disagreement')
    for r, t in zip(rows, falls):
        level = presence['initial_high'] ^ bool(bisect_right(presence['edges_s'], t) % 2)
        require(level == bool(r['ready'] and r['patched']), 'presence/sample mismatch')


def review_timing(raw, channels, build_id=None):
    """Check every service, probe and qualified-output edge in a complete run."""
    info, run, rows, changes = jack_capture.parse(raw, build_id)
    expected = {'sense', 'service', 'presence', 'probe'}
    if info['protocol'] >= 4: expected.add('audio')
    require(set(channels) == expected, 'missing/unknown channel')
    for name, d in channels.items():
        require(type(d['initial_high']) is bool, 'invalid initial state')
        times = d['edges_s']
        require(all(math.isfinite(t) for t in times) and
                all(a < b for a, b in zip(times, times[1:])), 'invalid ' + name + ' timeline')
        require(math.isfinite(d['begin_s']) and math.isfinite(d['end_s']) and d['begin_s'] < d['end_s'],
                'invalid channel duration')
        require(not times or d['begin_s'] < times[0] <= times[-1] < d['end_s'], 'missing edge margins')
    service_rows = [dict(time_us=r['sample_us'], work_us=r['end_us']-r['sample_us']) for r in rows]
    service = channels['service']
    rises, falls, alignment = match_service(service_rows, service['edges_s'], service['initial_high'])
    require(all(d['begin_s'] < rises[0] < falls[-1] < d['end_s'] for d in channels.values()),
            'missing full observation coverage')
    scale = 1 + alignment['clock_scale_ppm'] / 1e6
    require(not channels['probe']['initial_high'], 'probe must start low')
    expected, previous = [], False
    for r, t in zip(rows, rises):
        if bool(r['probe']) != previous:
            expected.append(t - (r['sample_us']-r['drive_us']) * scale / 1e6)
        previous = bool(r['probe'])
    probe = channels['probe']['edges_s']
    require(len(probe) == len(expected) + int(previous), 'unexpected probe edge count')
    probe_error = max(abs(a-b)*1e6 for a, b in zip(probe, expected))
    require(probe_error < 5, 'probe drive timing disagreement')
    terminal_error = None
    if previous:
        # Firmware returns the probe low at acquisition END, not at the end of
        # its last conversion. Keep the end timestamp and the 5 us limit.
        expected_end = falls[-1] + (run['elapsed_us']-rows[-1]['end_us']) * scale / 1e6
        terminal_error = abs(probe[-1]-expected_end)*1e6
        require(probe[-1] >= falls[-1] and terminal_error < 5, 'terminal probe release disagreement')
    review_presence(rows, rises, falls, channels['presence'], scale)
    return dict(run=run, rows=rows, changes=changes, rises=rises, falls=falls,
                alignment=alignment, scale=scale, probe_error=probe_error,
                terminal_error=terminal_error)


def review(raw, channels, analog, build_id=None, case='empty'):
    require(case in CASES, 'unknown fixture case')
    inserted = case != 'empty'
    timing = review_timing(raw, channels, build_id)
    run, rows, changes = (timing[k] for k in ('run', 'rows', 'changes'))
    rises, falls = timing['rises'], timing['falls']
    alignment = timing['alignment']
    probe_error, terminal_error = timing['probe_error'], timing['terminal_error']
    probe = channels['probe']['edges_s']
    sense = channels['sense']
    propagation = []
    if inserted:
        require(not sense['initial_high'] and not sense['edges_s'], 'inserted sense must stay low')
    else:
        require(not sense['initial_high'] and len(sense['edges_s']) == len(probe),
                'unexpected empty-jack sense edges')
        propagation = [(s-p)*1e6 for s, p in zip(sense['edges_s'], probe)]
        require(all(-1 < x < 20 for x in propagation), 'empty-jack propagation disagreement')
    def level(name, t):
        d = channels[name]
        return d['initial_high'] ^ bool(bisect_right(d['edges_s'], t) % 2)
    require(all(level('probe', t) == bool(r['probe']) for r, t in zip(rows, rises)), 'physical probe bit mismatch')
    if inserted:
        qualified = 511 if run['policy'] else 63
        require(len(changes) == 1 and changes[0]['seq'] == qualified and
                changes[0]['ready'] and changes[0]['patched'], 'inserted qualification disagreement')
        require(all(r['raw'] <= 16384 for r in rows), 'inserted ADC must stay low')
    else:
        require(all(level('sense', t) == bool(r['probe']) and level('sense', u) == bool(r['probe'])
                    for r, t, u in zip(rows, rises, falls)), 'empty-jack sense/sample mismatch')
        require(all(r['raw'] >= 49151 if r['probe'] else r['raw'] <= 16384 for r in rows),
                'ADC does not follow empty jack')
    require(run['adc_failures'] == 0 and rows[-1]['ready'] and bool(rows[-1]['patched']) == inserted,
            'failed ADC or final fixture state')
    invalid = sum(r['evidence'] == 2 for r in rows)
    if run['fault'] == 0:
        require(not run['missed'] and not invalid, 'baseline missed/invalid observations')
    elif run['fault'] == 1:
        require(not run['missed'] and invalid == sum(r['injected'] for r in rows), 'unexplained ADC-gap invalidity')
    else:
        first = next(i for i, r in enumerate(rows) if r['drive_us'] >= run['fault_end_us'])
        require(first > 0 and run['missed'] > 0, 'missing service-gap recovery')
        recovering = True
        for i, r in enumerate(rows):
            require(r['missed'] == (0 if i < first else run['missed']), 'extra missed slots outside stall')
            # A stall can return near a slot boundary. More than the first
            # conversion can then overrun its slot while cadence catches up.
            late = r['adc_end_us'] >= (r['slot'] + 1) * 500
            expected_invalid = i == first or (i > first and recovering and late)
            if i > first and not late: recovering = False
            require((r['evidence'] == 2) == expected_invalid, 'unexplained service-gap invalidity')
        require(not recovering, 'service cadence did not recover')
    rate, begin, end = analog['sample_rate_hz'], analog['begin_s'], analog['end_s']
    indices, volts = analog['plateau_indices'], analog['plateau_volts']
    require(math.isfinite(rate) and rate > 0 and math.isfinite(begin) and math.isfinite(end), 'invalid analog clock')
    require(begin < rises[0] < falls[-1] < end, 'incomplete analog coverage')
    require(len(indices) == len(volts) == len(rows), 'missing analog plateau samples')
    require(type(analog['samples']) is int and analog['samples'] > 0, 'missing analog length')
    lo, hi = analog['min_volts'], analog['max_volts']
    require(math.isfinite(lo) and math.isfinite(hi) and lo <= hi, 'invalid analog extrema')
    for idx, v, t, r in zip(indices, volts, falls, rows):
        require(type(idx) is int and 0 <= idx < analog['samples'] and math.isfinite(v) and lo <= v <= hi,
                'invalid analog plateau')
        require(-1e-12 <= t-(begin+idx/rate) < 1/rate+1e-12, 'analog plateau time mismatch')
        require(v >= 2.4 if r['probe'] and not inserted else v <= .85, 'analog/digital plateau disagreement')
    return dict(schema=1, status='pass', case=CASES[case], samples=len(rows), run=run,
                raw_sha256=hashlib.sha256(raw).hexdigest(), service_alignment=alignment,
                probe_edges=len(probe), probe_max_error_us=probe_error,
                terminal_release_error_us=terminal_error,
                propagation_min_us=min(propagation) if propagation else None,
                propagation_max_us=max(propagation) if propagation else None,
                invalid_observations=invalid, state_changes=changes,
                analog_min_volts=lo, analog_max_volts=hi,
                limitation='One stationary fixture, no audio load, insertion/withdrawal, calibrated voltage or absolute time qualification. Command-start qualification is not mechanical insertion latency. Analog plateau samples cannot exclude between-sample glitches.')


def _review_motion(raw, channels, analog, cycles, fault_transition):
    """Review complete insert/withdraw cycles without a powered external source.

    Analog extrema bracket each ADC aperture, including one native sample at
    either boundary. Crossing/ambiguous apertures are counted, never relabelled
    as stable voltage agreement. This does not time mechanical seating.
    """
    timing = review_timing(raw, channels)
    run, rows, changes = (timing[k] for k in ('run', 'rows', 'changes'))
    rises, falls = timing['rises'], timing['falls']
    require(type(cycles) is int and cycles > 0, 'invalid cycle count')
    require(run['adc_failures'] == 0, 'motion capture ADC failure')
    if fault_transition:
        require(run['fault'] in (1, 2) and 1 <= run.get('trigger', 0) <= 6,
                'transition fault plan required')
        require(0 <= run['fault_begin_us'] - run['fault_due_us'] < 500,
                'fault missed requested slot')
        if run['fault'] == 1:
            require(run['missed'] == 0, 'service loss during ADC-only gap')
        else:
            first = next(i for i, r in enumerate(rows) if r['drive_us'] >= run['fault_end_us'])
            require(first > 0 and run['missed'] > 0 and rows[first]['evidence'] == 2,
                    'missing service-gap invalidation')
            require(all(r['missed'] == (0 if i < first else run['missed']) for i, r in enumerate(rows)),
                    'extra missed slots outside transition fault')
            require(run['fault_end_us'] - run['fault_begin_us'] < run['fault_duration_us'] + 500,
                    'service pause exceeded requested duration tolerance')
    else:
        require(run['fault'] == 0 and run['missed'] == 0, 'motion capture acquisition failure')
    require(len(changes) == 1+2*cycles and changes[0]['seq'] == 63 and
            all(c['ready'] and c['patched'] == bool(i%2) for i,c in enumerate(changes)) and
            rows[-1]['ready'] and not rows[-1]['patched'], 'unexpected motion state sequence')
    ambiguous, transitions, invalid, stable = review_apertures(rows, rises, falls, channels, analog)
    # Independent known-level challenges before, between and after the actions.
    # Mid-dwell voltage checks do not imply the physical plug was fully seated.
    intervals = [(0,1000000,False), (run['elapsed_us']-1000000,run['elapsed_us'],False)]
    for i,c in enumerate(changes):
        stop = changes[i+1]['time_us'] if i+1<len(changes) else run['elapsed_us']
        require(stop-c['time_us'] > 2000000, 'insufficient dwell coverage')
        middle = (stop+c['time_us'])//2
        intervals.append((middle-500000,middle+500000,c['patched']))
    dwell = []
    for start,stop,patched in intervals:
        selected = [i for i,r in enumerate(rows) if start <= r['sample_us'] < stop]
        require(len(selected) >= 1999 and {rows[i]['probe'] for i in selected} == {0,1},
                'incomplete dwell challenge')
        require(all(stable[i] == (0 if patched else rows[i]['probe']) and
                    (rows[i]['raw'] <= 16384 if patched or not rows[i]['probe'] else rows[i]['raw'] >= 49151)
                    for i in selected), 'dwell voltage disagreement')
        dwell.append(dict(begin_us=start,end_us=stop,patched=patched,samples=len(selected)))
    return dict(schema=1,status='pass',case='insertion/withdrawal',
        samples=len(rows),cycles=cycles,run=run,state_changes=changes,
        service_alignment=timing['alignment'],probe_max_error_us=timing['probe_error'],
        terminal_release_error_us=timing['terminal_error'],
        sense_edges=len(channels['sense']['edges_s']),presence_edges=len(channels['presence']['edges_s']),
        invalid_observations=invalid,ambiguous_analog_apertures=ambiguous,
        digital_transition_apertures=transitions,dwell_checks=dwell,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        limitation='One fixture/cable and operator-declared motion; no mechanical seating timestamp or universal insertion latency. Aperture extrema do not resolve voltage inside a conversion or qualify glitches between observations. No external powered source or audio load.')


def review_motion(raw, channels, analog, cycles=3):
    return _review_motion(raw, channels, analog, cycles, fault_transition=False)


def review_fault_motion(raw, channels, analog, cycles=1):
    """Require a triggered protocol-3 fault and complete independent evidence."""
    return _review_motion(raw, channels, analog, cycles, fault_transition=True)


def review_apertures(rows, rises, falls, channels, analog):
    """Every independent voltage aperture; shared by motion and loaded runs."""
    rate, begin, end = (analog[k] for k in ('sample_rate_hz','begin_s','end_s'))
    total = analog['samples']
    require(all(math.isfinite(x) for x in (rate,begin,end)) and rate > 0 and
            type(total) is int and total > 0 and begin < rises[0] < falls[-1] < end,
            'incomplete analog coverage')
    require(analog['representation'] == 'Native extrema over each service aperture, including boundary samples',
            'unknown analog representation')
    a, b = analog['first_indices'], analog['last_indices']
    low, high = analog['minimum_volts'], analog['maximum_volts']
    require(all(len(x) == len(rows) for x in (a,b,low,high)), 'missing aperture evidence')
    sense, probe = channels['sense'], channels['probe']
    require(not sense['initial_high'] and len(sense['edges_s']) % 2 == 0 and
            sense['edges_s'] and probe['edges_s'][0]-1e-6 <= sense['edges_s'][0] and
            sense['edges_s'][-1] <= probe['edges_s'][-1]+20e-6, 'sense idle disagreement')
    ambiguous = transitions = invalid = 0
    stable = []
    for i,(r,t,u) in enumerate(zip(rows,rises,falls)):
        require(type(a[i]) is int and type(b[i]) is int and 0 <= a[i] < b[i] < total and
                a[i] == math.floor((t-begin)*rate) and b[i] == math.ceil((u-begin)*rate),
                'analog aperture timing disagreement')
        require(math.isfinite(low[i]) and math.isfinite(high[i]) and low[i] <= high[i],
                'invalid analog aperture bounds')
        is_low, is_high = high[i] <= .85, low[i] >= 2.4
        require(not is_low or r['raw'] <= 16384, 'stable low analog/ADC disagreement')
        require(not is_high or r['raw'] >= 49151, 'stable high analog/ADC disagreement')
        j, k = bisect_right(sense['edges_s'],t), bisect_right(sense['edges_s'],u)
        level = sense['initial_high'] ^ bool(j%2)
        if j == k:
            require(not (level and r['raw'] <= 16384) and not (not level and r['raw'] >= 49151),
                    'stable digital/ADC disagreement')
        else: transitions += 1
        require((probe['initial_high'] ^ bool(bisect_right(probe['edges_s'],t)%2)) == bool(r['probe']),
                'physical probe bit mismatch')
        ambiguous += not (is_low or is_high)
        invalid += r['evidence'] == 2
        stable.append(0 if is_low else 1 if is_high else -1)
    return ambiguous, transitions, invalid, stable
