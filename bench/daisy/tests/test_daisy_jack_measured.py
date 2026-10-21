#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Recheck stationary jack captures and retain rejected physical evidence."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import review_daisy_jacks as physical
import export_daisy_jack


def unpack(name, case='empty'):
    base = ROOT / ('bench/daisy/measured/daisy/2026-10-19-jack-' + case)
    meta = json.loads((base / (name + '.json')).read_text())
    payloads = {}
    for key in ('raw', 'channels', 'analog'):
        packed = (base / (name + '-' + key + '.txt.gz')).read_bytes()
        assert hashlib.sha256(packed).hexdigest() == meta[key + '_compressed_sha256']
        raw = gzip.decompress(packed)
        assert hashlib.sha256(raw).hexdigest() == meta[key + '_sha256']
        payloads[key] = raw if key == 'raw' else json.loads(raw)
    return meta, payloads


class Measured(unittest.TestCase):
    def test_protocol_three_stationary_fault_preflights(self):
        for name, fault in [('baseline', 0), ('adc-gap', 1), ('service-gap', 2)]:
            with self.subTest(capture=name):
                meta, p = unpack(name, 'transition-preflight')
                info, run, rows, changes = physical.jack_capture.parse(p['raw'])
                report = physical.review(p['raw'], p['channels'], p['analog'], meta['build']['build_id'])
                self.assertEqual(info['protocol'], 3)
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(run, meta['run'])
                self.assertEqual(run['fault'], fault)
                self.assertEqual(run['trigger'], 0)
                self.assertEqual(run['trigger_seq'], 0xffffffff)
                self.assertEqual(run['trigger_us'], 0)
                self.assertEqual(run['fault_due_us'], 2000000 if fault else 0)
                self.assertEqual(run['fault_duration_us'], 25000)
                self.assertEqual(run['count'] + run['missed'], 6000)
                self.assertEqual(run['adc_failures'], 0)
                self.assertEqual(run['finish_reason'], 'duration')
                self.assertEqual(p['channels']['presence']['edges_s'], [])
                self.assertEqual(len(changes), 1)
                self.assertTrue(changes[0]['ready']); self.assertFalse(changes[0]['patched'])
                self.assertEqual(report['invalid_observations'], [0, 50, 1][fault])
                self.assertEqual(run['missed'], 50 if fault == 2 else 0)
                if fault:
                    self.assertTrue(0 <= run['fault_begin_us'] - run['fault_due_us'] < 500)
                    self.assertEqual(run['fault_end_us'] - run['fault_begin_us'], 25000)
                for i, r in enumerate(rows):
                    if r['evidence'] == 2:
                        self.assertEqual((r['ready'], r['patched']),
                                         (rows[i-1]['ready'], rows[i-1]['patched']))
                        self.assertEqual(r['bad_windows'], 0)

    def test_complete_scope_tail_after_short_and_long_finishes(self):
        for name in ('minimum','early','duration','early-phase','long-duration','long-early'):
            with self.subTest(capture=name):
                meta, p = unpack(name, 'postroll')
                report = physical.review(p['raw'], p['channels'], p['analog'], meta['build']['build_id'])
                run = report['run']
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(run, meta['run'])
                self.assertEqual(run['missed'], 0); self.assertEqual(run['adc_failures'], 0)
                self.assertEqual(report['invalid_observations'], 0)
                self.assertEqual(len(p['channels']['service']['edges_s']), run['count'] * 2)
                self.assertEqual(p['channels']['presence']['edges_s'], [])
                self.assertGreaterEqual(meta['capture_tail']['scope_postroll_seconds'], .5)
                self.assertEqual(run['finish_reason'], 'duration' if name in ('duration','long-duration') else 'operator')
                if name in ('minimum','duration','long-duration'):
                    self.assertEqual(run['count'], {'minimum':2000,'duration':6000,'long-duration':120000}[name])
                else:
                    low, high = (120000,122000) if name == 'long-early' else (4000,6000)
                    self.assertTrue(low < run['count'] < high)

    def test_operator_finish_minimum_and_duration(self):
        for name, count, limit, reason in [
                ('early', 4505, 2252500, 'operator'),
                ('minimum', 2000, 1000000, 'operator'),
                ('duration', 6000, 3000000, 'duration')]:
            with self.subTest(capture=name):
                meta, p = unpack(name, 'finish')
                report = physical.review(p['raw'], p['channels'], p['analog'],
                                         meta['build']['build_id'])
                info, run, _, _ = physical.jack_capture.parse(p['raw'])
                self.assertEqual(info['protocol'], 2)
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(run, meta['run'])
                self.assertEqual(run['count'], count)
                self.assertEqual(run['acquisition_limit_us'], limit)
                self.assertEqual(run['finish_reason'], reason)
                self.assertEqual(run['elapsed_us'], limit)
                self.assertEqual(run['duration_ms'], 3000 if name == 'duration' else 300000)
                self.assertEqual(run['missed'], 0)
                self.assertEqual(run['adc_failures'], 0)
                self.assertEqual(report['invalid_observations'], 0)
                self.assertEqual(p['channels']['presence']['edges_s'], [])
                self.assertEqual(len(p['channels']['service']['edges_s']), count * 2)
                self.assertGreater(p['analog']['max_volts'], 3)
                self.assertLess(p['analog']['min_volts'], .1)

    def test_reconnected_analog_high_low_challenge(self):
        for name in ('reconnected', 'after-motion-reconnected'):
            with self.subTest(capture=name):
                meta, p = unpack(name, 'analog-disagreement')
                report = physical.review(p['raw'], p['channels'], p['analog'], meta['build']['build_id'])
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(report['run']['count'], 6000)
                self.assertEqual(report['invalid_observations'], 0)
                self.assertEqual(report['run']['missed'], 0)
                self.assertEqual(report['run']['adc_failures'], 0)
                self.assertGreater(p['analog']['max_volts'], 3)
                self.assertLess(p['analog']['min_volts'], .1)
        # A passed connection challenge does not retroactively change the
        # rejected trace or establish attachment during constant-low readings.
        old, failed = unpack('empty-preflight', 'analog-disagreement')
        self.assertEqual(old['status'], 'analog-disagreement')
        self.assertLess(failed['analog']['max_volts'], .1)
        motion = ROOT / 'bench/daisy/measured/daisy/2026-10-19-jack-motion/slow-partial-silent.json'
        self.assertEqual(json.loads(motion.read_text())['status'], 'motion-analog-disagreement')

    def test_analog_disagreement_stays_rejected(self):
        meta, p = unpack('empty-preflight', 'analog-disagreement')
        self.assertEqual(meta['status'], 'analog-disagreement')
        self.assertIsNone(meta['review'])
        _, run, rows, _ = physical.jack_capture.parse(p['raw'])
        self.assertEqual(run['count'], 6000)
        self.assertGreater(max(r['raw'] for r in rows), 49151)
        self.assertLess(p['analog']['max_volts'], .1)
        self.assertEqual(len(p['channels']['sense']['edges_s']), 3024)
        with self.assertRaisesRegex(ValueError, 'analog/digital plateau disagreement'):
            physical.review(p['raw'], p['channels'], p['analog'])

    def test_empty_run_resets_a_retained_patched_output(self):
        _, p = unpack('baseline')
        d = copy.deepcopy(p['channels'])
        # Construct the documented reset of a previous patched run. Retain the
        # complete empty-jack evidence, including an independently timed edge.
        d['presence']['initial_high'] = True
        d['presence']['edges_s'] = [d['service']['edges_s'][0] - .000152]
        physical.review(p['raw'], d, p['analog'])
        d['presence']['edges_s'][0] -= .000010
        with self.assertRaisesRegex(ValueError, 'presence reset timing'):
            physical.review(p['raw'], d, p['analog'])

    def test_export_rejects_relabelled_fixture(self):
        meta, p = unpack('baseline', 'inserted-open')
        # Electrically low traces alone cannot establish the cable's far-end
        # termination. The declared setup must accompany the measurement.
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'capture'
            (source / 'fixture').mkdir(parents=True)
            (source / 'fixture/raw.txt').write_bytes(p['raw'])
            (source / 'fixture/metadata.json').write_text(json.dumps(dict(
                status='complete', build=meta['build'],
                declared_fixture=json.dumps(dict(case='inserted-open')))))
            prefix = Path(folder) / 'published'
            with self.assertRaisesRegex(AssertionError, 'fixture declaration differs'):
                export_daisy_jack.export(source, prefix, 'pass', case='inserted-silent')
            self.assertFalse(prefix.with_suffix('.json').exists())

    def test_passive_termination_preflights(self):
        for name, fault in [('baseline', 0), ('adc-gap', 1), ('service-gap', 2)]:
            with self.subTest(capture=name):
                meta, p = unpack(name, 'inserted-silent')
                report = physical.review(p['raw'], p['channels'], p['analog'],
                                         meta['build']['build_id'], case='inserted-silent')
                self.assertEqual(meta['fixture']['case'], 'inserted-silent')
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(report['run'], meta['run'])
                self.assertEqual(report['run']['fault'], fault)
                self.assertEqual(report['run']['count'] + report['run']['missed'], 6000)
                self.assertEqual(report['state_changes'],
                                 [dict(seq=511, time_us=255789, ready=True, patched=True)])
                self.assertEqual(p['channels']['sense']['edges_s'], [])
                self.assertTrue(p['channels']['presence']['initial_high'])
                self.assertEqual(len(p['channels']['presence']['edges_s']), 2)
                self.assertEqual(report['invalid_observations'], meta['review']['invalid_observations'])
                self.assertEqual(report['invalid_observations'], [0, 50, 1][fault])
                if fault == 2:
                    self.assertEqual(report['run']['missed'], 50)
                    self.assertEqual(report['run']['fault_end_us']-report['run']['fault_begin_us'], 25322)
                # Requiring an actual probe waveform still matters when the
                # cable's sense input is correctly constant.
                d = copy.deepcopy(p['channels']); d['probe']['edges_s'].pop()
                with self.assertRaisesRegex(ValueError, 'unexpected probe edge count'):
                    physical.review(p['raw'], d, p['analog'], case='inserted-silent')

    def test_inserted_open_and_fault_preflights(self):
        for name, fault in [('baseline', 0), ('adc-gap', 1), ('service-gap', 2)]:
            with self.subTest(capture=name):
                meta, p = unpack(name, 'inserted-open')
                report = physical.review(p['raw'], p['channels'], p['analog'],
                                         meta['build']['build_id'], case='inserted-open')
                self.assertEqual(meta['fixture']['case'], 'inserted-open')
                for key in ('status', 'case', 'run', 'raw_sha256', 'state_changes',
                            'invalid_observations', 'probe_edges'):
                    self.assertEqual(report[key], meta['review'][key])
                self.assertEqual(report['run']['fault'], fault)
                self.assertEqual(report['run']['count'] + report['run']['missed'], 6000)
                self.assertEqual(report['state_changes'],
                                 [dict(seq=511, time_us=255789, ready=True, patched=True)])
                self.assertEqual(report['invalid_observations'], [0, 50, 1][fault])
                if fault == 2:
                    self.assertEqual(report['run']['missed'], 50)
                    self.assertEqual(report['run']['fault_end_us']-report['run']['fault_begin_us'], 25219)
                self.assertEqual(p['channels']['sense']['edges_s'], [])
                self.assertEqual(len(p['channels']['presence']['edges_s']), 1 if fault == 0 else 2)
                # A stationary inserted cable cannot pass as an empty normal.
                with self.assertRaises(ValueError):
                    physical.review(p['raw'], p['channels'], p['analog'])

    def test_reject_inserted_glitches_early_qualification_and_wrong_reset(self):
        for name in ('baseline', 'adc-gap'):
            _, p = unpack(name, 'inserted-open')
            def check(channels, analog=None):
                return physical.review(p['raw'], channels, analog or p['analog'], case='inserted-open')
            for channel in ('sense', 'presence'):
                d = copy.deepcopy(p['channels'])
                end = d[channel]['end_s']
                d[channel]['edges_s'] += [end-.02, end-.01]
                with self.subTest(capture=name, channel=channel), self.assertRaises(ValueError):
                    check(d)
            for offset in (-.000050, .000050):
                d = copy.deepcopy(p['channels']); d['presence']['edges_s'][-1] += offset
                with self.assertRaisesRegex(ValueError, 'presence qualification timing'):
                    check(d)
            d = copy.deepcopy(p['channels']); d['presence']['edges_s'].pop()
            with self.assertRaisesRegex(ValueError, 'unexpected qualified patched'):
                check(d)
            if name == 'adc-gap':
                d = copy.deepcopy(p['channels']); d['presence']['edges_s'][0] -= .01
                with self.assertRaisesRegex(ValueError, 'presence reset timing'):
                    check(d)
            analog = copy.deepcopy(p['analog']); analog['plateau_volts'][0] = analog['max_volts'] = 1.65
            with self.assertRaisesRegex(ValueError, 'analog/digital plateau disagreement'):
                check(p['channels'], analog)
        _, p = unpack('baseline')
        with self.assertRaisesRegex(ValueError, 'inserted sense must stay low'):
            physical.review(p['raw'], p['channels'], p['analog'], case='inserted-open')
        with self.assertRaisesRegex(ValueError, 'unknown fixture case'):
            physical.review(p['raw'], p['channels'], p['analog'], case='unknown')

    def test_complete_empty_jack_and_fault_preflights(self):
        for name, fault in [('baseline', 0), ('adc-gap', 1), ('service-gap', 2)]:
            with self.subTest(capture=name):
                meta, p = unpack(name)
                report = physical.review(p['raw'], p['channels'], p['analog'], meta['build']['build_id'])
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(report['run'], meta['run'])
                self.assertEqual(report['state_changes'], meta['review']['state_changes'])
                self.assertEqual(report['run']['fault'], fault)
                self.assertEqual(report['run']['count'] + report['run']['missed'], 6000)
                self.assertEqual(report['run']['adc_failures'], 0)
                self.assertEqual([c['patched'] for c in report['state_changes']], [False])
                self.assertEqual(report['state_changes'][0]['seq'], 63)
                self.assertEqual(report['invalid_observations'], [0, 50, 2][fault])
                self.assertEqual(p['channels']['presence']['edges_s'], [])
                if fault == 2:
                    _, _, rows, _ = physical.jack_capture.parse(p['raw'])
                    self.assertEqual(report['run']['missed'], 51)
                    self.assertEqual(report['run']['fault_end_us']-report['run']['fault_begin_us'], 25950)
                    self.assertEqual([r['seq'] for r in rows if r['evidence'] == 2], [4000, 4001])
                    self.assertEqual([r['adc_end_us'] for r in rows[4000:4003]], [2026240, 2026530, 2026820])

    def test_missing_probe_stays_rejected(self):
        meta, p = unpack('missing-probe')
        self.assertEqual(meta['status'], 'missing-probe')
        self.assertEqual(p['channels']['probe']['edges_s'], [])
        with self.assertRaisesRegex(ValueError, 'unexpected probe edge count'):
            physical.review(p['raw'], p['channels'], p['analog'])

    def test_reject_trimming_extra_edges_wrong_timing_and_voltage(self):
        _, p = unpack('baseline')
        for name in ('service', 'sense', 'probe'):
            d = copy.deepcopy(p['channels']); d[name]['edges_s'].pop()
            with self.subTest(channel=name), self.assertRaises(ValueError):
                physical.review(p['raw'], d, p['analog'])
        d = copy.deepcopy(p['channels'])
        d['presence']['edges_s'] = [d['service']['edges_s'][-1]+.01, d['service']['edges_s'][-1]+.02]
        with self.assertRaisesRegex(ValueError, 'unexpected qualified patched'):
            physical.review(p['raw'], d, p['analog'])
        for index in (0, -1):
            d = copy.deepcopy(p['channels']); d['probe']['edges_s'][index] += .000020
            with self.subTest(edge=index), self.assertRaises(ValueError):
                physical.review(p['raw'], d, p['analog'])
        # The original checker used last conversion end +50 us. Pin the real
        # >200 us tail and reject moving the edge to that incorrect reference.
        d = copy.deepcopy(p['channels'])
        self.assertGreater(d['probe']['edges_s'][-1]-d['service']['edges_s'][-1], .000200)
        d['probe']['edges_s'][-1] = d['service']['edges_s'][-1] + .000010
        with self.assertRaisesRegex(ValueError, 'terminal probe release disagreement'):
            physical.review(p['raw'], d, p['analog'])
        analog = copy.deepcopy(p['analog']); analog['plateau_volts'][0] = 1.65
        with self.assertRaisesRegex(ValueError, 'analog/digital plateau disagreement'):
            physical.review(p['raw'], p['channels'], analog)
        analog = copy.deepcopy(p['analog']); analog['plateau_indices'][0] += 10
        with self.assertRaisesRegex(ValueError, 'analog plateau time mismatch'):
            physical.review(p['raw'], p['channels'], analog)
        analog = copy.deepcopy(p['analog']); analog['plateau_volts'].pop()
        with self.assertRaisesRegex(ValueError, 'missing analog plateau samples'):
            physical.review(p['raw'], p['channels'], analog)

if __name__ == '__main__': unittest.main()
