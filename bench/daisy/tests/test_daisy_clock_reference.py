# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Synthetic independent-clock changes must not conceal scheduling errors."""
import copy
import gzip
import json
import lzma
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import jack_capture as j
import review_daisy_clock_reference as reference
import review_daisy_jack_load as load
from test_daisy_dsp_capture import fixture, REFERENCE
from test_daisy_jack_matrix import generator, BUILD, TIMES
from inspect_daisy_timing import read_digital


def mrecord(raw):
    return raw.replace(b'daisy-jack-bench', b'daisy-jack-clock-reference').replace(b'JSTART,', b'MSTART,')


class Reference(unittest.TestCase):
    def test_measured_counterexample_keeps_external_failure_and_checks_widths(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-20-jack-hse-audio'
        meta=json.loads((folder/'clock-combined-full.json').read_text())
        def payload(key):
            entry=meta['payloads'][key]
            data=(folder/entry['file']).read_bytes()
            return lzma.decompress(data) if key=='clock' else gzip.decompress(data)
        _,_,rows,_=j.parse(payload('raw'),clock_diagnostic=True)
        def channel(key):
            initial,edges=read_digital(payload(key))
            return dict(initial_high=initial,edges_s=edges)
        result=reference.scheduling(rows,channel('service'),channel('clock'))
        self.assertEqual(result[-2]['status'],'pass')
        self.assertLess(result[-2]['max_residual_us'],.5)
        self.assertLess(result[-2]['max_work_width_error_us'],3)
        self.assertEqual(result[-1]['failures'],meta['service_timing']['failures'])
        self.assertGreater(result[-1]['alignment']['max_fit_residual_us'],12)
        # Original diagnostic identity is still rejected by the behavior path.
        with self.assertRaisesRegex(ValueError,'wrong firmware role'):
            reference.review_timing(payload('raw'),{})

    def test_explicit_mode_capability_and_complete_markers(self):
        raw,_,_=fixture(voices=0,kib=0,finish=True)
        m=mrecord(raw)
        self.assertEqual(j.parse(m,clock_reference=True)[1],j.parse(raw)[1])
        for value,kwargs in ((raw,dict(clock_reference=True)),(m,{}),
                             (m,dict(clock_diagnostic=True)),
                             (m,dict(clock_reference=True,clock_diagnostic=True))):
            with self.assertRaises(ValueError):j.parse(value,**kwargs)
        with self.assertRaisesRegex(ValueError,'MSTART'):
            j.parse(m.replace(b'MSTART',b'KSTART'),clock_reference=True)
        manifest=dict(protocol=6,clock_reference=j.CLOCK_REFERENCE)
        j.validate_clock_reference(manifest,10000,0)
        for m,d,p in (({},10000,0),(manifest,11000,0),(manifest,999,0),(manifest,3000,1)):
            with self.assertRaises(ValueError):j.validate_clock_reference(m,d,p)
        self.assertEqual(j.digital_layout(6,clock_reference=True)[-2:],
                         [('clock',1,0),('audio',1,1)])
        for kwargs in (dict(protocol=5),dict(protocol=6,clock_diagnostic=True),
                       dict(protocol=6,diagnostic_audio=True)):
            with self.assertRaises(ValueError):j.digital_layout(**kwargs,clock_reference=True)

    def test_scheduling_rejects_delay_drift_width_loss_and_incomplete_clock(self):
        physical=lambda t: 1+t+30e-6*t*t
        rows=[dict(sample_us=10000+i*1000,end_us=10100+i*1000) for i in range(2000)]
        edges=[physical(r[k]/1e6) for r in rows for k in ('sample_us','end_us')]
        clock=dict(initial_high=False,edges_s=[physical(i/1000+j*.0005)
                                              for i in range(3000) for j in (0,1)])
        service=dict(initial_high=False,edges_s=edges)
        result=reference.scheduling(rows,service,clock,1000)
        self.assertEqual(result[-2]['status'],'pass')
        self.assertEqual(result[-1]['failures'],['global_fit'])
        self.assertLess(result[-2]['max_residual_us'],.001)
        for mode in ('delay','width','missing'):
            bad=copy.deepcopy(service)
            if mode=='delay':bad['edges_s'][1000:1002]=[t+8e-6 for t in edges[1000:1002]]
            if mode=='width':bad['edges_s'][1001]+=4e-6
            if mode=='missing':del bad['edges_s'][1000:1002]
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                reference.scheduling(rows,bad,clock,1000)
        bad=[dict(sample_us=r['sample_us']*1.00001,end_us=r['end_us']*1.00001) for r in rows]
        with self.assertRaisesRegex(ValueError,'offset/drift'):
            reference.scheduling(bad,service,clock,1000)
        for bad_edges in (clock['edges_s'][500:],clock['edges_s'][:2000]+clock['edges_s'][2002:]):
            with self.assertRaises(ValueError):
                reference.scheduling(rows,service,dict(initial_high=False,edges_s=bad_edges),1000)

    def test_complete_behavior_and_both_fault_types_keep_physical_apertures(self):
        physical=lambda t: t+30e-6*t*t
        original_scheduling=reference.scheduling
        for fault,trigger in ((0,0),(1,2),(2,5)):
            raw,c,a=fixture(fault=fault,trigger=trigger)
            raw=mrecord(raw)
            for channel in c.values():
                channel['edges_s']=[physical(t) for t in channel['edges_s']]
                channel['end_s']=physical(channel['end_s'])
            c['clock']=dict(initial_high=False,begin_s=0.,end_s=13.,
                edges_s=[physical(i/1000+j*.0005) for i in range(1,12000) for j in (0,1)])
            rises,falls=c['service']['edges_s'][::2],c['service']['edges_s'][1::2]
            a['first_indices']=[math.floor(t*250000) for t in rises]
            a['last_indices']=[math.ceil(t*250000) for t in falls]
            a['source_plateaus']['center_indices']=[math.floor((t+u)/2*250000) for t,u in zip(rises,falls)]
            # Synthetic clock frequency only: the production reviewer fixes
            # its nominal HSE/15 conversion and accepts no capture-supplied rate.
            with patch.object(reference,'scheduling',
                              side_effect=lambda *args:original_scheduling(*args,nominal_hz=1000)):
                result=load.review(raw,c,a,generator(),BUILD,TIMES,dsp_reference=REFERENCE,
                                   require_response=True,clock_reference=True)
                self.assertEqual(result['qualification'],'responsive')
                self.assertEqual(result['scheduling']['status'],'pass')
                self.assertEqual(result['clock_stability']['failures'],['global_fit'])
                self.assertEqual(result['run']['missed'],50 if fault==2 else 0)
                self.assertEqual(result['ambiguous_analog_apertures'],0)
                bad=copy.deepcopy(c);bad['audio']['edges_s']=bad['audio']['edges_s'][:-2]
                with self.assertRaisesRegex(ValueError,'count'):
                    load.review(raw,bad,a,generator(),BUILD,TIMES,dsp_reference=REFERENCE,
                                clock_reference=True)
                bad=copy.deepcopy(a);bad['minimum_volts'][100]=0.;bad['maximum_volts'][100]=3.3
                # Ambiguous voltage must remain ambiguous, never made stable
                # by the change in timing reference.
                ambiguous=load.review(raw,c,bad,generator(),BUILD,TIMES,dsp_reference=REFERENCE,
                                      clock_reference=True)
                self.assertEqual(ambiguous['ambiguous_analog_apertures'],1)
                bad=copy.deepcopy(a);bad['first_indices'][100]+=1
                with self.assertRaisesRegex(ValueError,'aperture timing'):
                    load.review(raw,c,bad,generator(),BUILD,TIMES,dsp_reference=REFERENCE,
                                clock_reference=True)


if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
