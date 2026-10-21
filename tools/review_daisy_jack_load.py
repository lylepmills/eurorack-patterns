#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Independent scheduling, voltage and recovery evidence under real SAI IRQ load."""
import hashlib
from bisect import bisect_right
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'examples/daisy'))
from capture import require
import pulse_generator
from review_daisy_jacks import review_timing, review_apertures


def source_plateaus(timing, channels, analog):
    """Bound the electrical source separately from ADC-conversion evidence.

    Keep every conservative full-aperture ambiguity. Three interior native
    samples plus a stable digital level locate the external clamp, even when
    the next probe bit falls in a full aperture's boundary sample.
    """
    p = analog['source_plateaus']
    require(p['representation'] == 'Three native samples centered at or before each service midpoint; source timing only',
            'unknown source plateau representation')
    mid, low, high = (p[k] for k in ('center_indices','minimum_volts','maximum_volts'))
    rows, rises, falls = (timing[k] for k in ('rows','rises','falls'))
    require(all(len(x) == len(rows) for x in (mid,low,high)), 'missing source plateau evidence')
    rate, begin = analog['sample_rate_hz'], analog['begin_s']
    groups = []
    for i,(r,t,u) in enumerate(zip(rows,rises,falls)):
        require(type(mid[i]) is int and mid[i] == math.floor(((t+u)/2-begin)*rate) and
                analog['first_indices'][i] < mid[i]-1 and mid[i]+1 < analog['last_indices'][i],
                'source plateau timing disagreement')
        require(math.isfinite(low[i]) and math.isfinite(high[i]) and low[i] <= high[i] and
                analog['minimum_volts'][i] <= low[i] <= high[i] <= analog['maximum_volts'][i],
                'source plateau outside full aperture bounds')
        # Include one native sample interval on each side in the time bracket.
        a,b = begin+(mid[i]-2)/rate, begin+(mid[i]+2)/rate
        stable = 0 if high[i] <= .85 else 1 if low[i] >= 2.4 else -1
        sense = channels['sense']; edges = sense['edges_s']
        j,k = bisect_right(edges,a),bisect_right(edges,b)
        if stable < 0 or j != k: continue
        require(stable == int(sense['initial_high'] ^ bool(j%2)), 'source plateau analog/digital disagreement')
        if not r['probe']: continue
        clamped = stable == 0
        if not groups or groups[-1][0] != clamped: groups.append((clamped,[]))
        groups[-1][1].append((i,a,b))
    require([g[0] for g in groups] == [False,True,False], 'unexpected electrical clamp sequence')
    before,during,after = (g[1] for g in groups)
    return during[0][0],after[0][0], [before[-1][1],during[0][2]], [during[-1][1],after[0][2]]


def review_audio(timing, channel):
    load = timing['run']['audio']
    require(not channel['initial_high'] and len(channel['edges_s']) % 2 == 0,
            'incomplete audio callback pulses')
    starts, stops = channel['edges_s'][::2], channel['edges_s'][1::2]
    require(len(starts) == load['callbacks'], 'audio callback count disagrees with scope')
    if not load['block']:
        return dict(callbacks=0, independent_marker='verified idle')
    scale = timing['scale']
    origin = timing['rises'][0] - timing['rows'][0]['sample_us'] * scale / 1e6
    require(origin-5e-6 <= starts[0] and stops[-1] <= origin + load['end_us']*scale/1e6+5e-6,
            'audio pulse outside measured window')
    widths = [(b-a)*1e6/scale for a,b in zip(starts, stops)]
    intervals = [(b-a)*1e6/scale for a,b in zip(starts, starts[1:])]
    hz = load['timer_hz']
    require(abs(max(widths)-load['max_work_ticks']*1e6/hz) < 5,
            'audio callback work disagrees with scope')
    require(abs(max(intervals)-load['max_interval_ticks']*1e6/hz) < 5,
            'audio callback cadence disagrees with scope')
    expected = load['end_us']*48000/(load['block']*1e6)
    require(abs(len(starts)-expected) <= max(3, expected*.002), 'missing audio callback coverage')
    require(not any(load[k] for k in ('over_budget','late_intervals','bad_size')),
            'audio callback deadline/size failure')
    require(min(widths) >= load['period_ticks']*load['permille']/1000*1e6/hz - 5,
            'audio padding absent from independent waveform')
    return dict(callbacks=len(starts), independent_marker='verified every callback',
        minimum_work_us=min(widths), maximum_work_us=max(widths),
        maximum_interval_us=max(intervals), measured_end_us=load['end_us'])


