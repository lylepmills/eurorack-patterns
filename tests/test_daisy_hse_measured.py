# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Reproduce the hardware-clock diagnosis without reclassifying failed loads."""
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'examples/daisy')]
import jack_capture
from daisy_scope import inspect_service
from inspect_daisy_clock import inspect
from inspect_daisy_timing import read_digital
from review_daisy_dsp import verify
from review_daisy_jack_load import review_finish
import test_daisy_jack_scheduled_measured as prior
REFERENCE = Path(sys.argv[1])
FOLDER = ROOT/'tests/measured/daisy/2026-10-20-jack-hse'


class Measured(unittest.TestCase):
    assert_review_equal = prior.Measured.assert_review_equal

    def payload(self, meta, key, folder=FOLDER):
        d = meta['payloads'][key]
        packed = (folder/d['file']).read_bytes()
        self.assertEqual(hashlib.sha256(packed).hexdigest(), d['compressed_sha256'])
        # Standard XZ's byte-delta filter compresses the native double timestamps
        # losslessly. The decompressed bytes must match the original MSO export.
        raw = lzma.decompress(packed) if d['file'].endswith('.xz') else gzip.decompress(packed)
        self.assertEqual(len(raw), d['bytes'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), d['sha256'])
        return raw

    def test_complete_wire_and_service_evidence_for_every_diagnostic(self):
        campaign = json.loads((FOLDER/'campaign.json').read_text())
        self.assertEqual(len(campaign['diagnostics']), 5)
        self.assertIn('incomplete', campaign['status'])
        for case in campaign['diagnostics']:
            with self.subTest(name=case['name']):
                meta = json.loads((FOLDER/(case['name']+'.json')).read_text())
                raw, service = (self.payload(meta, key) for key in ('raw', 'service'))
                _, run, rows, _ = jack_capture.parse(raw, clock_diagnostic=True)
                self.assertEqual(run, meta['run'])
                self.assertEqual(run['missed'], 0)
                self.assertEqual(run['adc_failures'], 0)
                self.assertEqual(verify(run, REFERENCE), meta['dsp_dma'])
                initial, edges = read_digital(service)
                timing = inspect_service([dict(time_us=r['sample_us'],
                    work_us=r['end_us']-r['sample_us']) for r in rows],
                    edges, initial, local_seconds=1)[2]
                self.assert_review_equal(timing, meta['service_timing'])
                self.assertEqual(timing['failures'],
                                 ['global_fit'] if 'combined' in case['name'] else [])
                self.assertEqual('clock' in meta['payloads'], case['public_full_clock'])
                with self.assertRaisesRegex(ValueError, 'wrong firmware role'):
                    jack_capture.parse(raw)

    def test_complete_hardware_cycles_explain_full_duration_counterexample(self):
        for name in ('clock-unloaded', 'clock-combined-full'):
            with self.subTest(name=name):
                meta = json.loads((FOLDER/(name+'.json')).read_text())
                report = inspect(*(self.payload(meta,k) for k in ('raw','service','clock')), REFERENCE)
                self.assert_review_equal(report['hardware_clock'], meta['hardware_clock'])
                self.assert_review_equal(report['service_clock_cycles'], meta['service_clock_cycles'])
                self.assertLess(report['service_clock_cycles']['max_residual_us'], .5)
                self.assertEqual(report['service_clock_cycles']['samples'], report['run']['count'])
                if name == 'clock-combined-full':
                    self.assertGreater(report['service_timing']['alignment']['max_fit_residual_us'], 14)
                    self.assertEqual(report['service_timing']['failures'], ['global_fit'])
                    blocks = report['hardware_clock']['blocks']
                    self.assertEqual(len(blocks), 10)
                    # The change is visible in counted clock cycles themselves.
                    self.assertGreater(min(b['clock_scale_ppm'] for b in blocks[8:]) -
                                       max(b['clock_scale_ppm'] for b in blocks[:8]), 8)
                    self.assertTrue(all(abs(b['clock_scale_ppm']-b['service_clock_scale_ppm']) < .4
                                        for b in blocks))
                    self.assertEqual(report['run']['dma']['verified'], 7999)

    def test_normal_marker_mode_and_early_finish_restored(self):
        for name in ('normal-before', 'normal-after'):
            meta = json.loads((FOLDER/(name+'.json')).read_text())
            payload = {}
            for key in ('raw','channels','analog'):
                packed = (FOLDER/(name+'-'+key+'.txt.gz')).read_bytes()
                self.assertEqual(hashlib.sha256(packed).hexdigest(), meta[key+'_compressed_sha256'])
                data = gzip.decompress(packed)
                self.assertEqual(hashlib.sha256(data).hexdigest(), meta[key+'_sha256'])
                payload[key] = data if key == 'raw' else json.loads(data)
            result = review_finish(payload['raw'],payload['channels'],payload['analog'],
                                   dsp_reference=REFERENCE)
            self.assert_review_equal(result, meta['review'])
            self.assertEqual(result['status'], 'pass')


