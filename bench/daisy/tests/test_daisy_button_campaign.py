# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'examples/daisy'))
import button_campaign as campaign
import pulse_generator


class Tests(unittest.TestCase):
    def test_coordinator_releases_identified_source_on_acquisition_failure(self):
        # No physical ports: exercise cleanup before/after the fixture's ack,
        # including a generator failure while the fixture is still collecting.
        for failure in ('identity', 'fixture-before-ack', 'source-start',
                        'source-finish', 'fixture-after-ack'):
            events = []
            class Port:
                def __init__(self, **kwargs): pass
                def __enter__(self): return self
                def __exit__(self, *args): pass
            class Source:
                def __init__(self, *args): self.identified = False
                def prepare(self, times):
                    events.append('prepare')
                    if failure == 'identity': raise ValueError('identity')
                    self.identified = True
                def start(self):
                    events.append('start')
                    if failure == 'source-start': raise ValueError('start')
                def finish(self):
                    events.append('finish')
                    if failure == 'source-finish': raise ValueError('finish')
                def abort(self): events.append('abort')
            def fixture(args, on_started):
                events.append('fixture')
                if failure == 'fixture-before-ack': raise ValueError('fixture')
                events.append('ack')
                on_started()
                return 2 if failure == 'fixture-after-ack' else 0
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as td:
                replay = Path(td)/'replay'; replay.touch()
                args = SimpleNamespace(case='baseline', phase_us=0, port='fixture',
                    generator_port='source', manifest=None, generator_manifest=None,
                    replay=replay, out=Path(td)/'case', audio_permille=650, usb_hz=500)
                with patch.dict(sys.modules, {'serial': SimpleNamespace(Serial=Port)}), \
                     patch.object(campaign.capture, 'load_manifest', return_value={'load_faults':1}), \
                     patch.object(campaign.pulse_generator, 'load_manifest', return_value={}), \
                     patch.object(campaign.pulse_generator, 'Generator', Source), \
                     patch.object(campaign.load_capture, 'record', fixture):
                    with self.assertRaises(ValueError): campaign.record(args)
                self.assertEqual(events.count('abort'), int(failure != 'identity'))
                self.assertEqual(events.count('start'), int(failure not in ('identity','fixture-before-ack')))
                if 'start' in events:
                    self.assertLess(events.index('ack'), events.index('start'))
                self.assertTrue((args.out/'campaign.json').is_file())

    def test_plans(self):
        for case in campaign.CASES:
            for phase in (0, 137, 999):
                times = campaign.timetable(case, phase)
                pulse_generator.validate_times(times)
                self.assertEqual(times[0], 1000000+phase)
                self.assertLess(times[-1], 6000000)
        for case, phase in [('bad',0),('baseline',-1),('baseline',1000),('baseline',True)]:
            with self.assertRaises(ValueError): campaign.timetable(case,phase)

    def test_cancellation_and_recovery(self):
        rows = [dict(seq=i,time_us=t,pressed=p,gesture=g,adc_valid=1,injected=0)
                for i,(t,p,g) in enumerate([(0,0,0),(100000,1,0),(800000,0,0),
                    (1000000,1,0),(1100000,0,0),(1110000,0,1)])]
        for case in ('press-stall','hold-stall','release-stall'):
            summary = dict(checks=dict(status='pass'),configuration=dict(
                scenario=campaign.capture.SCENARIOS[case],startup_held=False))
            self.assertEqual(campaign.review_controls(summary,rows,case)['expected_gestures'],[1])
            wrong = copy.deepcopy(rows); wrong[2]['gesture']=1
            with self.assertRaises(ValueError): campaign.review_controls(summary,wrong,case)
            wrong = copy.deepcopy(rows); wrong[-1]['gesture']=2
            with self.assertRaises(ValueError): campaign.review_controls(summary,wrong,case)
            wrong = copy.deepcopy(summary); wrong['configuration']['startup_held']=True
            with self.assertRaises(ValueError): campaign.review_controls(wrong,rows,case)

    def test_adc_independence_requires_fault_and_recovery(self):
        rows = [dict(seq=i,time_us=t,pressed=p,gesture=g,adc_valid=v,injected=1-v)
                for i,(t,p,g,v) in enumerate([(0,0,0,1),(100000,1,0,1),
                    (200000,0,0,0),(210000,0,1,0),(1000000,1,0,1),
                    (1100000,0,0,1),(1110000,0,1,1)])]
        s = dict(checks=dict(status='pass'),configuration=dict(scenario=8,startup_held=False))
        self.assertEqual(campaign.review_controls(s,rows,'press-adc-gap')['expected_gestures'],[1,1])
        bad = copy.deepcopy(rows); bad[3]['adc_valid']=1;bad[3]['injected']=0
        with self.assertRaises(ValueError): campaign.review_controls(s,bad,'press-adc-gap')
        bad = copy.deepcopy(rows); bad[-1]['adc_valid']=0;bad[-1]['injected']=1
        with self.assertRaises(ValueError): campaign.review_controls(s,bad,'press-adc-gap')


if __name__ == '__main__': unittest.main()
