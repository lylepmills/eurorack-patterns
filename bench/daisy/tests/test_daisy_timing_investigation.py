#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Independent binary decoding and retained global-fit counterexample."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools'))
from inspect_daisy_timing import read_digital
from inspect_daisy_timing import load_capture
from daisy_scope import inspect_service, match_service, inspect_aggregate_service, match_aggregate_service


class BinaryTests(unittest.TestCase):
    def encoded(self, edges=(.1, .2), chunks=1, initial=0, count=2):
        return (struct.pack('<8siiQIdddQ', b'<SALEAE>', 1, 0, chunks, initial, 1e9, 0., 1., count)
                + struct.pack('<'+'d'*len(edges), *edges))

    def test_decode(self):
        initial, edges = read_digital(self.encoded())
        self.assertFalse(initial)
        self.assertEqual(list(edges), [.1, .2])
        self.assertTrue(read_digital(self.encoded(initial=1))[0])

    def test_reject_gaps_truncation_and_invalid_edges(self):
        for data in (b'', self.encoded()[:-1], self.encoded()+b'x', self.encoded(count=3),
                     self.encoded(chunks=2), self.encoded(initial=2),
                     self.encoded(edges=(.2, .1)), self.encoded(edges=(.1, .1)),
                     self.encoded(edges=(-.1, .2)), self.encoded(edges=(.1, 1.1)),
                     self.encoded(edges=(float('nan'), .2))):
            with self.subTest(data=data[:24]), self.assertRaises(ValueError): read_digital(data)


class MeasuredTiming(unittest.TestCase):
    def test_later_ordinary_repeat_is_a_separate_bounded_pass(self):
        p = ROOT/'bench/daisy/measured/daisy/2026-10-18-timing-review/ordinary-soak-30m'
        meta = json.loads(p.with_suffix('.json').read_text())
        compressed = p.with_suffix('.txt.gz').read_bytes(); raw = gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(), meta['compressed_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['raw_sha256'])
        s, controls, buckets = load_capture.parse(raw, meta['firmware_build_id'])
        self.assertIsNone(controls)  # Aggregates cannot replay individual observations.
        self.assertEqual(len(buckets), 1800)
        self.assertEqual(s['configuration'], meta['configuration'])
        c = s['configuration']
        self.assertEqual((c['mode'], c['duration_ms'], c['audio_permille'], c['block_size'], c['usb_hz']),
                         (1, 1800000, 650, 16, 500))
        self.assertEqual(s['counters'], meta['counters'])
        self.assertEqual(s['counters']['samples'], 1800000)
        self.assertTrue(all(b['samples'] == 1000 for b in buckets))
        self.assertTrue(load_capture.assess(s, True, dict(meta['host_writer'], error=None)))
        self.assertEqual(s['checks']['failures'], meta['quality_failures'])
        self.assertEqual(meta['validation_status'], 'pass')
        # These are full-recording review results, not a published full waveform.
        # The separate retained failure tests must continue to reject older runs.
        scope = meta['scope']
        self.assertEqual(scope['samples'], 1800000)
        self.assertFalse(scope['mismatched_buckets'])
        self.assertLess(scope['max_interval_error_us'], 5)
        self.assertLess(scope['max_work_width_error_us'], 3)
        self.assertTrue(scope['button_released_throughout'])
        self.assertEqual(scope['action_edges'], 0)
        self.assertEqual(meta['firmware_commit'], 'd30437a42a71796a8cb912d355df0743b6273e6e')

    def test_all_nine_soak_disagreements_remain_rejected(self):
        p = ROOT/'bench/daisy/measured/daisy/2026-10-18-timing-review/soak-disagreements'
        meta = json.loads(p.with_suffix('.json').read_text())
        compressed = p.with_suffix('.txt.gz').read_bytes(); raw = gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(), meta['compressed_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['data_sha256'])
        data = json.loads(raw)
        wire = gzip.decompress((ROOT/'bench/daisy/measured/daisy/2026-10-16-load/soak-30m.txt.gz').read_bytes())
        self.assertEqual(hashlib.sha256(wire).hexdigest(), meta['source_wire_sha256'])
        _, controls, buckets = load_capture.parse(wire)
        self.assertIsNone(controls)
        first, seconds = data['first_original_second'], data['seconds']
        self.assertEqual((first, seconds), (1610, 60))
        selected = [dict(b, second=b['second']-first,
                         first_us=b['first_us']-first*1000000,
                         last_us=b['last_us']-first*1000000) for b in buckets[first:first+seconds]]
        edges = [t/1e9 for t in data['service_edges_ns']]
        self.assertEqual(len(edges), 120000)
        report = inspect_aggregate_service(selected, edges)
        self.assertEqual([b['second']+first for b in report['mismatched_buckets']],
                         meta['failed_original_seconds'])
        self.assertTrue(22.01 < report['max_interval_error_us'] < 22.02)
        self.assertTrue(20.31 < report['max_work_width_error_us'] < 20.32)
        with self.assertRaises(ValueError): match_aggregate_service(selected, edges)

    def test_complete_failed_window_remains_failed(self):
        p = ROOT/'bench/daisy/measured/daisy/2026-10-18-timing-review/clock-drift'
        meta = json.loads(p.with_suffix('.json').read_text())
        compressed = p.with_suffix('.txt.gz').read_bytes(); raw = gzip.decompress(compressed)
        self.assertEqual(hashlib.sha256(compressed).hexdigest(), meta['compressed_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['data_sha256'])
        data = json.loads(raw)
        self.assertEqual(len(data['time_us']), 150000)
        self.assertEqual(len(data['work_us']), 150000)
        self.assertEqual(len(data['service_edges_ns']), 300000)
        rows = [dict(time_us=t, work_us=w) for t, w in zip(data['time_us'], data['work_us'])]
        edges = [t/1e9 for t in data['service_edges_ns']]
        result = inspect_service(rows, edges, local_seconds=1)[2]
        self.assertEqual(result['status'], meta['original_status'])
        self.assertEqual(result['failures'], ['global_fit'])
        report = result['alignment']
        self.assertTrue(5.64 < report['max_fit_residual_us'] < 5.65)
        self.assertLess(report['max_interval_error_us'], 1.06)
        self.assertLess(report['max_work_width_error_us'], 1.10)
        for key in ('max_fit_residual_us', 'max_interval_error_us', 'max_work_width_error_us'):
            self.assertLess(abs(report[key]-meta['original_report'][key]), .002)
        blocks = result['local_diagnostic']['blocks']
        self.assertEqual(len(blocks), 150)
        self.assertEqual(sum(b['samples'] for b in blocks), 150000)
        self.assertLess(max(b['max_fit_residual_us'] for b in blocks), .62)
        self.assertTrue(all(39.4 < b['clock_scale_ppm'] < 40.1 for b in blocks))
        with self.assertRaises(ValueError): match_service(rows, edges)


if __name__ == '__main__': unittest.main()
