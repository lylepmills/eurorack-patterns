# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Protocol-6 corruption, coverage and full DSP signature checks; no hardware."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import jack_capture as j
import jack_dsp_matrix
import review_daisy_dsp as dsp
import review_daisy_jack_load as load
from test_daisy_jack_acquisition_capture import fixture as prior
from test_daisy_jack_fault_capture import rehash
from test_daisy_jack_matrix import generator, BUILD, TIMES
REFERENCE=Path(sys.argv[2])


def fixture(voices=4,kib=4,finish=False, fault=0, trigger=0):
    raw,c,a=prior(fault, trigger, finish=finish); lines=raw.splitlines(keepends=True)
    lines[0]=lines[0].replace(b'"protocol":5',b'"protocol":6')
    values=lines[1][:-1].split(b','); values[9]=b'0'
    lines[1]=b','.join(values+[str(voices).encode(),str(kib).encode()])+b'\n'
    values=lines[4][:-1].split(b','); values[2]=b'0'; lines[4]=b','.join(values)+b'\n'
    frames = 1377*48 if finish else 384000
    s=dsp.signature(str(REFERENCE.resolve()),voices,frames) if voices else dict(frames=0,hash=2166136261,peak=0,nonzero=0,macs=0)
    ds=[voices]+[s[k] for k in ('frames','hash','peak','nonzero','macs')]
    transfers,end = (1376,1377000) if finish else (7999,8000000)
    dm=[kib,1000,transfers,transfers,transfers,transfers*kib*1024,0,0,0,0,1100,end,1100,24000,transfers,240,2,6] if kib else [0]*18
    lines[6:6]=[('JDSP,'+','.join(map(str,ds))+'\n').encode(),('JDMA,'+','.join(map(str,dm))+'\n').encode()]
    return rehash(lines),c,a


class DspCapture(unittest.TestCase):
    def test_early_finish_replays_exact_shortened_dsp_and_drains_dma(self):
        raw,c,a=fixture(finish=True)
        r=load.review_finish(raw,c,a,dsp_reference=REFERENCE)
        self.assertEqual(r['samples'],2754)
        self.assertEqual(r['run']['dsp']['frames'],1377*48)
        self.assertEqual(r['run']['dma']['verified'],1376)
        lines=raw.splitlines(keepends=True); values=lines[7][:-1].split(b',')
        values[3]=b'1377'; lines[7]=b','.join(values)+b'\n'
        with self.assertRaisesRegex(ValueError,'DMA incomplete'):
            load.review_finish(rehash(lines),c,a,dsp_reference=REFERENCE)

    def test_dsp_and_dma_and_baselines(self):
        for voices,kib in ((0,0),(4,0),(0,4),(4,16)):
            raw,c,a=fixture(voices,kib)
            r=load.review(raw,c,a,generator(),BUILD,TIMES,dsp_reference=REFERENCE)
            self.assertEqual(r['qualification'],'responsive')
            self.assertEqual(r['run']['dsp']['voices'],voices)
            self.assertEqual(r['run']['dma']['kib'],kib)
            self.assertEqual(r['workload']['dma_payload_bytes'],7999*kib*1024)

    def test_signature_required_and_corruption_rejected(self):
        raw,_,_=fixture(); run=j.parse(raw)[1]
        with self.assertRaisesRegex(ValueError,'reference executable'): dsp.verify(run)
        for index in (2,3,4,5,6):
            lines=raw.splitlines(keepends=True); parts=lines[6][:-1].split(b',')
            parts[index]=str(int(parts[index])+1).encode(); lines[6]=b','.join(parts)+b'\n'
            with self.subTest(field=index),self.assertRaises(ValueError): dsp.verify(j.parse(rehash(lines))[1],REFERENCE)

    def test_dma_counter_errors_and_missing_coverage_rejected(self):
        raw,_,_=fixture()
        for index,value in ((1,16),(2,500),(3,8000),(4,7998),(5,7998),(6,0),
                            (7,1),(8,1),(9,1),(11,10001),(12,7900000),(13,10001),
                            (14,1200001),(15,7998),(16,0),(17,0),(18,2)):
            lines=raw.splitlines(keepends=True); parts=lines[7][:-1].split(b',')
            parts[index]=str(value).encode(); lines[7]=b','.join(parts)+b'\n'
            with self.subTest(field=index),self.assertRaises(ValueError): dsp.verify(j.parse(rehash(lines))[1],REFERENCE)
        run=j.parse(raw)[1]; run['dma']['verified']=10
        with self.assertRaisesRegex(ValueError,'cover'): dsp.verify(run,REFERENCE)
        for index in (6,7):
            lines=raw.splitlines(keepends=True); del lines[index]
            with self.assertRaises(ValueError): j.parse(rehash(lines))

    def test_bounded_campaign_and_plan(self):
        for stage,n in (('sweep',19),('faults',4)):
            cases=jack_dsp_matrix.cases(stage)
            self.assertEqual(len(cases),n); self.assertEqual(len({c['name'] for c in cases}),n)
            for c in cases:
                j.validate_audio(10000,c['audio_block'],c['audio_permille'],c['audio_off_ms'])
                j.validate_dsp(10000,c['audio_block'],c['audio_permille'],c['dsp_voices'],c['dma_kib'])
        for args in ((10000,0,0,1,0),(10000,48,250,1,0),(10000,48,0,33,0),
                     (10000,48,0,1,8),(31000,48,0,1,16),(10000,48,0,-1,0)):
            with self.assertRaises(ValueError): j.validate_dsp(*args)
        self.assertEqual(j.digital_layout(6),j.digital_layout(5))

if __name__=='__main__': unittest.main(argv=[sys.argv[0]])
