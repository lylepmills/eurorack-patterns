#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Separate scheduling in measured clock cycles from external clock stability.

Only explicit M-mode records enter this path. Physical voltage apertures and
generator bounds stay on the original scope timeline. No fitted local rate,
discarded clock periods, extrapolation, or old-record reclassification.
"""
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import jack_capture
from capture import require
from daisy_scope import inspect_service
from inspect_daisy_clock import inspect_clock, clock_coordinates, service_cycles
from review_daisy_jacks import review_presence


def scheduling(rows, service, clock, nominal_hz=16000000/15):
    """All full hardware periods plus fixed-offset 5/5/3 us service checks."""
    wire = [dict(time_us=r['sample_us'], work_us=r['end_us']-r['sample_us']) for r in rows]
    rises, falls, external = inspect_service(wire, service['edges_s'], service['initial_high'],
                                            local_seconds=1)
    hardware = inspect_clock(clock['edges_s'], clock['initial_high'],
                             [(rises[0], falls[-1])], nominal_hz)
    cr = clock['edges_s'][::2]
    mapped = clock_coordinates(service['edges_s'], cr, nominal_hz)
    cycle = service_cycles(rises, [r['sample_us'] for r in rows], cr, nominal_hz)
    width = max(abs(b-a-r['work_us']) for a,b,r in zip(mapped[::2],mapped[1::2],wire))
    require(cycle['max_residual_us'] < 5, 'clock-referenced service offset/drift exceeds 5us')
    require(cycle['max_interval_error_us'] < 5, 'clock-referenced service interval exceeds 5us')
    require(width < 3, 'clock-referenced service width exceeds 3us')
    report = dict(status='pass', basis='Counted HSE/15 cycles at fixed nominal frequency; one constant offset; no fitted rate',
                  samples=len(rows), offset_us=cycle['offset_us'],
                  max_residual_us=cycle['max_residual_us'],
                  max_interval_error_us=cycle['max_interval_error_us'],
                  max_work_width_error_us=width,
                  limits_us=dict(offset=5, interval=5, work_width=3))
    return rises, falls, mapped, cr, hardware, report, external


def review_timing(raw, channels, build_id=None):
    info, run, rows, changes = jack_capture.parse(raw, build_id, clock_reference=True)
    require(set(channels) == {'sense','service','presence','probe','clock','audio'},
            'missing/unknown clock-reference channel')
    for name, d in channels.items():
        require(type(d['initial_high']) is bool, 'invalid initial state')
        times = d['edges_s']
        require(all(math.isfinite(t) for t in times) and
                all(a < b for a,b in zip(times,times[1:])), 'invalid '+name+' timeline')
        require(math.isfinite(d['begin_s']) and math.isfinite(d['end_s']) and
                d['begin_s'] < d['end_s'], 'invalid channel duration')
        require(not times or d['begin_s'] < times[0] <= times[-1] < d['end_s'],
                'missing edge margins')
    rises, falls, mapped, cr, hardware, report, external = scheduling(
        rows, channels['service'], channels['clock'])
    require(all(d['begin_s'] < rises[0] < falls[-1] < d['end_s'] for d in channels.values()),
            'missing full observation coverage')
    hz = hardware['nominal_hz']
    mapped_channels = {}
    for name in ('presence','probe','audio'):
        d = channels[name]
        mapped_channels[name] = dict(initial_high=d['initial_high'], edges_s=[
            t/1e6 for t in clock_coordinates(d['edges_s'], cr, hz)])
    mr, mf = [t/1e6 for t in mapped[::2]], [t/1e6 for t in mapped[1::2]]
    # M campaigns start and finish empty. A retained-high pre-clock reset is
    # outside measured clock coverage and must not be silently extrapolated.
    require(not channels['presence']['initial_high'], 'clock-reference fixture must start empty')
    require(not channels['probe']['initial_high'], 'probe must start low')
    expected, previous = [], False
    for r,t in zip(rows,mr):
        if bool(r['probe']) != previous:
            expected.append(t-(r['sample_us']-r['drive_us'])/1e6)
        previous = bool(r['probe'])
    probe = mapped_channels['probe']['edges_s']
    require(len(probe) == len(expected)+int(previous), 'unexpected probe edge count')
    error = max(abs(a-b)*1e6 for a,b in zip(probe,expected))
    require(error < 5, 'probe drive timing disagreement')
    terminal = None
    if previous:
        end = mf[-1]+(run['elapsed_us']-rows[-1]['end_us'])/1e6
        terminal = abs(probe[-1]-end)*1e6
        require(probe[-1] >= mf[-1] and terminal < 5, 'terminal probe release disagreement')
    review_presence(rows,mr,mf,mapped_channels['presence'],1)
    return dict(run=run,rows=rows,changes=changes,rises=rises,falls=falls,
                alignment=report,scale=1,probe_error=error,terminal_error=terminal,
                scheduling=report,clock_stability=external,hardware_clock=hardware,
                audio_timing=dict(run=run,rows=rows,rises=mr,scale=1),
                audio_channel=mapped_channels['audio'])
