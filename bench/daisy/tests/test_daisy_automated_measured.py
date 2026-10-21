#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Replay complete automated captures and retain rejected physical evidence."""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'examples/daisy'))
import review_daisy_buttons as physical
import button_campaign
import load_capture
REPLAY = Path(sys.argv.pop(1)).resolve()


def unpack(name, destination):
    source = ROOT/'bench/daisy/measured/daisy/2026-10-18-auto-button'
    meta = json.loads((source/(name+'.json')).read_text())
    payloads = {}
    for key in ('fixture','generator','channels'):
        compressed = (source/(name+'-'+key+'.txt.gz')).read_bytes()
        assert hashlib.sha256(compressed).hexdigest() == meta[key+'_compressed_sha256']
        payloads[key] = gzip.decompress(compressed)
    assert hashlib.sha256(payloads['fixture']).hexdigest() == meta['raw_sha256']
    assert hashlib.sha256(payloads['generator']).hexdigest() == meta['generator_raw_sha256']
    (destination/'fixture').mkdir();(destination/'generator').mkdir()
    (destination/'campaign.json').write_text(json.dumps(meta))
    (destination/'fixture/raw.txt').write_bytes(payloads['fixture'])
    (destination/'generator/raw.txt').write_bytes(payloads['generator'])
    writer = dict(meta['writer'],error=None)
    (destination/'fixture/metadata.json').write_text(json.dumps(dict(writer=writer)))
    summary = load_capture.save_analysis(payloads['fixture'],destination/'fixture',
        meta['fixture_build']['build_id'],REPLAY,False,writer)
    assert summary['checks']['status'] == 'pass' and 'samples replayed' in summary['replay']
    return meta,json.loads(payloads['channels']),summary


