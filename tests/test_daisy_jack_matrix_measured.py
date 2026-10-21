# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Selected full electrical recordings plus the bounded campaign manifest."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'examples/daisy'), str(ROOT/'tools')]
import jack_capture
import jack_matrix
from review_daisy_jack_matrix import review

FOLDER = ROOT/'tests/measured/daisy/2026-10-19-jack-matrix'


class Measured(unittest.TestCase):
    def test_complete_campaign_manifest(self):
        campaign=json.loads((FOLDER/'campaign.json').read_text())
        self.assertEqual(campaign['status'],'pass')
        self.assertEqual([r['name'] for r in campaign['cases']], [c['name'] for c in jack_matrix.cases()])
        for actual,plan in zip(campaign['cases'],jack_matrix.cases()):
            for key in ('fault','trigger','fault_delay_slots'):
                self.assertEqual(actual['run'][key],plan[key])
            self.assertEqual(actual['run']['fault_duration_us'],plan['fault_us'])
            self.assertEqual(actual['status'],'pass')
            self.assertEqual(actual['run']['adc_failures'],0)
            self.assertEqual(actual['presence_edges'],2)
            self.assertEqual(actual['run']['count']+actual['run']['missed'],20000)
        self.assertEqual(campaign['observations'],sum(r['run']['count'] for r in campaign['cases']))
        self.assertEqual(campaign['missed_slots'],sum(r['run']['missed'] for r in campaign['cases']))
        self.assertEqual(campaign['invalid_observations'],sum(r['invalid_observations'] for r in campaign['cases']))
        self.assertEqual(campaign['presence_edges'],sum(r['presence_edges'] for r in campaign['cases']))
        self.assertEqual([c['acquisition_segment'] for c in campaign['cases']],
                         ['initial-cases'] * 80 + ['remaining-cases'] * 30)
        for key in ('acquisition_tools_source_commit', 'resumed_acquisition_tools_source_commit',
                    'export_tools_source_commit'):
            self.assertRegex(campaign[key], r'^[0-9a-f]{40}$')

    def test_selected_complete_native_derived_recordings(self):
        campaign=json.loads((FOLDER/'campaign.json').read_text())
        selected=campaign['public_replay_cases']
        self.assertEqual(len(selected),18)
        self.assertEqual(len(set(selected)),18)
        expected={'baseline-before','baseline-after'}
        expected.update(f't{t}-f{f}-us100000-d00' for t in range(1,7) for f in (1,2))
        expected.update(f't{t}-f{f}-us000500-d01' for t in (2,5) for f in (1,2))
        self.assertEqual(set(selected),expected)
        cases={c['name']:c for c in campaign['cases']}
        for name in selected:
            with self.subTest(name=name):
                meta=json.loads((FOLDER/(name+'.json')).read_text())
                self.assertEqual(meta['raw_sha256'],cases[name]['raw_sha256'])
                self.assertEqual(meta['generator_sha256'],cases[name]['generator_sha256'])
                self.assertEqual(meta['run'],cases[name]['run'])
                self.assertEqual(meta['native_scope_sha256'],cases[name]['native_scope_sha256'])
                payload={}
                for key in ('raw','channels','analog','generator'):
                    packed=(FOLDER/f'{name}-{key}.txt.gz').read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
                    data=gzip.decompress(packed)
                    self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
                    payload[key]=json.loads(data) if key in ('channels','analog') else data
                result=review(payload['raw'],payload['channels'],payload['analog'],payload['generator'],
                              meta['generator_build']['build_id'],jack_matrix.TIMES_US)
                self.assertEqual(result['status'],'pass')
                self.assertEqual(result['state_changes'],meta['review']['state_changes'])
                self.assertEqual(result['run'],meta['run'])
                for key in ('invalid_observations', 'ambiguous_analog_apertures',
                            'digital_transition_apertures', 'presence_edges'):
                    self.assertEqual(result[key],cases[name][key])
                _,run,rows,changes=jack_capture.parse(payload['raw'])
                for i,r in enumerate(rows):
                    if r['evidence']==2:
                        self.assertEqual((r['ready'],r['patched']), (rows[i-1]['ready'],rows[i-1]['patched']))
                        self.assertEqual(r['bad_windows'],0)
                # Before-publication faults must restart from fresh evidence.
                if run['trigger'] in (2,5) and run['fault_delay_slots']==0:
                    last=max(i for i,r in enumerate(rows) if r['injected'] or
                             (i and r['missed']!=rows[i-1]['missed']))
                    next_change=next(c for c in changes if c['seq']>last)
                    self.assertEqual(next_change['seq']-last,512 if run['trigger']==2 else 64)


if __name__=='__main__': unittest.main()