def review_finish(raw, channels, analog, dsp_reference=None):
    """Empty-jack operator finish, including conversion drain and audio stop."""
    timing = review_timing(raw, channels)
    run, rows, changes = (timing[k] for k in ('run','rows','changes'))
    require('acquisition' in run and run['finish_reason'] == 'operator' and not run['fault'],
            'scheduled operator finish required')
    require(run['acquisition_limit_us'] < run['duration_ms']*1000, 'finish did not shorten capture')
    ambiguous, crossings, invalid, stable = review_apertures(rows,timing['rises'],timing['falls'],channels,analog)
    require(not run['missed'] and not run['adc_failures'] and not invalid and not ambiguous and not crossings,
            'incomplete/invalid finish acquisition')
    require(all(s == r['probe'] and r['evidence'] == 0 for s,r in zip(stable,rows)) and
            len(changes) == 1 and changes[0]['seq'] == 63 and not changes[0]['patched'],
            'finish fixture was not continuously empty')
    audio = review_audio(timing,channels['audio'])
    from review_daisy_dsp import verify
    workload = verify(run, dsp_reference)
    require(run['elapsed_us'] - run['acquisition_limit_us'] < 50,
            'acquisition did not stop at the published boundary')
    result = dict(schema=1,status='pass',case='automated empty-jack finish',run=run,samples=len(rows),
        audio=audio,service_alignment=timing['alignment'],probe_max_error_us=timing['probe_error'],
        terminal_release_error_us=timing['terminal_error'],raw_sha256=hashlib.sha256(raw).hexdigest(),
        limitation='One stationary empty-jack fixture and software-requested finish; no insertion or production-input qualification.')
    if workload is not None: result['workload'] = workload
    return result


