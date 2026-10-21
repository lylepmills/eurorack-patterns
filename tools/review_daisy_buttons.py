#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Offline physical review of a complete two-Daisy button campaign case."""
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import button_campaign
import capture
import load_capture
import pulse_generator
from capture import require
from daisy_scope import match_service


def review(directory, channels):
    """channels maps button/service/gesture to (initial_high, transitions_s)."""
    meta = json.loads((directory/'campaign.json').read_text())
    raw = (directory/'fixture/raw.txt').read_bytes()
    summary, controls, _ = load_capture.parse(raw, meta['fixture_build']['build_id'])
    writer = json.loads((directory/'fixture/metadata.json').read_text())['writer']
    load_capture.assess(summary, False, writer)
    _, run, rows = capture.parse(controls)
    behavior = button_campaign.review_controls(summary, rows, meta['case'])
    gen_raw = (directory/'generator/raw.txt').read_bytes()
    source = pulse_generator.parse(gen_raw, meta['generator_build']['build_id'], meta['times_us'])
    button_high, buttons = channels['button']; buttons = list(map(float, buttons))
    stimulus = pulse_generator.inspect_physical(source, button_high, buttons)
    require(stimulus['status'] == 'pass', 'physical stimulus timing failed')
    rises, falls, alignment = match_service(rows, channels['service'][1], channels['service'][0])
    require(rises[0] < buttons[0] < buttons[-1] < falls[-1], 'stimulus outside complete service window')
    disagreements = [i for i, (r, t) in enumerate(zip(rows, rises))
        if r['pressed'] != (bisect_right(buttons, t) % 2)]
    require(not disagreements, 'physical/button observation mismatch: '+str(disagreements))
    initial_action, actions = channels['gesture']; actions = list(map(float, actions))
    require(all(math.isfinite(t) for t in actions) and all(a < b for a,b in zip(actions,actions[1:])),
            'invalid action timeline')
    inside = [t for t in actions if rises[0] <= t <= falls[-1]]
    outside = [t for t in actions if not rises[0] <= t <= falls[-1]]
    # Collect explicitly clears a previous run's high action marker. Preserve
    # the one allowed setup fall; reject other unaccounted transitions.
    require((not initial_action and not outside) or
            (initial_action and len(outside) == 1 and 0 < rises[0]-outside[0] < .001),
            'unexpected action edges outside acquisition')
    events = [r for r in rows if r['gesture']]
    require(len(inside) == len(events) and
            all(rises[r['seq']] <= t <= falls[r['seq']] for r, t in zip(events, inside)),
            'physical action/service mismatch')
    pair_indices = [0,1,2] if meta['case'] == 'baseline' else [0,1] if meta['case'] == 'press-adc-gap' else [1]
    timed = behavior.get('boundary')
    if timed:
        require(meta.get('fault_delay_us') == summary['configuration']['fault_delay_us'],
                'campaign/receiver fault delay mismatch')
        pair_indices = [e['pair'] for e in timed['expected_events']]
    latencies = []
    for r, t, pair in zip(events, inside, pair_indices):
        press, release = buttons[2*pair:2*pair+2]
        latency = (t-(release if r['gesture'] == 1 else press))*1e6
        if timed and r['gesture'] == 2:
            # The raw-dwell oracle pins the exact service index. For a pending
            # press requalified after a gap, time from the physical press alone
            # is not the hold deadline. All service pulses remain independently
            # matched with the same clock/width limits above.
            q = timed['qualified_press_us'][pair]
            delta = (r['time_us']//1000-q//1000)*1000
            require(600000 <= delta < 602000 and press < t < release,
                    'timed physical hold deadline/placement')
        else:
            require((5000 < latency < 25000) if r['gesture'] == 1 else
                    (605000 < latency < 625000 and t < release), 'physical gesture deadline/placement')
        latencies.append(latency)
    scale = 1 + alignment['clock_scale_ppm']/1e6
    phase = []
    for edge in buttons:
        previous = bisect_right(rises, edge)-1
        require(0 <= previous < len(rows)-1, 'button outside service coverage')
        require(rows[previous+1]['time_us']-rows[previous]['time_us'] < 2000,
                'input edge occurred inside service gap; phase needs separate review')
        # Interpolate from the nearest observed service; this is a measured
        # phase estimate, not the requested generator offset or host timing.
        estimated = rows[previous]['time_us']+(edge-rises[previous])*1e6/scale
        phase.append(estimated % 1000)
    return dict(schema=1, status='pass', case=meta['case'],
        fixture_raw_sha256=hashlib.sha256(raw).hexdigest(), generator_raw_sha256=hashlib.sha256(gen_raw).hexdigest(),
        samples=len(rows), service_alignment=alignment, source=stimulus,
        sampled_button_disagreements=disagreements,
        button_edges_s=buttons, service_first_s=rises[0], service_last_s=falls[-1],
        action_edges_s=inside, setup_action_edges_s=outside,
        action_latencies_us=latencies, measured_input_phase_us=phase,
        phase_uncertainty_note='Service clock alignment residual plus marker/read skew; no exact phase-bin qualification.',
        software_behavior=behavior, fault=summary.get('fault'),
        limitation=('Configurable receiver delay, measured service/edge phase, clean generated edges, one fixture. '
                    'Not exhaustive phase coverage or switch-bounce qualification.' if timed else
                    'Fixed receiver fault delays, clean generated edges, one fixture. Not a programmable fault-boundary matrix or switch-bounce qualification.'))