class SimultaneousAudio(unittest.TestCase):
    """Replay all three complete clock/audio captures without passing the load."""
    assert_review_equal = prior.Measured.assert_review_equal
    folder = ROOT/'tests/measured/daisy/2026-10-20-jack-hse-audio'

    def payload(self, meta, key):
        return Measured.payload(self, meta, key, self.folder)

    def test_every_callback_and_service_observation_against_hardware_cycles(self):
        campaign = json.loads((self.folder/'campaign.json').read_text())
        self.assertIn('incomplete', campaign['status'])
        self.assertEqual(len(campaign['diagnostics']), 3)
        samples = callbacks = 0
        for case in campaign['diagnostics']:
            with self.subTest(name=case['name']):
                meta = json.loads((self.folder/(case['name']+'.json')).read_text())
                raw, service, clock, audio = (
                    self.payload(meta, key) for key in ('raw','service','clock','audio'))
                report = inspect(raw, service, clock, REFERENCE, audio)
                for key in ('run','service_timing','hardware_clock','service_clock_cycles',
                            'audio_in_clock_cycles','dsp_dma'):
                    self.assert_review_equal(report[key], meta[key])
                self.assertEqual(report['run']['missed'], 0)
                self.assertEqual(report['run']['adc_failures'], 0)
                self.assertLess(report['service_clock_cycles']['max_residual_us'], .5)
                self.assertEqual(report['audio_in_clock_cycles']['callbacks'],
                                 report['run']['audio']['callbacks'])
                combined = case['name'] == 'clock-combined-full'
                self.assertEqual(report['service_timing']['failures'],
                                 ['global_fit'] if combined else [])
                if combined:
                    self.assertGreater(
                        report['service_timing']['alignment']['max_fit_residual_us'], 12)
                    self.assertEqual(report['run']['dma']['verified'], 7999)
                with self.assertRaisesRegex(ValueError, 'wrong firmware role'):
                    jack_capture.parse(raw)
                samples += report['run']['count']
                callbacks += report['audio_in_clock_cycles']['callbacks']
        self.assertEqual(samples, 32000)
        self.assertEqual(callbacks, 30008)

    def test_normal_mode_restored_and_loaded_early_finish_complete(self):
        for name in ('normal-before', 'normal-after'):
            with self.subTest(name=name):
                meta = json.loads((self.folder/(name+'.json')).read_text())
                payload = {}
                for key in ('raw','channels','analog'):
                    packed = (self.folder/(name+'-'+key+'.txt.gz')).read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),
                                     meta[key+'_compressed_sha256'])
                    data = gzip.decompress(packed)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), meta[key+'_sha256'])
                    payload[key] = data if key == 'raw' else json.loads(data)
                result = review_finish(payload['raw'],payload['channels'],payload['analog'],
                                       dsp_reference=REFERENCE)
                self.assert_review_equal(result, meta['review'])
                self.assertEqual(result['status'], 'pass')
                if name == 'normal-after':
                    self.assertEqual(result['audio']['callbacks'], 4285)
                    self.assertEqual(result['run']['dma']['verified'], 1427)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
