# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Full physical replay of the finite SAI load, recovery and fault campaign."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import jack_capture
import jack_load_matrix
from review_daisy_jack_load import review
FOLDER=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-audio'


class Measured(unittest.TestCase):
    def assert_review_equal(self, actual, expected):
        # Python versions differ in compensated summation used by the clock
        # fit. The reviewer reruns all physical limits unchanged; only stored
        # derived floating-point diagnostics need roundoff tolerance here.
        if isinstance(expected,dict):
            self.assertEqual(actual.keys(),expected.keys())
            for k in expected: self.assert_review_equal(actual[k],expected[k])
        elif isinstance(expected,list):
            self.assertEqual(len(actual),len(expected))
            for a,b in zip(actual,expected): self.assert_review_equal(a,b)
        elif type(expected) is float:
            self.assertAlmostEqual(actual,expected,delta=1e-6)
        else: self.assertEqual(actual,expected)

    def test_complete_measured_campaign(self):
        campaign=json.loads((FOLDER/'campaign.json').read_text())
        plans=sum((jack_load_matrix.cases(s) for s in ('sweep','recovery','faults')),[])
        self.assertEqual(campaign['status'],'complete')
        self.assertEqual([c['name'] for c in campaign['cases']],[p['name'] for p in plans])
        self.assertEqual(len(plans),21)
        totals=dict(observations=0,missed_slots=0,invalid_observations=0,audio_callbacks=0)
        for case,plan in zip(campaign['cases'],plans):
            name=case['name']
            with self.subTest(name=name):
                meta=json.loads((FOLDER/(name+'.json')).read_text())
                payload={}
                for key in ('raw','channels','analog','generator'):
                    packed=(FOLDER/f'{name}-{key}.txt.gz').read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
                    data=gzip.decompress(packed)
                    self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
                    payload[key]=json.loads(data) if key in ('channels','analog') else data
                required=name.startswith(('recovery','loaded')) or not plan['audio_block']
                result=review(payload['raw'],payload['channels'],payload['analog'],payload['generator'],
                    meta['generator_build']['build_id'],case['generator_times_us'],require_response=required)
                self.assert_review_equal(result,meta['review'])
                self.assertEqual(meta['native_scope_sha256'],case['native_scope_sha256'])
                self.assertEqual(meta['raw_sha256'],case['raw_sha256'])
                self.assertEqual(meta['generator_sha256'],case['generator_sha256'])
                self.assertEqual(result['qualification'],case['qualification'])
                self.assertEqual(result['run'],case['run'])
                run=result['run']
                for key in ('fault','trigger','fault_delay_slots'): self.assertEqual(run[key],plan[key])
                self.assertEqual(run['fault_duration_us'],plan['fault_us'])
                for actual,planned in [('block','audio_block'),('permille','audio_permille'),('off_ms','audio_off_ms')]:
                    self.assertEqual(run['audio'][actual],plan[planned])
                _,_,rows,changes=jack_capture.parse(payload['raw'])
                for i,r in enumerate(rows):
                    if r['evidence']==2:
                        self.assertEqual((r['ready'],r['patched']),(rows[i-1]['ready'],rows[i-1]['patched']) if i else (0,0))
                        self.assertEqual(r['bad_windows'],0)
                if plan['fault']:
                    self.assertGreater(run['fault_begin_us'],0)
                    self.assertLess(run['fault_end_us'],run['audio']['end_us'])
                    affected=[i for i,r in enumerate(rows) if r['injected'] or (i and r['missed']!=rows[i-1]['missed'])]
                    self.assertTrue(affected)
                    last=affected[-1]
                    change=next(c for c in changes if c['seq']>last)
                    self.assertEqual(change['seq']-last,512 if run['trigger']==2 else 64)
                totals['observations']+=run['count']; totals['missed_slots']+=run['missed']
                totals['invalid_observations']+=result['invalid_observations']
                totals['audio_callbacks']+=run['audio']['callbacks']
        for k,v in totals.items(): self.assertEqual(campaign[k],v)
        # Fixed observations, not a claim that these loads always fail or pass.
        limits={c['name'] for c in campaign['cases'] if c['qualification'].startswith('starved')}
        self.assertEqual(limits,{'audio-b16-p700','audio-b48-p500','audio-b48-p700',
                               'audio-b96-p250','audio-b96-p500','audio-b96-p700'})
        changed=campaign['review_change']
        self.assertTrue(changed['native_recording_unchanged'])
        self.assertEqual(changed['full_aperture_ambiguities_preserved'],2277)


if __name__=='__main__': unittest.main()