def review(raw, channels, analog, generator_raw, generator_build, times, require_response=False, dsp_reference=None,
           *, clock_reference=False):
    source = pulse_generator.parse(generator_raw, generator_build, times)
    require(len(times) == 2, 'one complete electrical clamp required')
    if clock_reference:
        from review_daisy_clock_reference import review_timing as clock_timing
        timing = clock_timing(raw, channels)
    else:
        timing = review_timing(raw, channels)
    run, rows, changes = (timing[k] for k in ('run','rows','changes'))
    require('audio' in run and run['adc_failures'] == 0, 'protocol 4 and completed conversions required')
    audio = review_audio(timing.get('audio_timing', timing),
                         timing.get('audio_channel', channels['audio']))
    from review_daisy_dsp import verify
    workload = verify(run, dsp_reference)
    if run['audio']['block']:
        target = min(run['audio']['off_ms']*1000, run['acquisition_limit_us'])
        tolerance = 1000 + 2*run['audio']['block']*1e6/48000 + (run['fault_duration_us'] if run['fault']==2 else 0)
        require(target <= run['audio']['end_us'] <= target+tolerance, 'audio stop missed requested window')
    ambiguous, crossings, invalid, stable = review_apertures(rows, timing['rises'], timing['falls'], channels, analog)
    if 'acquisition' in run:
        acq, hz = run['acquisition'], run['audio']['timer_hz']
        require(abs(acq['timer_irqs'] - run['elapsed_us']/50) <= 2,
                'missing acquisition timer interrupts')
        require(0 < acq['max_timer_ticks'] < hz/20000 and
                0 < acq['max_adc_ticks'] < hz/20000, 'acquisition ISR exceeded 50us budget')
        work = acq['work_ticks_low'] + (acq['work_ticks_high'] << 32)
        require(max(acq['max_timer_ticks'], acq['max_adc_ticks']) <= work < run['elapsed_us']*hz/1e7,
                'acquisition ISR work outside bounded 10 percent budget')
        require(not any(r['adc_end_us'] >= (r['slot']+1)*500 for r in rows),
                'scheduled ADC missed slot deadline')
        expected_missed = run['fault_duration_us']//500 if run['fault'] == 2 else 0
        require(run['missed'] == expected_missed, 'unexpected scheduled acquisition loss')
        # Invalid voltage around a physical edge remains invalid. Do not erase
        # ambiguous ADC apertures to make a scheduling result look cleaner.
        require_response = True
    during, after, onset, release = source_plateaus(timing, channels, analog)
    require(all(0 <= b-a < .01 for a,b in (onset,release)), 'unbounded electrical transition')
    bounds = [release[0]-onset[1], release[1]-onset[0]]
    edges = source['edges']
    gen_bounds = [(edges[1]['before_us']-edges[0]['after_us'])/1e6,
                  (edges[1]['after_us']-edges[0]['before_us'])/1e6]
    require(bounds[0] <= gen_bounds[1]*1.001+5e-6 and bounds[1] >= gen_bounds[0]*.999-5e-6,
            'generator/physical clamp duration disagreement')
    # A starved qualification is a measured scheduling limit, not a responsive
    # pass. Keep it explicit, while still rejecting invented/extra transitions.
    states = [bool(c['patched']) for c in changes]
    require(states in ([False], [False,True,False], [True,False]), 'unexpected loaded state sequence')
    responsive = states in ([False,True,False], [True,False])
    if require_response: require(responsive, 'required jack qualification did not complete')
    if responsive:
        inserted, removed = (c['seq'] for c in changes[-2:])
        require(during <= inserted < after and removed >= after-1,
                'qualified state contradicts physical clamp phase')
        if 'acquisition' in run and run['audio']['block']:
            require(changes[-2]['time_us'] < run['audio']['end_us'],
                    'qualification waited for audio to stop')
    # Full final unloaded second must recover cadence, validity and empty state.
    tail = [i for i,r in enumerate(rows) if r['drive_us'] >= run['acquisition_limit_us']-1000000]
    require(len(tail) >= 1999 and all(rows[i]['evidence'] == 0 and stable[i] == rows[i]['probe']
            for i in tail) and rows[-1]['ready'] and not rows[-1]['patched'], 'unloaded tail did not recover')
    if run['audio']['block']:
        require(run['audio']['end_us'] < rows[tail[0]]['drive_us'], 'audio still active in recovery tail')
    result = dict(schema=1, status='pass', case='automated jack audio load', samples=len(rows), run=run,
        qualification='responsive' if responsive else 'starved under load; recovered empty',
        first_ready_us=changes[0]['time_us'],
        patched_while_audio_active=bool(responsive and changes[-2]['time_us'] < run['audio']['end_us']),
        late_adc_observations=sum(r['adc_end_us'] >= (r['slot']+1)*500 for r in rows),
        state_changes=changes, audio=audio, generator=source, service_alignment=timing['alignment'],
        probe_max_error_us=timing['probe_error'], terminal_release_error_us=timing['terminal_error'],
        clamp_onset_bounds_s=onset, clamp_release_bounds_s=release,
        source_timing_evidence='Three interior native analog samples per service pulse, checked against digital sense; full ADC aperture review unchanged',
        physical_clamp_duration_bounds_s=bounds, invalid_observations=invalid,
        ambiguous_analog_apertures=ambiguous, digital_transition_apertures=crossings,
        recovery_tail_samples=len(tail), raw_sha256=hashlib.sha256(raw).hexdigest(),
        limitation='One passive electrical-clamp fixture; silent SAI DMA callbacks with measured busy padding. Not DSP/audio quality, mechanical motion, calibrated absolute latency, arbitrary IRQ priorities or protected-input qualification.')
    if workload is not None:
        result['workload'] = workload
        result['limitation'] = ('One passive electrical-clamp fixture; deterministic FIR/delay processing and optional '
            'SDRAM DMA with silent codec outputs. Not codec audio quality, arbitrary DSP/DMA traffic, '
            'mechanical motion, calibrated absolute latency or protected-input qualification.')
    if clock_reference:
        result.update(status='scheduling and behavior pass; clock stability reported separately',
                      scheduling=timing['scheduling'], clock_stability=timing['clock_stability'],
                      hardware_clock=timing['hardware_clock'])
        result['limitation'] += (' Scheduling uses counted HSE cycles with a fixed nominal conversion and constant offset only. '
            'External clock-stability failures are retained; this is not an overall clock-accuracy pass.')
        if workload is not None:
            workload['limitation'] = ('DSP signature reuses the tested integer kernel; DMA counters and full-word checks '
                'are device-reported. D5 independently checks audio callbacks in counted HSE units, not the DMA2 bus '
                'or codec audio fidelity.')
    return result
