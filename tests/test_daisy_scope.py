#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Reject incomplete scope coverage and metadata outside the public allowlist."""
import gzip
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from daisy_scope import match_service, match_aggregate_service
from export_daisy_trace import check_identity, public_identity, public_writer


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(time_us=i*1000, work_us=140) for i in range(100)]
        self.edges = [t for i in range(100) for t in (2.2+i*.001, 2.200140+i*.001)]

    def test_complete(self):
        self.assertEqual(len(match_service(self.rows, self.edges)[0]), 100)

    def test_startup_prefix_is_retained(self):
        _, _, report = match_service(self.rows, [.1, 2.] + self.edges, startup=True)
        self.assertEqual(len(report['pre_application_high_intervals_s']), 1)
        self.assertLess(report['pre_application_high_intervals_s'][0][1], 0)

    def test_bad_traces_rejected(self):
        for rows in ([], self.rows[:1]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                match_service(rows, [.1, 2.], startup=True)
        moved = self.edges.copy(); moved[100] += .0003; moved[101] += .0003
        wide = self.edges.copy(); wide[101] += .00002
        cases = [self.edges[2:], [.1, 2.] + self.edges[2:],
                 [.1, .100140] + self.edges, [.1, .5, .7, 2.] + self.edges,
                 self.edges[:100] + self.edges[102:], moved, wide, self.edges[:-1],
                 [float('nan')] + self.edges[1:]]
        for edges in cases:
            with self.subTest(edges=edges[:4]), self.assertRaises(ValueError):
                match_service(self.rows, edges, startup=True)

    def test_prefix_requires_startup_and_margin(self):
        with self.assertRaises(ValueError):
            match_service(self.rows, [.1, 2.] + self.edges)
        with self.assertRaises(ValueError):
            match_service(self.rows, [.1, 2.199] + self.edges, startup=True)
        with self.assertRaises(ValueError):
            match_service(self.rows, self.edges, initial_high=True)

    def test_aggregate_counts_extrema_and_clock_drift(self):
        buckets = [dict(second=i, samples=1000, missed=0, adc_failures=0, cadence_breaks=0,
                        first_us=i*1000000, last_us=i*1000000+999000,
                        max_interval_us=1000, max_work_us=140) for i in range(2)]
        edges = [2+t*1.00004 for i in range(2000) for t in (i*.001, i*.001+.000140)]
        report = match_aggregate_service(buckets, edges)
        self.assertEqual(report['samples'], 2000)
        self.assertAlmostEqual(report['clock_scale_ppm_min'], 40, places=4)
        self.assertLess(report['max_interval_error_us'], .001)
        drifting = [2 + i*.001*1.00004 + t*1.00004 for i in range(1000) for t in (0, .000140)]
        drifting += [3.00004 + i*.001*1.00008 + t*1.00008 for i in range(1000) for t in (0, .000140)]
        self.assertGreater(match_aggregate_service(buckets, drifting)['clock_scale_ppm_max'], 79)
        wide = edges.copy(); wide[101] += .000020
        shifted = edges.copy(); shifted[2000] += .000300; shifted[2001] += .000300
        for bad in (edges[2:], edges+[5., 5.1], edges[:-1], wide, shifted,
                    [float('nan')]+edges[1:]):
            with self.subTest(edges=len(bad)), self.assertRaises(ValueError):
                match_aggregate_service(buckets, bad)
        for key, value in [('samples',999),('missed',1),('adc_failures',1),
                           ('cadence_breaks',1),('second',2),('max_work_us',100),
                           ('max_interval_us',1200),('last_us',9990010)]:
            bad = [dict(b) for b in buckets]; bad[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                match_aggregate_service(bad, edges)
        with self.assertRaises(ValueError): match_aggregate_service(buckets, edges, True)
        with self.assertRaises(ValueError): match_aggregate_service([], [])


class ExportPrivacyTests(unittest.TestCase):
    def test_new_identity_fields_require_review(self):
        path = Path(__file__).resolve().parent/'measured/daisy/2026-10-16-load/baseline.txt.gz'
        info = json.loads(gzip.decompress(path.read_bytes()).splitlines()[0][5:])
        check_identity(info, load=True)
        check_identity(dict(info, timing_diagnostics=1), load=True)
        for value in (True, 0, 2, '1'):
            with self.assertRaises(AssertionError): check_identity(dict(info, timing_diagnostics=value), load=True)
        for key, value in [('extra', 'unreviewed metadata'), ('cpu_hz', 'unreviewed text'),
                           ('build_id', 'unreviewed-machine'), ('board', 'unreviewed-board')]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                check_identity(dict(info, **{key:value}), load=True)
        with self.assertRaises(AssertionError): check_identity(info)
        wire = b'INFO,' + json.dumps(info).encode() + b'\n'
        self.assertEqual(public_identity(wire, load=True), info)
        duplicate = wire.replace(b'{', b'{"cpu_hz":"unreviewed text",', 1)
        with self.assertRaises(AssertionError): public_identity(duplicate, load=True)

    def test_writer_exports_only_numeric_evidence(self):
        writer = dict(packets=100, skipped_slots=5, max_lateness_s=.01, error=None, extra='not exported')
        self.assertEqual(set(public_writer(writer)), {'packets', 'skipped_slots', 'max_lateness_s'})
        for key, value in [('error', 'arbitrary OS error text'), ('packets', True),
                           ('skipped_slots', -1), ('max_lateness_s', float('nan')),
                           ('max_lateness_s', float('inf')), ('max_lateness_s', -.1)]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                public_writer(dict(writer, **{key:value}))


if __name__ == '__main__':
    unittest.main()
