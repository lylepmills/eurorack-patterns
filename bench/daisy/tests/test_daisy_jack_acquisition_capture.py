#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Protocol-5 replay from the same phase controller used by the firmware."""
import copy
import math
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'examples/daisy'), str(ROOT/'tools')]
import jack_capture as j
import review_daisy_jack_load as review
from test_daisy_jack_fault_capture import scope, rehash
from test_daisy_jack_matrix import generator, BUILD, TIMES
BINARY=sys.argv[1]


def fixture(fault=0,trigger=0,finish=False):
    raw=subprocess.check_output([BINARY,'--trace',str(fault),str(trigger)])
    if finish:
        lines=raw.splitlines(keepends=True)
        lines[2]=b'JFINISH,17,1376500,1377000,1\n'
        lines[4]=b'JLOAD,48,250,8000,1377000,1377,61000,240000,0,0,0,240000,240000000\n'
        lines[5]=b'JACQ,50,0,0,1,27540,2754,240,480,7931520,0,0,0,0,1\n'
        lines=lines[:8+2754]+[b'JEND,17,2754,0,0,0,1377000,0\n']
        raw=rehash(lines)
    parsed=j.parse(raw); channels,analog=scope(parsed)
    load=parsed[1]['audio']; edges=[]
    for i in range(load['callbacks']):
        t=1.0001+i*.001; edges += [t,t+load['max_work_ticks']/240000000]
    channels['audio']=dict(initial_high=False,begin_s=0.,end_s=12.,edges_s=edges)
    service=channels['service']['edges_s']
    analog['source_plateaus']=dict(
        center_indices=[math.floor((a+b)/2*250000) for a,b in zip(service[::2],service[1::2])],
        minimum_volts=analog['minimum_volts'][:], maximum_volts=analog['maximum_volts'][:],
        representation='Three native samples centered at or before each service midpoint; source timing only')
    return raw,channels,analog


def check(raw,c,a): return review.review(raw,c,a,generator(),BUILD,TIMES)


class AcquisitionCapture(unittest.TestCase):
    def test_all_transition_faults_replay_and_qualify(self):
        for fault,trigger in [(0,0)]+[(f,t) for f in (1,2) for t in range(7)]:
            with self.subTest(fault=fault,trigger=trigger):
                raw,c,a=fixture(fault,trigger); result=check(raw,c,a)
                self.assertEqual(result['qualification'],'responsive')
                self.assertTrue(result['patched_while_audio_active'])
                self.assertEqual(result['late_adc_observations'],0)
                self.assertEqual(result['run']['missed'],50 if fault==2 else 0)

    def test_hashed_acquisition_metadata_failures_rejected(self):
        raw,c,a=fixture()
        for index,value in [(1,100),(2,1),(3,1),(4,0),(5,100),(6,1),
                            (7,12000),(8,12000),(9,0),(10,1),(11,1),(12,1),(13,1),(14,0)]:
            lines=raw.splitlines(keepends=True)
            parts=lines[5][:-1].split(b','); parts[index]=str(value).encode()
            lines[5]=b','.join(parts)+b'\n'
            with self.subTest(index=index),self.assertRaises(ValueError): check(rehash(lines),c,a)
        lines=raw.splitlines(keepends=True); del lines[5]
        with self.assertRaises(ValueError): j.parse(rehash(lines))

    def test_finish_command_and_audio_channel_layout_include_protocol5(self):
        self.assertEqual(j.digital_layout(5),j.digital_layout(4))
        raw,c,a=fixture()
        bad=copy.deepcopy(c); del bad['audio']
        with self.assertRaises(ValueError): check(raw,bad,a)

    def test_independent_finish_review(self):
        raw,c,a=fixture(finish=True)
        result=review.review_finish(raw,c,a)
        self.assertEqual(result['samples'],2754)
        self.assertEqual(result['audio']['callbacks'],1377)
        bad=copy.deepcopy(c); bad['service']['edges_s'].pop()
        with self.assertRaises(ValueError): review.review_finish(raw,bad,a)
        raw,c,a=fixture()
        with self.assertRaises(ValueError): review.review_finish(raw,c,a)

    def test_exact_boundary_finish_includes_already_started_slot(self):
        raw,_,_=fixture()
        lines=raw.splitlines(keepends=True)
        lines[2]=b'JFINISH,17,9999500,10000000,1\n'
        _,run,rows,_=j.parse(rehash(lines))
        self.assertEqual(run['finish_reason'],'operator')
        self.assertEqual(rows[-1]['slot'],19999)
        lines[2]=b'JFINISH,17,9999500,9999500,1\n'
        with self.assertRaisesRegex(ValueError,'finish boundary'): j.parse(rehash(lines))

if __name__=='__main__': unittest.main(argv=[sys.argv[0]])
