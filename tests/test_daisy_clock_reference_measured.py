# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Replay every remaining measured DSP/DMA profile with separate clock verdicts."""
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import jack_capture,jack_dsp_matrix
from inspect_daisy_timing import read_digital
from review_daisy_jack_load import review
REFERENCE=Path(sys.argv[1])
FOLDER=ROOT/'tests/measured/daisy/2026-10-20-jack-clock-reference'

class Measured(unittest.TestCase):
    def assert_review_equal(self,actual,expected,key=''):
        # Python's compensated sum changed across versions. Allow 0.1 ns
        # roundoff only in stored microsecond summaries (below the scope's
        # 1 ns digital resolution). The reviewer reruns every physical gate.
        if isinstance(expected,dict):
            self.assertEqual(actual.keys(),expected.keys())
            for k in expected:self.assert_review_equal(actual[k],expected[k],k)
        elif isinstance(expected,list):
            self.assertEqual(len(actual),len(expected))
            for a,b in zip(actual,expected):self.assert_review_equal(a,b,key)
        elif type(expected) is float:
            self.assertAlmostEqual(actual,expected,delta=1e-4 if key.endswith('_us') else 1e-6)
        else:self.assertEqual(actual,expected)

    def test_all_remaining_profiles_keep_clock_verdicts_separate(self):
        campaign=json.loads((FOLDER/'campaign.json').read_text())
        self.assertEqual(campaign['status'],'18 scheduling and behavior comparisons complete; external clock stability reported separately')
        plans=jack_dsp_matrix.cases('sweep')[5:]+jack_dsp_matrix.cases('faults')
        self.assertEqual([c['name'] for c in campaign['cases']],[p['name'] for p in plans])
        self.assertEqual(campaign['prior_original_passes'],5)
        samples=0
        skipped_launch_cases=[]
        clock_failures=0
        for plan,case in zip(plans,campaign['cases']):
            name=case['name']
            with self.subTest(name=name):
                meta=json.loads((FOLDER/(name+'.json')).read_text())
                self.assertTrue(meta['clock_reference'])
                self.assertEqual(meta['build']['source_commit'],'08fcb8204e917cf8af8d1601710e56e765b9f59b')
                payload={}
                for key in ('raw','channels','analog','generator','clock'):
                    path=FOLDER/(meta['clock_file'] if key=='clock' else name+'-'+key+'.txt.gz')
                    packed=path.read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
                    data=lzma.decompress(packed) if key=='clock' else gzip.decompress(packed)
                    self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
                    payload[key]=json.loads(data) if key in ('channels','analog') else data
                self.assertEqual(meta['clock_sha256'],meta['native_scope_sha256']['digital_2_0.bin'])
                raw=payload['clock'];initial,edges=read_digital(raw)
                _,_,begin,end,_=struct.unpack_from('<IdddQ',raw,24)
                payload['channels']['clock']=dict(initial_high=initial,edges_s=edges,begin_s=begin,end_s=end)
                result=review(payload['raw'],payload['channels'],payload['analog'],payload['generator'],
                              meta['generator_build']['build_id'],meta['generator_times_us'],
                              require_response=True,dsp_reference=REFERENCE,clock_reference=True)
                self.assert_review_equal(result,meta['review'])
                self.assertEqual(result['run'],case['run'])
                self.assertEqual(result['status'],meta['status'])
                self.assertEqual(result['scheduling']['status'],'pass')
                self.assert_review_equal(result['scheduling'],case['scheduling'])
                self.assert_review_equal(result['clock_stability'],case['clock_stability'])
                clock_failures+=result['clock_stability']['status']=='fail'
                self.assertEqual(result['qualification'],'responsive')
                run=result['run'];self.assertEqual(run['fault'],plan['fault'])
                self.assertEqual(run['trigger'],plan['trigger'])
                self.assertEqual(run['missed'],50 if plan['fault']==2 else 0)
                self.assertEqual(run['adc_failures'],0)
                self.assertEqual(result['invalid_observations'],50 if plan['fault']==1 else 1 if plan['fault']==2 else 0)
                self.assertEqual(run['count'],20000-(50 if plan['fault']==2 else 0))
                self.assertEqual(run['dma']['started'],run['dma']['verified'])
                if run['dma']['skipped']:
                    skipped_launch_cases.append(name)
                self.assertEqual(result['late_adc_observations'],0)
                samples+=run['count']
                print('PASS:',name,'scheduling/behavior; external clock:',result['clock_stability']['status'],flush=True)
        self.assertEqual(samples,359900)
        self.assertEqual(clock_failures,13)
        self.assertEqual(skipped_launch_cases,[
            'dsp-b16-v16-k16','dsp-b48-v16-k16','dsp-b96-v16-k16'])

if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
