# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Preserve accepted evidence AND the reproducible combined-load rejection."""
from bisect import bisect_left,bisect_right
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import jack_capture,pulse_generator,jack_dsp_matrix
import test_daisy_jack_scheduled_measured as prior
from daisy_scope import inspect_service,match_service
from inspect_daisy_timing import read_digital
from review_daisy_dsp import verify
from review_daisy_jack_load import review,review_finish
REFERENCE=Path(sys.argv[1]);FOLDER=ROOT/'bench/daisy/measured/daisy/2026-10-20-jack-dsp'


class Measured(unittest.TestCase):
    assert_review_equal=prior.Measured.assert_review_equal

    def payload(self,name,keys):
        meta=json.loads((FOLDER/(name+'.json')).read_text());payload={}
        for key in keys:
            desc=meta.get('payloads',{}).get(key)
            packed=(FOLDER/(desc['file'] if desc else f'{name}-{key}.txt.gz')).read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(),desc['compressed_sha256'] if desc else meta[key+'_compressed_sha256'])
            data=gzip.decompress(packed)
            self.assertEqual(hashlib.sha256(data).hexdigest(),desc['sha256'] if desc else meta[key+'_sha256'])
            payload[key]=json.loads(data) if key in ('channels','analog') else data
        self.assertEqual(meta['build']['source_commit'],'a6cee8ec6e570d0468f74f8537f8578fb390d020')
        return meta,payload

    def test_only_completed_prefix_is_qualified(self):
        campaign=json.loads((FOLDER/'campaign.json').read_text())
        self.assertEqual(campaign['status'],'incomplete; stopped on reproducible global timing disagreement')
        plans=jack_dsp_matrix.cases('sweep')
        self.assertEqual([c['name'] for c in campaign['accepted_cases']],[p['name'] for p in plans[:5]])
        self.assertEqual(campaign['remaining_unattempted'],[p['name'] for p in plans[6:]+jack_dsp_matrix.cases('faults')])
        samples=0
        for case in campaign['accepted_cases']:
            with self.subTest(name=case['name']):
                m,p=self.payload(case['name'],('raw','channels','analog','generator'))
                r=review(p['raw'],p['channels'],p['analog'],p['generator'],m['generator_build']['build_id'],m['generator_times_us'],require_response=True,dsp_reference=REFERENCE)
                self.assert_review_equal(r,m['review']);self.assertEqual(r['run'],case['run'])
                self.assertEqual(r['qualification'],'responsive');self.assertEqual(r['run']['missed'],0)
                self.assertEqual(r['late_adc_observations'],0);samples+=r['samples']
        self.assertEqual(samples,100000)

    def test_early_finish_with_dsp_and_dma_enabled(self):
        for name in ('finish-unloaded','finish-dsp-dma'):
            with self.subTest(name=name):
                m,p=self.payload(name,('raw','channels','analog'))
                r=review_finish(p['raw'],p['channels'],p['analog'],dsp_reference=REFERENCE)
                self.assert_review_equal(r,m['review']);self.assertEqual(r['run']['finish_reason'],'operator')
                self.assertEqual(r['run']['dma']['started'],r['run']['dma']['verified'])

    def test_rejected_and_reference_recordings_keep_original_timing_gate(self):
        names=['combined-timing-rejected','combined-timing-repeat-rejected','reference-unloaded','reference-dsp-only','reference-combined']
        for name in names:
            with self.subTest(name=name):
                m,p=self.payload(name,('raw','service','audio','sense','probe','generator'))
                _,run,rows,_=jack_capture.parse(p['raw']);self.assertEqual(run,m['run'])
                self.assertEqual(run['count'],20000);self.assertEqual(run['missed'],0)
                self.assertEqual(run['adc_failures'],0);self.assertEqual(verify(run,REFERENCE),m['dsp_dma'])
                pulse_generator.parse(p['generator'],m['generator_build_id'],m['generator_times_us'])
                initial,edges=read_digital(p['service'])
                sr=[dict(time_us=r['sample_us'],work_us=r['end_us']-r['sample_us']) for r in rows]
                timing=inspect_service(sr,edges,initial,local_seconds=1)[2]
                self.assert_review_equal(timing,m['service_timing'])
                fail=name not in ('reference-unloaded','reference-dsp-only')
                self.assertEqual(timing['failures'],['global_fit'] if fail else [])
                if fail:
                    with self.assertRaisesRegex(ValueError,'do not match'):match_service(sr,edges,initial)
                    self.assertGreater(timing['alignment']['max_fit_residual_us'],10)
                else:match_service(sr,edges,initial)
                if name.startswith('reference-'):self.check_reference(m,p)

    def check_reference(self,m,p):
        # The declared map must account for EVERY edge not explained by the
        # probe. Every remaining generator edge must be physically occluded.
        ref=m['clock_reference'];si,sense=read_digital(p['sense']);pi,probe=read_digital(p['probe'])
        def nearest(t):
            j=bisect_left(probe,t)
            return min(abs(t-probe[k]) for k in (j-1,j) if 0<=k<len(probe))
        visible=[(t,bool(si ^ ((i+1)%2))) for i,t in enumerate(sense) if nearest(t)>5e-6]
        self.assertEqual(len(visible),ref['visible_edges']);self.assertEqual(len(visible),len(ref['matched']))
        x=[];y=[];seqs=[]
        gen=pulse_generator.parse(p['generator'],m['generator_build_id'],m['generator_times_us'])
        for (t,high),w in zip(visible,ref['matched']):
            self.assertEqual(t,w['physical_s']);self.assertEqual(high,bool(w['seq']%2))
            e=gen['edges'][w['seq']];x.append((e['before_us']+e['after_us'])/2e6);y.append(t);seqs.append(w['seq'])
        self.assertEqual(len(seqs),len(set(seqs)))
        mx,my=sum(x)/len(x),sum(y)/len(y)
        scale=sum((a-mx)*(b-my) for a,b in zip(x,y))/sum((a-mx)**2 for a in x);offset=my-scale*mx
        residual=max(abs(b-(scale*a+offset))*1e6 for a,b in zip(x,y))
        self.assertLess(residual,.3);self.assertAlmostEqual(residual,ref['max_residual_us'],delta=1e-6)
        self.assertAlmostEqual((scale-1)*1e6,ref['clock_scale_ppm'],delta=1e-6)
        self.assertEqual([h['seq'] for h in ref['hidden']],[i for i in range(64) if i not in seqs])
        for h in ref['hidden']:
            e=gen['edges'][h['seq']];t=offset+scale*(e['before_us']+e['after_us'])/2e6
            self.assertFalse(bool(pi ^ (bisect_right(probe,t)%2)))
            self.assertEqual(h['explanation'],'probe low')

if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
