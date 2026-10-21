# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Synthetic IRQ evidence, starvation, recovery and adversarial checks; no hardware."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import jack_capture as j
import jack_load_matrix
import review_daisy_jack_load as review
from test_daisy_jack_fault_capture import scope, rehash
from test_daisy_jack_matrix import generator, BUILD, TIMES
BINARY=sys.argv[1]


def fixture(permille=250):
    raw=subprocess.check_output([BINARY,'--load-trace',str(permille)])
    parsed=j.parse(raw)
    channels,analog=scope(parsed)
    load=parsed[1]['audio']
    edges=[]
    for i in range(load['callbacks']):
        t=1.0001+i*.001
        edges += [t,t+(load['max_work_ticks']/240000000)]
    channels['audio']=dict(initial_high=False,begin_s=0.,end_s=12.,edges_s=edges)
    service=channels['service']['edges_s']
    analog['source_plateaus']=dict(
        center_indices=[math.floor((a+b)/2*250000) for a,b in zip(service[::2],service[1::2])],
        minimum_volts=analog['minimum_volts'][:],maximum_volts=analog['maximum_volts'][:],
        representation='Three native samples centered at or before each service midpoint; source timing only')
    return raw,channels,analog


def check(raw,channels,analog,**kw):
    return review.review(raw,channels,analog,generator(),BUILD,TIMES,**kw)


class AudioLoad(unittest.TestCase):
    def test_source_witness_preserves_full_aperture_ambiguity(self):
        raw,c,a=fixture(700)
        # At a service boundary the next bit can enter the analog sample bin.
        # The interior samples identify the source without certifying that ADC.
        for i in range(100,500):
            a['minimum_volts'][i]=0.; a['maximum_volts'][i]=3.3
        result=check(raw,c,a)
        self.assertEqual(result['ambiguous_analog_apertures'],400)
        for field,value in [('center_indices',0),('minimum_volts',4.),('maximum_volts',float('nan'))]:
            bad=copy.deepcopy(a); bad['source_plateaus'][field][100]=value
            with self.subTest(field=field),self.assertRaises(ValueError): check(raw,c,bad)
        bad=copy.deepcopy(a)
        p=bad['source_plateaus']; value=3.3 if p['maximum_volts'][100]<1 else 0.
        p['minimum_volts'][100]=p['maximum_volts'][100]=value
        with self.assertRaisesRegex(ValueError,'analog/digital'): check(raw,c,bad)

    def test_replay_and_independent_irq_coverage(self):
        raw,channels,analog=fixture()
        r=check(raw,channels,analog,require_response=True)
        self.assertEqual(r['audio']['callbacks'],8000)
        self.assertEqual(r['qualification'],'responsive')
        self.assertEqual(r['recovery_tail_samples'],2000)

    def test_starvation_is_reported_and_not_called_responsive(self):
        raw,channels,analog=fixture(700)
        r=check(raw,channels,analog)
        self.assertEqual(r['qualification'],'starved under load; recovered empty')
        self.assertGreater(r['run']['missed'],0)
        self.assertGreater(r['invalid_observations'],0)
        with self.assertRaisesRegex(ValueError,'did not complete'): check(raw,channels,analog,require_response=True)

    def test_independent_audio_corruption_rejected(self):
        raw,channels,analog=fixture()
        for change in ('missing','extra','width','cadence','stuck','coverage'):
            c=copy.deepcopy(channels); e=c['audio']['edges_s']
            if change=='missing': del e[100:102]
            if change=='extra': e[100:100]=[1.0495,1.0496]
            if change=='width': e[101]+=.0001
            if change=='cadence': e[100]+=.0001; e[101]+=.0001
            if change=='stuck': c['audio']['initial_high']=True
            if change=='coverage': c['audio']['end_s']=8.
            with self.subTest(change=change),self.assertRaises(ValueError): check(raw,c,analog)

    def test_checksummed_counter_and_plan_mutations(self):
        raw,channels,analog=fixture()
        for index,value in [(1,16),(2,500),(3,9000),(4,1),(5,7999),(6,1),(7,1),(8,1),(9,1),(10,1),(11,1),(12,1)]:
            lines=raw.splitlines(keepends=True)
            parts=lines[4][:-1].split(b','); parts[index]=str(value).encode(); lines[4]=b','.join(parts)+b'\n'
            with self.subTest(field=index),self.assertRaises(ValueError): check(rehash(lines),channels,analog)
        lines=raw.splitlines(keepends=True); del lines[-2]
        parts=lines[-1][:-1].split(b','); parts[2]=str(int(parts[2])-1).encode(); lines[-1]=b','.join(parts)+b'\n'
        with self.assertRaisesRegex(ValueError,'missing final'): j.parse(rehash(lines))

    def test_finite_plan_and_boundaries(self):
        for stage,expected in [('sweep',14),('recovery',3),('faults',4)]:
            cases=jack_load_matrix.cases(stage)
            self.assertEqual(len(cases),expected)
            self.assertEqual(len({c['name'] for c in cases}),expected)
            for c in cases: j.validate_audio(10000,c['audio_block'],c['audio_permille'],c['audio_off_ms'])
        for c in jack_load_matrix.cases('faults'):
            self.assertEqual((c['audio_block'],c['audio_permille'],c['fault_delay_slots'],c['fault_us']),(16,250,0,25000))
            j.validate_plan(10000,c['fault'],c['policy'],c['trigger'],c['fault_delay_slots'],c['fault_us'])
        for p in [(16,700,8000),(48,0,1000),(96,250,9000),(0,0,0)]: j.validate_audio(10000,*p)
        for p in [(0,1,0),(17,0,8000),(16,701,8000),(16,0,9500),(16,-1,8000),(48,100,4294967295)]:
            with self.assertRaises(ValueError): j.validate_audio(10000,*p)

if __name__=='__main__': unittest.main(argv=[sys.argv[0]])
