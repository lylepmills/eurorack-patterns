#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Inspect a finite hardware-clock waveform. No clock or behavior qualification.

K-mode routes HSE/15 through MCO2 (PC9), independently of GPIO writes/IRQs.
Keep whole-window service acceptance unchanged. Frequency estimates compare
oscillators; none is asserted to be a calibrated absolute time reference.
"""
import argparse
from bisect import bisect_left, bisect_right
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import jack_capture
from inspect_daisy_timing import read_digital
from daisy_scope import inspect_service
from review_daisy_dsp import verify


def inspect_clock(edges, initial_high, ranges, nominal_hz=16000000/15):
    if (initial_high or len(edges) < 8 or len(edges) % 2 or
            not math.isfinite(nominal_hz) or nominal_hz <= 0 or
            any(not math.isfinite(t) for t in edges) or
            any(a >= b for a,b in zip(edges,edges[1:]))):
        raise ValueError('Incomplete or unordered clock waveform')
    rises = edges[::2]
    period = 1/nominal_hz
    # Opening a mux onto an already-high clock can create one partial first
    # pulse/period. Report it explicitly; check every subsequent full period.
    # Closing onto GPIO-low can truncate only the last high half-pulse.
    shortest = min(rises[i]-rises[i-1] for i in range(2,len(rises)))
    longest = max(rises[i]-rises[i-1] for i in range(2,len(rises)))
    min_width = min(edges[2*i+1]-edges[2*i] for i in range(1,len(rises)-1))
    max_width = max(edges[2*i+1]-edges[2*i] for i in range(1,len(rises)-1))
    if not (0 < rises[1]-rises[0] < 1.25*period and
            .75*period < shortest <= longest < 1.25*period and
            .2*period < min_width <= max_width < .8*period):
        raise ValueError('Clock waveform has extra/missing edges or invalid duty')
    result = []
    for begin,end in ranges:
        if not (math.isfinite(begin) and math.isfinite(end) and
                rises[1] <= begin < end <= rises[-1]):
            raise ValueError('Clock does not cover the requested interval')
        first,last = bisect_left(rises,begin),bisect_right(rises,end)-1
        if last-first < 2: raise ValueError('Insufficient clock cycles')
        scale = (rises[last]-rises[first])*nominal_hz/(last-first)
        result.append(dict(begin_s=begin,end_s=end,first_cycle=first,last_cycle=last,
            clock_scale_ppm=(scale-1)*1e6))
    return dict(status='diagnostic only',cycles=len(rises),nominal_hz=nominal_hz,
        minimum_period_s=shortest,maximum_period_s=longest,
        first_gated_period_s=rises[1]-rises[0],
        boundary_high_widths_s=[edges[1]-edges[0],edges[-1]-edges[-2]],blocks=result,
        limitation='Every interior full clock period checked; initial gated period and boundary half-pulse widths reported separately. Relative clocks only; no DUT acceptance override.')


def clock_coordinates(edges, clock_rises, nominal_hz):
    """Map finite observations inside full, previously validated clock periods."""
    if (not math.isfinite(nominal_hz) or nominal_hz <= 0 or
            any(not math.isfinite(t) for t in edges) or
            any(a >= b for a, b in zip(edges, edges[1:]))):
        raise ValueError('Invalid ordered clock observations')
    result = []
    for edge in edges:
        cycle = bisect_right(clock_rises, edge) - 1
        if not 1 <= cycle < len(clock_rises) - 1:
            raise ValueError('Observation lacks full clock-cycle coverage')
        begin, end = clock_rises[cycle:cycle+2]
        result.append((cycle + (edge-begin)/(end-begin)) * 1e6 / nominal_hz)
    return result


def service_cycles(service_edges, timestamps_us, clock_rises, nominal_hz):
    """Compare timestamps to validated full clock cycles, with offset only.

    Call after inspect_clock has checked the complete waveform. Interpolation
    uses the two adjacent physical clock edges, never a fitted local rate.
    A constant offset accounts for unrelated acquisition/clock starting phases.
    No slope is fitted: timestamp drift and delayed service edges remain visible.
    """
    if (len(service_edges) != len(timestamps_us) or len(service_edges) < 2 or
            not math.isfinite(nominal_hz) or nominal_hz <= 0 or
            any(not math.isfinite(t) for t in service_edges) or
            any(not math.isfinite(t) for t in timestamps_us) or
            any(a >= b for a, b in zip(service_edges, service_edges[1:])) or
            any(a >= b for a, b in zip(timestamps_us, timestamps_us[1:]))):
        raise ValueError('Invalid paired service observations')
    coordinates = clock_coordinates(service_edges, clock_rises, nominal_hz)
    offsets = [t-stamp for t, stamp in zip(coordinates, timestamps_us)]
    offset = math.fsum(offsets) / len(offsets)
    return dict(status='diagnostic only', samples=len(offsets),
        offset_us=offset,
        max_residual_us=max(abs(t-offset) for t in offsets),
        peak_to_peak_us=max(offsets)-min(offsets),
        max_interval_error_us=max(abs(b-a) for a,b in zip(offsets,offsets[1:])),
        limitation='Fixed nominal clock-cycle units and one constant offset; no fitted rate. Does not establish absolute clock accuracy, audio timing or behavior qualification.')


def audio_cycles(run, rows, service_edges, initial_high, audio_edges, clock_rises, nominal_hz):
    """Apply unchanged callback checks in already validated HSE-cycle units."""
    from review_daisy_jack_load import review_audio
    mapped = dict(initial_high=initial_high, edges_s=[
        t/1e6 for t in clock_coordinates(audio_edges,clock_rises,nominal_hz)])
    timing = dict(run=run, rows=rows, scale=1,
                  rises=[t/1e6 for t in clock_coordinates(service_edges,clock_rises,nominal_hz)])
    return review_audio(timing, mapped)


def inspect(raw, service_data, clock_data, reference, audio_data=None):
    info,run,rows,_=jack_capture.parse(raw,clock_diagnostic=True)
    initial,service=read_digital(service_data)
    rises,_,timing=inspect_service([dict(time_us=r['sample_us'],work_us=r['end_us']-r['sample_us'])
        for r in rows],service,initial,local_seconds=1)
    ci,ce=read_digital(clock_data)
    ranges=[]
    # One-second windows follow the actual service edges. Each comparison uses
    # the same two physical boundaries, so startup/USB offset is irrelevant.
    groups={}
    for i,r in enumerate(rows):groups.setdefault(r['sample_us']//1000000,[]).append(i)
    for ids in groups.values():
        if len(ids)<2:raise ValueError('Incomplete diagnostic second')
        ranges.append((rises[ids[0]],rises[ids[-1]]))
    clock=inspect_clock(ce,ci,ranges)
    for block,ids in zip(clock['blocks'],groups.values()):
        a,b=ids[0],ids[-1]
        block.update(first_seq=a,last_seq=b,service_clock_scale_ppm=
            ((rises[b]-rises[a])*1e6/(rows[b]['sample_us']-rows[a]['sample_us'])-1)*1e6)
    result = dict(schema=1,status='diagnostic only; normal load campaign still requires its original review',
        raw_sha256=hashlib.sha256(raw).hexdigest(),service_sha256=hashlib.sha256(service_data).hexdigest(),
        clock_sha256=hashlib.sha256(clock_data).hexdigest(),build_id=info['build_id'],
        run=run,service_timing=timing,hardware_clock=clock,
        service_clock_cycles=service_cycles(rises, [r['sample_us'] for r in rows],
                                           ce[::2], clock['nominal_hz']),
        dsp_dma=verify(run,reference))
    if audio_data is not None:
        ai, ae = read_digital(audio_data)
        result['audio_in_clock_cycles'] = audio_cycles(
            run, rows, rises, ai, ae, ce[::2], clock['nominal_hz'])
        result['audio_sha256'] = hashlib.sha256(audio_data).hexdigest()
        result['audio_limitation'] = 'Callback checks in counted HSE clock units only; no jack behavior or absolute clock qualification.'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('raw','service','clock','dsp-reference','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--audio', type=Path, help='Optional separate diagnostic audio marker on D5')
    a=p.parse_args()
    r=inspect(a.raw.read_bytes(),a.service.read_bytes(),a.clock.read_bytes(),a.dsp_reference,
              a.audio.read_bytes() if a.audio else None)
    with a.out.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print('Diagnostic saved; service timing:',r['service_timing']['status'])

if __name__=='__main__':main()
