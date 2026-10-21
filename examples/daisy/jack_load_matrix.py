#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Finite silent-audio IRQ sweep, independent electrical clamp, and recovery.

No flashing, serial discovery or overwriting. A physical-integrity failure
stops the campaign; a correctly replayed starvation limit remains explicit.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from capture import require
import jack_capture
import jack_matrix
import pulse_generator


def cases(stage):
    common = dict(fault=0, trigger=0, fault_delay_slots=0, fault_us=25000, policy=1,
                  audio_block=0, audio_permille=0, audio_off_ms=0)
    if stage == 'sweep':
        result = [dict(name='baseline-before', **common)]
        for block in (16,48,96):
            for permille in (0,250,500,700):
                result.append(dict(common, name=f'audio-b{block}-p{permille}',
                    audio_block=block, audio_permille=permille, audio_off_ms=8000))
        return result + [dict(name='baseline-after', **common)]
    if stage == 'recovery':
        return [dict(common, name=f'recovery-b{block}-p700',audio_block=block,
                     audio_permille=700,audio_off_ms=8000) for block in (16,48,96)]
    require(stage == 'faults', 'unknown load stage')
    # Chosen after the initial physical sweep: this measured profile retained
    # all ADC slots and completed both qualifications. Recheck with each run.
    return [dict(common, name=f'loaded-t{trigger}-f{fault}',audio_block=16,
                 audio_permille=250,audio_off_ms=8000,trigger=trigger,fault=fault)
            for trigger in (2,5) for fault in (1,2)]


def run(a, *, before_case=None):
    require(a.port != a.generator_port and not a.out.exists(), 'distinct ports and new output required')
    manifest = json.loads(a.manifest.read_text())
    require(manifest.get('kind') == 'eurorack-patterns-daisy-jack-bench' and manifest.get('protocol') in (4, 5, 6),
            'protocol-4/5/6 jack load firmware required')
    gen = pulse_generator.load_manifest(a.generator_manifest)
    requested = a.case.split(',')
    available = cases(a.stage)
    require(a.case == 'all' or (len(set(requested)) == len(requested) and
            set(requested) <= {c['name'] for c in available}), 'unknown or duplicate case')
    selected = [c for c in available if a.case == 'all' or c['name'] in requested]
    times, seconds = ([3000000,10500000],14) if a.stage == 'recovery' else ([3000000,6500000],10)
    for c in selected:
        jack_capture.validate_audio(seconds*1000,c['audio_block'],c['audio_permille'],c['audio_off_ms'])
    a.out.mkdir(parents=True)
    state = dict(schema=1,status='incomplete',cases=selected,completed=[],times_us=times,
        fixture_build=manifest,generator_build=gen,acquired_utc=datetime.now(timezone.utc).isoformat())
    path = a.out/'matrix.json'
    jack_capture.publish_json(path,state)
    from saleae import automation
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
    from review_daisy_jack_load import review
    def reviewer(*args): return review(*args,require_response=manifest['protocol'] >= 5 or a.stage != 'sweep' or not c['audio_block'])
    try:
        with automation.Manager.launch(headless=True,port=a.server_port) as manager:
            for c in selected:
                if before_case is not None: before_case()
                print('Starting '+c['name'],flush=True)
                result=jack_matrix.record_case(a,c,manager,gen,times=times,seconds=seconds,reviewer=reviewer)
                reviewed=json.loads((a.out/c['name']/'physical-review.json').read_text())
                actual=reviewed['run']['audio']
                require((actual['block'],actual['permille'],actual['off_ms']) ==
                        (c['audio_block'],c['audio_permille'],c['audio_off_ms']), 'recorded audio plan differs')
                result['qualification']=reviewed['qualification']
                state['completed'].append(result); jack_capture.publish_json(path,state)
                print(f"VERIFIED {len(state['completed'])}/{len(selected)}: {c['name']}; {result['qualification']}",flush=True)
    except BaseException as error:
        state.update(status='stopped on failure; evidence retained',error=str(error))
        jack_capture.publish_json(path,state); raise
    state['status']='pass'; jack_capture.publish_json(path,state)
    return state


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=('sweep','recovery','faults'),default='sweep')
    p.add_argument('--case',default='all',help='all or comma-separated exact names; creates a new campaign')
    p.add_argument('--plan-only',action='store_true')
    for k in ('port','generator-port','scope-id'): p.add_argument('--'+k)
    for k in ('manifest','generator-manifest','out'): p.add_argument('--'+k,type=Path)
    p.add_argument('--server-port',type=int,default=10439)
    a=p.parse_args()
    if a.plan_only: print(json.dumps(cases(a.stage),indent=2)); return
    if any(getattr(a,k) is None for k in ('port','generator_port','scope_id','manifest','generator_manifest','out')):
        p.error('explicit identities, manifests and output required')
    print(json.dumps(run(a),indent=2))

if __name__=='__main__': main()
