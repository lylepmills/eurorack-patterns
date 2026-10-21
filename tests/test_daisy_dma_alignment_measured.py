# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Replay complete fixed-layout SDRAM captures, preserving receiver/clock failures."""
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
import dma_memory,dma_alignment,pulse_generator
from inspect_daisy_timing import read_digital
from inspect_daisy_clock import clock_coordinates
from inspect_daisy_clock_periods import summarize
from inspect_daisy_reference import fit
from review_daisy_clock_reference import review_timing
from review_daisy_dsp import verify
from review_daisy_jack_load import review_audio
FOLDER=ROOT/'tests/measured/daisy/2026-10-20-sdram-alignment'
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

    def test_complete_fixed_layout_comparison(self):
        campaign=json.loads((FOLDER/'campaign.json').read_text());build=campaign['build']
        self.assertEqual(build['source_commit'],'4a6f288f4cc723917bc06e95f1346a0f174ad283')
        self.assertEqual(build['protocol'],9)
        self.assertEqual(build['build_id'],'efb2237905e88d4bbaba81f8')
        self.assertEqual(build['artifacts_sha256']['patterns_jack.bin'],
                         '8a5fbb7dcb4d740918f441a2c25a0bf555bd5bc305f5d6d855dd71f03303f00c')
        self.assertEqual(build['fixed_sdram_storage'],{
            'ep_dma_sdram_buffers':dict(address=0xc0000000,size_bytes=32768),
            'ep_dma_low_arena':dict(address=0xc0210000,size_bytes=65536),
            'ep_dma_high_arena':dict(address=0xc1d70000,size_bytes=65536),
            'ep_dsp_delay':dict(address=0xc0008000,size_bytes=2097152),
            'ep_jack_records':dict(address=0xc2000000,size_bytes=28800000)})
        self.assertEqual(campaign['plans']['comparison'],dma_alignment.cases())
        preflight=['early-idle','early-low-offset','early-high-offset']
        names=preflight+[p['name'] for p in dma_alignment.cases()]
        self.assertEqual([c['name'] for c in campaign['cases']],names)
        self.assertEqual(len(names),33)
        self.assertEqual(campaign['settling_seconds'],60)
        self.assertEqual(campaign['scope_settings']['threshold_volts'],1.65)
        self.assertEqual(campaign['scope_settings']['minimum_pulse_width_seconds'],0)
        self.assertEqual(campaign['scope_settings']['scope_derived_digital']['low_threshold_volts'],1.2)
        self.assertEqual(campaign['scope_settings']['scope_derived_digital']['high_threshold_volts'],2.0)
        provenance=campaign['acquisition_provenance']
        for key in ('host_commit','session_adapter_sha256','dsp_reference_sha256','physical_channels'):
            self.assertEqual(provenance['preflight'][key],provenance['comparison'][key])
        samples=0;reference_edges=0;external_failures=[];callbacks=0;copies=0;raw_failures=0;results={}
        for case in campaign['cases']:
            name=case['name'];phase=case['phase']
            with self.subTest(name=name):
                meta=json.loads((FOLDER/(name+'.json')).read_text());expected=meta['review'];data={}
                self.assertEqual(meta['phase'],phase)
                self.assertEqual(set(meta['payloads']),{'wire','sense','service','presence','probe','clock','audio','hysteretic'} |
                                 ({'generator'} if phase=='comparison' else set()))
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
                run=timing['run'];samples+=run['count'];results[name]=run
                self.equal(run,expected['run']);dma_memory.verify_manifest(run,build)
                self.assertEqual((run['missed'],run['adc_failures']),(0,0))
                plan=next(p for p in campaign['plans'][phase] if p['name']==name)
                self.assertEqual(run['dsp']['voices'],plan['dsp_voices'])
                self.assertEqual(run['dma']['kib'],plan['dma_kib'])
                self.assertEqual(run['dma_memory']['region'],plan['dma_region'])
                self.assertEqual(run['dma']['period_us'],plan.get('dma_period_us',1000) if plan['dma_kib'] else 0)
                self.assertEqual(run['audio']['block'],plan['audio_block'])
                for key in ('scheduling','clock_stability','hardware_clock'):self.equal(timing[key],expected[key])
                self.assertEqual(timing['scheduling']['status'],'pass')
                if timing['clock_stability']['status']=='fail':external_failures.append(name)
                self.equal(verify(run,REFERENCE),expected['dsp_dma'])
                self.equal(review_audio(timing['audio_timing'],timing['audio_channel']),expected['audio'])
                if phase=='preflight':
                    self.assertEqual(run['finish_reason'],'operator')
                    self.assertTrue(1000000<=run['acquisition_limit_us']<=3000000)
                    continue
                self.assertEqual(run['count'],20000)
                self.assertEqual(run['finish_reason'],'duration')
                self.assertEqual(run['dma']['skipped'],0)
                if plan['dma_kib']:self.assertEqual(run['dma']['verified'],3999)
                if plan['audio_block']:self.assertEqual(run['audio']['callbacks'],24007)
                if plan['dsp_voices']:self.assertEqual(run['dsp']['frames'],384112)
                self.assertEqual([run['audio'][k] for k in ('block','permille','off_ms')],
                                 [plan[k] for k in ('audio_block','audio_permille','audio_off_ms')])
                callbacks+=run['audio']['callbacks'];copies+=run['dma']['verified']
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
                print('PASS:',name,'complete fixed-layout/work/clock replay',flush=True)
        self.assertEqual(
            [{k:p[k] for k in ('left','right','variable')} for p in campaign['throughput_comparisons']],
            dma_alignment.comparison_pairs())
        for pair in campaign['throughput_comparisons']:
            self.equal(dma_alignment.compare(results[pair['left']],results[pair['right']]),
                       {k:v for k,v in pair.items() if k not in ('left','right','variable')})
        # Exact measured totals; all eight clock failures remain explicit.
        self.assertEqual(samples,609406)
        self.assertEqual(reference_edges,1920)
        self.assertEqual(callbacks,672196)
        self.assertEqual(copies,103974)
        self.assertEqual(raw_failures,30)
        self.assertEqual(external_failures,['combined-s1-r4', 'combined-s1-r6', 'combined-s1-r8', 'combined-s1-r2', 'combined-s2-r2', 'combined-s2-r8', 'combined-s2-r6', 'combined-s2-r4'])

if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
