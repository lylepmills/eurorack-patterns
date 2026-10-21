#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Finite FIR/delay and SDRAM DMA campaign; explicit devices and no flashing."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from capture import require
import jack_capture
import jack_matrix
import pulse_generator


def cases(stage):
    common = dict(fault=0,trigger=0,fault_delay_slots=0,fault_us=25000,policy=1,
                  audio_block=0,audio_permille=0,audio_off_ms=0,dsp_voices=0,dma_kib=0)
    if stage == 'sweep':
        result = [dict(common,name='baseline-before')]
        for kib in (4,16):
            result.append(dict(common,name=f'dma-only-k{kib}',audio_block=48,audio_off_ms=8000,dma_kib=kib))
        for block in (16,48,96):
            for voices,kib in ((4,0),(16,0),(4,4),(16,4),(16,16)):
                result.append(dict(common,name=f'dsp-b{block}-v{voices}-k{kib}',
                    audio_block=block,audio_off_ms=8000,dsp_voices=voices,dma_kib=kib))
        return result + [dict(common,name='baseline-after')]
    require(stage == 'faults','unknown DSP stage')
    return [dict(common,name=f'dsp-loaded-t{t}-f{f}',audio_block=16,audio_off_ms=8000,
                 dsp_voices=4,dma_kib=4,fault=f,trigger=t) for t in (2,5) for f in (1,2)]


def run(a, *, before_case=None):
    require(a.port != a.generator_port and not a.out.exists(),'distinct ports and new output required')
    manifest = json.loads(a.manifest.read_text())
    require(manifest.get('kind') == 'eurorack-patterns-daisy-jack-bench' and manifest.get('protocol') in (6, 7, 8, 9),
            'protocol-6/7/8/9 DSP/DMA firmware required')
    require(a.dsp_reference.is_file(),'explicit tested DSP reference executable required')
    reference = getattr(a, 'clock_reference', False)
    if reference: jack_capture.validate_clock_reference(manifest, 10000, 0)
    gen = pulse_generator.load_manifest(a.generator_manifest)
    available = cases(a.stage); requested = a.case.split(',')
    require(a.case == 'all' or (len(set(requested)) == len(requested) and
            set(requested) <= {c['name'] for c in available}),'unknown or duplicate case')
    selected = [c for c in available if a.case == 'all' or c['name'] in requested]
    for c in selected:
        jack_capture.validate_plan(10000,c['fault'],c['policy'],c['trigger'],c['fault_delay_slots'],c['fault_us'])
        jack_capture.validate_audio(10000,c['audio_block'],c['audio_permille'],c['audio_off_ms'])
        jack_capture.validate_dsp(10000,c['audio_block'],c['audio_permille'],c['dsp_voices'],c['dma_kib'])
    a.out.mkdir(parents=True)
    state = dict(schema=1,status='incomplete',cases=selected,completed=[],times_us=[3000000,6500000],
        fixture_build=manifest,generator_build=gen,acquired_utc=datetime.now(timezone.utc).isoformat(),
        dsp_reference_sha256=hashlib.sha256(a.dsp_reference.read_bytes()).hexdigest())
    path = a.out/'matrix.json'; jack_capture.publish_json(path,state)
    from saleae import automation
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
    from review_daisy_jack_load import review
    def reviewer(*args): return review(*args,require_response=True,dsp_reference=a.dsp_reference,
                                      clock_reference=reference)
    try:
        with automation.Manager.launch(headless=True,port=a.server_port) as manager:
            for c in selected:
                if before_case is not None: before_case()
                print('Starting '+c['name'],flush=True)
                result = jack_matrix.record_case(a,c,manager,gen,reviewer=reviewer)
                r = result['run']
                require((r['dsp']['voices'],r['dma']['kib']) == (c['dsp_voices'],c['dma_kib']),
                        'recorded DSP/DMA plan differs')
                require((r['audio']['block'],r['audio']['permille'],r['audio']['off_ms']) ==
                        (c['audio_block'],c['audio_permille'],c['audio_off_ms']),'recorded audio plan differs')
                result['qualification'] = 'responsive'
                state['completed'].append(result); jack_capture.publish_json(path,state)
                print(f"VERIFIED {len(state['completed'])}/{len(selected)}: {c['name']}",flush=True)
    except BaseException as error:
        state.update(status='stopped on failure; evidence retained',error=str(error))
        jack_capture.publish_json(path,state); raise
    state['status']=('scheduling and behavior pass; clock stability reported separately'
                     if reference else 'pass')
    jack_capture.publish_json(path,state); return state


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=('sweep','faults'),default='sweep')
    p.add_argument('--case',default='all'); p.add_argument('--plan-only',action='store_true')
    p.add_argument('--clock-reference',action='store_true')
    for k in ('port','generator-port','scope-id'): p.add_argument('--'+k)
    for k in ('manifest','generator-manifest','out','dsp-reference'): p.add_argument('--'+k,type=Path)
    p.add_argument('--server-port',type=int,default=10439)
    a=p.parse_args()
    if a.plan_only: print(json.dumps(cases(a.stage),indent=2)); return
    if any(getattr(a,k) is None for k in ('port','generator_port','scope_id','manifest','generator_manifest','out','dsp_reference')):
        p.error('explicit identities, manifests, reference executable and output required')
    result=run(a); print(result['status'],len(result['completed']),'reviewed DSP/DMA cases')

if __name__=='__main__': main()
