# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Replay complete current/previous/current captures, including clock failures."""
import bisect
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
import dma_memory,pulse_generator
from inspect_daisy_timing import read_digital
from inspect_daisy_clock import clock_coordinates
from inspect_daisy_clock_periods import summarize
from inspect_daisy_reference import fit
from review_daisy_clock_reference import review_timing
from review_daisy_dsp import verify
from review_daisy_jack_load import review_audio
FOLDER=ROOT/'tests/measured/daisy/2026-10-20-firmware-comparison'
REFERENCE=Path(sys.argv[1])

class Measured(unittest.TestCase):
    def equal(self,actual,expected,key=''):
        if isinstance(expected,dict):
            self.assertEqual(actual.keys(),expected.keys())
            for k in expected:self.equal(actual[k],expected[k],k)
        elif isinstance(expected,list):
            self.assertEqual(len(actual),len(expected))
            for a,b in zip(actual,expected):self.equal(a,b,key)
        elif type(expected) is float:
            self.assertAlmostEqual(actual,expected,delta=1e-4 if key.endswith('_us') else 1e-6)
        else:self.assertEqual(actual,expected)

    def test_complete_firmware_comparison(self):
        campaign=json.loads((FOLDER/'campaign.json').read_text())
        stages=['current-before','previous','current-after']
        names=['idle-before','dma-only','dsp-only','combined-first','combined-repeat','idle-after']
        self.assertEqual(campaign['stages'],stages)
        self.assertEqual([p['name'] for p in campaign['plans']],names)
        self.assertEqual([c['name'] for c in campaign['cases']],[s+'-'+n for s in stages for n in names])
        builds=campaign['builds']
        self.assertEqual(builds['current-before'],builds['current-after'])
        self.assertEqual(builds['previous']['source_commit'],'08fcb8204e917cf8af8d1601710e56e765b9f59b')
        self.assertEqual(builds['current-before']['source_commit'],'0cc9d0d64642e9b2d53270421bc0469e59f5f5ec')
        self.assertEqual([builds[s]['protocol'] for s in stages],[7,6,7])
        for key in campaign['common_build_settings']['same_build_environment_and_settings']:
            self.assertEqual(builds['previous'][key],builds['current-before'][key])
        for path in campaign['common_build_settings']['identical_kernel_sources']:
            self.assertEqual(builds['previous']['source_sha256'][path],builds['current-before']['source_sha256'][path])
        self.assertEqual(campaign['scope_settings']['threshold_volts'],1.65)
        self.assertEqual(campaign['scope_settings']['minimum_pulse_width_seconds'],0)
        self.assertEqual(campaign['scope_settings']['scope_derived_digital']['low_threshold_volts'],1.2)
        self.assertEqual(campaign['scope_settings']['scope_derived_digital']['high_threshold_volts'],2.0)
        self.assertEqual([(p['audio_block'],p['dsp_voices'],p['dma_kib']) for p in campaign['plans']],
                         [(0,0,0),(16,0,16),(16,16,0),(16,16,16),(16,16,16),(0,0,0)])
        for plan in campaign['plans']:
            self.assertEqual((plan['dma_region'],plan['dma_period_us']),(0,1000))
        samples=0;reference_edges=0;external_failures=[];combined_frames=[];callbacks=0;copies=0;raw_failures=0
        for case in campaign['cases']:
            name=case['name'];build=builds[case['stage']]
            with self.subTest(name=name):
                meta=json.loads((FOLDER/(name+'.json')).read_text());expected=meta['review'];data={}
                for key,p in meta['payloads'].items():
                    packed=(FOLDER/p['file']).read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),p['compressed_sha256'])
                    raw=lzma.decompress(packed) if key=='clock' else gzip.decompress(packed)
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),p['sha256'])
                    self.assertEqual(len(raw),p['bytes']);data[key]=raw
                self.assertEqual(meta['payloads']['wire']['sha256'],expected['raw_sha256'])
                channels={}
                for key in ('sense','service','presence','probe','clock','audio'):
                    raw=data[key];initial,edges=read_digital(raw)
                    _,_,begin,end,_=struct.unpack_from('<IdddQ',raw,24)
                    channels[key]=dict(initial_high=initial,edges_s=edges,begin_s=begin,end_s=end)
                    self.assertEqual(meta['payloads'][key]['sha256'],expected['digital_sha256'][key])
                timing=review_timing(data['wire'],channels,build['build_id'])
                run=timing['run'];samples+=run['count'];callbacks+=run['audio']['callbacks'];copies+=run['dma']['verified']
                self.equal(run,expected['run']);dma_memory.verify_manifest(run,build)
                self.assertEqual((run['count'],run['missed'],run['adc_failures']),(20000,0,0))
                self.assertEqual(run['finish_reason'],'duration')
                plan=next(p for p in campaign['plans'] if p['name']==case['case'])
                self.assertEqual([run['audio'][k] for k in ('block','permille','off_ms')],
                                 [plan[k] for k in ('audio_block','audio_permille','audio_off_ms')])
                self.assertEqual(run['dsp']['voices'],plan['dsp_voices'])
                self.assertEqual(run['dma']['kib'],plan['dma_kib'])
                self.assertEqual(run['dma']['period_us'],1000 if plan['dma_kib'] else 0)
                if build['protocol']==7:self.assertEqual(run['dma_memory']['region'],0)
                for key in ('scheduling','clock_stability','hardware_clock'):self.equal(timing[key],expected[key])
                self.assertEqual(timing['scheduling']['status'],'pass')
                if timing['clock_stability']['status']=='fail':external_failures.append(name)
                self.equal(verify(run,REFERENCE),expected['dsp_dma'])
                self.equal(review_audio(timing['audio_timing'],timing['audio_channel']),expected['audio'])
                generator=pulse_generator.parse(data['generator'],campaign['generator_build_id'],campaign['times_us'])
                raw_ref=channels['sense'];raw_expected=expected['raw_reference']
                if raw_expected['status']=='fail':
                    raw_failures+=1
                    self.assertEqual(len(raw_ref['edges_s']),raw_expected['observed_edges'])
                    with self.assertRaisesRegex(ValueError,'incomplete physical pulse sequence'):
                        pulse_generator.inspect_physical(generator,raw_ref['initial_high'],raw_ref['edges_s'])
                else:self.equal(pulse_generator.inspect_physical(generator,raw_ref['initial_high'],raw_ref['edges_s']),raw_expected)
                initial,edges=read_digital(data['hysteretic'])
                self.equal(pulse_generator.inspect_physical(generator,initial,edges),expected['independent']['generator_vs_scope'])
                self.assertEqual(len(edges),64);reference_edges+=len(edges)
                _,_,begin,end,_=struct.unpack_from('<IdddQ',data['hysteretic'],24)
                svc=timing['rises'];clock=channels['clock']['edges_s'][::2]
                self.assertTrue(begin<svc[0]<svc[-1]<end)
                gx=[(e['before_us']+e['after_us'])/2e6 for e in generator['edges']]
                hs=[v/1e6 for v in clock_coordinates(edges,clock,16000000/15)]
                self.equal(fit(gx,hs),expected['generator_vs_hse'])
                self.equal(summarize(clock,[(svc[0],svc[15999]),(svc[16001],svc[-1])]),expected['period_populations'])
                blocks=[];rows=timing['rows']
                for second in range(10):
                    ids=[i for i,r in enumerate(rows) if second*1e6<=r['sample_us']<(second+1)*1e6]
                    a,b=ids[0],ids[-1];ca,cb=bisect.bisect_left(clock,svc[a]),bisect.bisect_left(clock,svc[b])
                    blocks.append(dict(second=second,hse_period_ppm=((clock[cb]-clock[ca])*(16000000/15)/(cb-ca)-1)*1e6,service_period_ppm=((svc[b]-svc[a])*1e6/(rows[b]['sample_us']-rows[a]['sample_us'])-1)*1e6))
                self.equal(blocks,expected['blocks'])
                if case['case'].startswith('combined'):
                    combined_frames.append((run['dsp']['frames'],run['audio']['callbacks']))
                print('PASS:',name,'complete firmware/work/clock replay',flush=True)
        self.assertEqual(samples,360000)
        self.assertEqual(reference_edges,1152)
        self.assertEqual(external_failures,['previous-combined-first', 'previous-combined-repeat'])
        self.assertEqual(callbacks,288084)
        self.assertEqual(copies,59936)
        self.assertEqual(raw_failures,17)
        self.assertEqual(combined_frames,[(384112,24007)]*6)

if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