class Measured(unittest.TestCase):
    def assert_report_matches(self, actual, expected, field=''):
        # Least-squares arithmetic can round differently across Python versions.
        # The physical acceptance gates run before this report comparison.
        self.assertIs(type(actual), type(expected))
        if isinstance(expected, dict):
            self.assertEqual(actual.keys(), expected.keys())
            for key in expected:
                with self.subTest(field=key):
                    self.assert_report_matches(actual[key], expected[key], key)
        elif isinstance(expected, list):
            self.assertEqual(len(actual), len(expected))
            for value, reference in zip(actual, expected):
                self.assert_report_matches(value, reference, field)
        elif isinstance(expected, float):
            if field.endswith('_us') or field.endswith('_ppm'):
                # Derived microsecond metrics allow 1 ps of rounding; this is
                # far below the instrument's timestamp resolution. Keep saved
                # edge times exact and physical pass/fail limits unchanged.
                self.assertTrue(math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6),
                                (actual, expected))
            elif field == 'scale':
                self.assertTrue(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=0))
            else:
                self.assertEqual(actual, expected)
        else:
            self.assertEqual(actual, expected)

    def test_complete_baseline_and_reject_corrupt_physical_record(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td);meta,channels,summary=unpack('baseline',path)
            report=physical.review(path,channels)
            self.assert_report_matches(report,meta['review'])
            self.assertEqual(report['samples'],8000)
            self.assertEqual(report['software_behavior']['expected_gestures'],[1,2,1])
            self.assertEqual(report['sampled_button_disagreements'],[])
            self.assertEqual(len(report['button_edges_s']),6)
            self.assertEqual(summary['configuration']['audio_permille'],650)
            for key in ('button','service','gesture'):
                bad=copy.deepcopy(channels);bad[key][1].pop()
                with self.subTest(channel=key),self.assertRaises(ValueError):physical.review(path,bad)
            bad=copy.deepcopy(channels);bad['gesture'][1][-1]+=.001
            with self.assertRaises(ValueError):physical.review(path,bad)

    def test_external_pullup_complete_fixed_fault_campaign(self):
        source = ROOT/'bench/daisy/measured/daisy/2026-10-18-auto-button'
        names = {f'4k7-{case}-{phase:03d}' for case in button_campaign.CASES
                 for phase in (0, 500)}
        self.assertEqual({p.stem for p in source.glob('4k7-*.json')}, names)
        for name in sorted(names):
            with self.subTest(capture=name), tempfile.TemporaryDirectory() as td:
                path = Path(td)
                meta, channels, summary = unpack(name, path)
                self.assertEqual(meta['fixture_configuration']['external_pullup_ohms'], 4700)
                self.assertEqual(meta['times_us'], button_campaign.timetable(
                    meta['case'], meta['requested_input_phase_us']))
                report = physical.review(path, channels)
                self.assert_report_matches(report, meta['review'])
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(report['sampled_button_disagreements'], [])
                config = summary['configuration']
                self.assertEqual((config['audio_permille'], config['block_size'], config['usb_hz']),
                                 (650, 16, 500))
                stalled = meta['case'] in ('press-stall', 'hold-stall', 'release-stall')
                self.assertEqual(summary['cadence_breaks'], int(stalled))
                self.assertEqual(summary['counters']['samples'] + summary['counters']['missed'], 8000)

    def test_configurable_fault_boundaries_under_load(self):
        source = ROOT/'bench/daisy/measured/daisy/2026-10-18-auto-button'
        plans = [('baseline',0,0),('press-stall',0,0)]
        plans += [(case,delay,phase) for phase in (0,500) for case,delays in (
            ('press-stall',(8000,10000,12000)), ('hold-stall',(608000,610000,612000)),
            ('release-stall',(8000,10000,12000))) for delay in delays]
        plans += [('press-adc-gap',delay,0) for delay in (8000,610000)]
        self.assertEqual(len(plans),22)
        expected_names = {f'timing-{case}-{delay:06d}-{phase:03d}' for case,delay,phase in plans}
        self.assertEqual({p.stem for p in source.glob('timing-*.json')}, expected_names)
        for case,delay,phase in plans:
            name = f'timing-{case}-{delay:06d}-{phase:03d}'
            with self.subTest(capture=name), tempfile.TemporaryDirectory() as td:
                path = Path(td); meta,channels,summary = unpack(name,path)
                self.assertEqual(meta['fixture_configuration']['external_pullup_ohms'],4700)
                self.assertEqual(meta['times_us'],button_campaign.timetable(case,phase))
                self.assertEqual(meta['fault_delay_us'],delay)
                config = summary['configuration']
                self.assertEqual(config.get('fault_delay_us',0),delay)
                self.assertEqual((config['audio_permille'],config['block_size'],config['usb_hz']),(650,16,500))
                self.assertEqual(summary['counters']['samples']+summary['counters']['missed'],8000)
                report = physical.review(path,channels)
                self.assert_report_matches(report,meta['review'])
                self.assertEqual(report['sampled_button_disagreements'],[])
                self.assertEqual(report['source']['edges'],len(meta['times_us']))
                if (case,delay,phase) == ('press-stall',8000,0):
                    self.assertEqual(meta['original_rejection']['failures'],['missing service before fault'])
                    _,data,_ = load_capture.parse((path/'fixture/raw.txt').read_bytes())
                    _,run,rows = load_capture.capture.parse(data)
                    previous = next(r for r in reversed(rows) if r['time_us'] < run['stimulus']['begin_us'])
                    self.assertEqual(run['stimulus']['begin_us']-previous['time_us'],1008)
                    self.assertEqual(run['stimulus']['begin_us']//1000-previous['time_us']//1000,1)
                if delay:
                    boundary = report['software_behavior']['boundary']
                    # Pin the clearly separated boundary cases independently
                    # of replay and the oracle. The exact nominal boundary is
                    # classified by observed service timing, not requested phase.
                    expected = {('press-stall',8000):[2,1], ('press-stall',12000):[1],
                        ('hold-stall',608000):[1], ('hold-stall',612000):[2,1],
                        ('release-stall',8000):[1], ('release-stall',12000):[1,1]}.get((case,delay))
                    if case == 'press-adc-gap': expected = [1,1]
                    if expected is not None:
                        self.assertEqual(report['software_behavior']['expected_gestures'],expected)
                    if case == 'release-stall' and delay == 10000:
                        # Same nominal delay, different measured service order.
                        # The second capture services release before fault entry;
                        # a fixed-delay shortcut would incorrectly cancel it.
                        self.assertEqual(boundary['first_gesture_outcome'],
                                         'cancelled' if phase == 0 else 'tap_before_gap')
                        self.assertEqual(report['software_behavior']['expected_gestures'],
                                         [1] if phase == 0 else [1,1])
                        if phase == 500:
                            self.assertEqual(boundary['threshold_us'],1061000)
                            self.assertEqual(boundary['expected_events'][0]['time_us'],1061002)
                            self.assertEqual(boundary['fault_begin_minus_threshold_us'],338)
                    self.assertEqual([e['seq'] for e in boundary['expected_events']],
                                     report['software_behavior']['action_sequences'])
                    # Wrong campaign metadata must not relabel a valid capture.
                    bad = dict(meta,fault_delay_us=delay+1)
                    (path/'campaign.json').write_text(json.dumps(bad))
                    with self.assertRaisesRegex(ValueError,'fault delay mismatch'):
                        physical.review(path,channels)

    def test_successful_scope_command_does_not_imply_complete_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td);meta,channels,summary=unpack('incomplete-service-610000',path)
            self.assertEqual(summary['counters']['samples'],7975)
            self.assertEqual(len(channels['service'][1])//2,7148)
            self.assertEqual(meta['status'],'failed incomplete scope window')
            # Do not trim the firmware or reconstruct missing scope samples.
            with self.assertRaisesRegex(ValueError,'Service count mismatch'):
                physical.review(path,channels)

    def test_extra_action_marker_transitions_remain_rejected(self):
        for name,samples,edges,extra in (
            ('unexpected-marker-010000-500',7976,47,46),
            ('unexpected-marker-610000-500',7974,258,256)):
            with self.subTest(capture=name),tempfile.TemporaryDirectory() as td:
                path=Path(td);meta,channels,summary=unpack(name,path)
                self.assertEqual(summary['counters']['samples'],samples)
                self.assertEqual(len(channels['service'][1])//2,samples)
                self.assertEqual(len(channels['gesture'][1]),edges)
                self.assertEqual(meta['unexpected_post_acquisition_action_edges'],extra)
                with self.assertRaisesRegex(ValueError,'unexpected action edges outside acquisition'):
                    physical.review(path,channels)

    def test_release_chatter_remains_a_failed_source(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td);meta,channels,summary=unpack('press-stall',path)
            self.assertEqual(summary['counters']['samples'],7975)
            self.assertEqual(summary['counters']['missed'],25)
            _,controls,_=load_capture.parse((path/'fixture/raw.txt').read_bytes())
            _,_,rows=load_capture.capture.parse(controls)
            behavior=button_campaign.review_controls(summary,rows,'press-stall')
            self.assertEqual(behavior['expected_gestures'],[1])
            self.assertEqual(channels['button'][0],True)
            edges=channels['button'][1];self.assertEqual(len(edges),6)
            self.assertAlmostEqual((edges[-2]-edges[-3])*1e9,5,places=3)
            self.assertAlmostEqual((edges[-1]-edges[-2])*1e9,6,places=3)
            # Never filter these edges to turn failed apparatus evidence into a pass.
            with self.assertRaisesRegex(ValueError,'incomplete physical pulse sequence'):
                physical.review(path,channels)
            self.assertEqual(meta['status'],'failed physical source edge count')


if __name__=='__main__':unittest.main()
