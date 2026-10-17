#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Missing/glitched pulses must not be hidden by startup-window alignment."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from daisy_scope import match_service


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


if __name__ == '__main__':
    unittest.main()
