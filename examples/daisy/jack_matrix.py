#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Run a finite jack fault matrix using an identified independent open-drain MCU.

Uses installed firmware. Never flashes, discovers serial ports, resumes over
old evidence, or continues after a failed case. See docs/validation.md wiring.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import jack_capture
import jack_session
import pulse_generator
from capture import require

TIMES_US = [3000000, 6500000]
SECONDS = 10


def cases():
    baseline = dict(fault=0, trigger=0, fault_delay_slots=0, fault_us=25000, policy=1)
    result = [dict(name='baseline-before', **baseline)]
    for trigger in range(1, 7):
        for fault in (1, 2):
            for duration in (500, 25000, 100000):
                for delay in (0, 1, 64):
                    result.append(dict(name=f't{trigger}-f{fault}-us{duration:06d}-d{delay:02d}',
                        fault=fault, trigger=trigger, fault_delay_slots=delay,
                        fault_us=duration, policy=1))
    result.append(dict(name='baseline-after', **baseline))
    return result


def record_case(a, case, manager, generator_manifest, *, times=TIMES_US, seconds=SECONDS, reviewer=None):
    import serial
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
    from inspect_daisy_jack_scope import extract
    from review_daisy_jack_matrix import review
    if reviewer is None: reviewer = review

    out = a.out / case['name']
    require(not out.exists(), 'case output already exists')
    # jack_session creates out. Keep the generator stream in the already-created
    # campaign directory until acquisition begins; retain it on every failure.
    gen_raw = a.out / (case['name'] + '-generator.txt')
    port = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=2)
    port.dtr = False; port.rts = False
    if sys.platform != 'win32': port.exclusive = True
    port.port = a.generator_port
    args = SimpleNamespace(**{k:v for k,v in case.items() if k != 'name'},
        port=a.port, manifest=a.manifest, scope_id=a.scope_id, out=out,
        max_seconds=seconds, finish_after=None, server_port=a.server_port,
        clock_reference=getattr(a, 'clock_reference', False),
        notes=json.dumps(dict(case='automated-electrical-clamp',
            fixture='Empty switched jack; independent open-drain output on tip/sense; 1k probe series; 100k sense pulldown; no cable or external powered module.',
            generator_times_us=times, mechanical_motion=False)))
    with port, gen_raw.open('xb') as raw:
        gen = pulse_generator.Generator(port, raw, generator_manifest)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = None
            def started():
                nonlocal pending
                gen.start()
                pending = pool.submit(gen.finish)
            try:
                gen.prepare(times)
                jack_session.run(args, manager=manager, on_started=started)
                require(pending is not None, 'fixture never started generator')
                pending.result(timeout=10)
            except BaseException:
                if gen.identified:
                    try: gen.abort()
                    except Exception: pass
                raise
    raw, channels, analog = (extract(out, clock_reference=True)
                            if args.clock_reference else extract(out))
    result = reviewer(raw, channels, analog, gen_raw.read_bytes(), generator_manifest['build_id'], times)
    actual = result['run']
    require(all(actual[k] == case[k] for k in ('fault','trigger','fault_delay_slots'))
            and actual['fault_duration_us'] == case['fault_us'],
            'recorded fault plan differs from matrix')
    jack_capture.publish_json(out / 'physical-review.json', result)
    return dict(name=case['name'], status=result['status'], samples=result['samples'],
                raw_sha256=result['raw_sha256'], generator_sha256=result['generator']['raw_sha256'],
                run=result['run'], **({'scheduling': result['scheduling'],
                    'clock_stability': result['clock_stability']} if args.clock_reference else {}))


def run(a):
    require(a.port != a.generator_port, 'fixture and generator ports must differ')
    require(not a.out.exists(), 'campaign output already exists; never overwrite evidence')
    gen = pulse_generator.load_manifest(a.generator_manifest)
    fixture = json.loads(a.manifest.read_text())
    require(fixture.get('kind') == 'eurorack-patterns-daisy-jack-bench' and fixture.get('protocol') == 3,
            'protocol-3 jack firmware required')
    selected = [c for c in cases() if a.case == 'all' or c['name'] == a.case
                or (a.case == 'faults' and c['fault'])]
    require(selected, 'unknown matrix selection')
    for c in selected:
        jack_capture.validate_plan(SECONDS*1000, c['fault'], c['policy'], c['trigger'],
                                   c['fault_delay_slots'], c['fault_us'])
    a.out.mkdir(parents=True)
    state = dict(schema=1, status='incomplete', cases=selected, completed=[],
        fixture_build=fixture, generator_build=gen, times_us=TIMES_US,
        acquired_utc=datetime.now(timezone.utc).isoformat())
    path = a.out / 'matrix.json'
    jack_capture.publish_json(path, state)
    from saleae import automation
    try:
        with automation.Manager.launch(headless=True, port=a.server_port) as manager:
            for c in selected:
                print('Starting ' + c['name'], flush=True)
                result = record_case(a, c, manager, gen)
                state['completed'].append(result)
                jack_capture.publish_json(path, state)
                print(f"PASS {len(state['completed'])}/{len(selected)}: {c['name']}", flush=True)
    except BaseException as e:
        state.update(status='stopped on failure; evidence retained', error=str(e))
        jack_capture.publish_json(path, state)
        raise
    state['status'] = 'pass'
    jack_capture.publish_json(path, state)
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan-only', action='store_true')
    for name in ('port','generator-port','scope-id'): p.add_argument('--'+name)
    for name in ('manifest','generator-manifest','out'): p.add_argument('--'+name, type=Path)
    p.add_argument('--case', default='all', choices=['all','faults'] + [c['name'] for c in cases()])
    p.add_argument('--server-port', type=int, default=10439)
    a = p.parse_args()
    if a.plan_only:
        print(json.dumps(dict(cases=cases(), times_us=TIMES_US, seconds=SECONDS), indent=2)); return
    if any(getattr(a, k) is None for k in ('port','generator_port','scope_id','manifest','generator_manifest','out')):
        p.error('explicit fixture, generator, scope, manifests and output are required')
    result = run(a)
    print(f"{result['status']}: {len(result['completed'])} cases")


if __name__ == '__main__': main()
