# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
from pathlib import Path
import gzip
import hashlib
import json
import lzma
import sys
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'examples/daisy'))
from inspect_daisy_reference import fit, inspect
from inspect_daisy_clock_periods import summarize
from inspect_daisy_timing import read_digital
import pulse_generator


def fixture(drift=False):
    times = [.3]
    for i in range(1, 64):
        times.append(times[-1]+.130+(i*7919 % 25000)/1e6)
    physical = lambda t: 1+t*1.00004+(30e-6*t*t if drift else 0)
    generator = dict(edges=[dict(before_us=t*1e6, after_us=t*1e6) for t in times])
    pe = [i*.007+1 for i in range(1450)]
    ge = [physical(t) for t in times]
    events = sorted([(t, 0, bool((i+1) % 2)) for i, t in enumerate(pe)] +
                    [(t, 1, bool(i % 2)) for i, t in enumerate(ge)])
    levels = [False, True]; previous = False; se = []
    for t, role, value in events:
        levels[role] = value
        high = all(levels)
        if high != previous: se.append(t); previous = high
    return generator, dict(initial_high=False, edges_s=se), dict(initial_high=False, edges_s=pe)


class IndependentReference(unittest.TestCase):
    def test_all_edges_accounted_for(self):
        r = inspect(*fixture(), (.99, 1.01))
        self.assertEqual(r['generator_vs_scope']['status'], 'pass')
        self.assertAlmostEqual(r['generator_vs_scope']['clock_scale_ppm'], 40, places=5)
        self.assertGreater(r['visible_edges'], 20)
        self.assertEqual(r['visible_edges']+len(r['hidden_edges']), 64)
        self.assertLess(r['max_waveform_error_us'], 1e-7)

    def test_global_fit_preserves_drift_failure(self):
        x = [i*.1 for i in range(100)]
        r = fit(x, [2+t+30e-6*t*t for t in x])
        self.assertEqual(r['status'], 'fail')
        self.assertIn('global_fit', r['failures'])
        self.assertGreater(r['max_residual_us'], 400)

    def test_extra_missing_wrong_level_and_hidden_edges_rejected(self):
        g, s, p = fixture()
        variants = [dict(s, initial_high=True),
                    dict(s, edges_s=s['edges_s'][:-2]),
                    dict(s, edges_s=s['edges_s'][:10]+s['edges_s'][12:]),
                    dict(s, edges_s=sorted(s['edges_s']+[1.015001, 1.015003]))]
        for bad in variants:
            with self.assertRaises(ValueError): inspect(g, bad, p, (.99, 1.01))
        with self.assertRaises(ValueError): inspect(g, s, p, (2, 3))
        bad = dict(edges=[dict(e) for e in g['edges']])
        bad['edges'][10]['before_us'] += 3000
        bad['edges'][10]['after_us'] += 3000
        with self.assertRaises(ValueError): inspect(bad, s, p, (.99, 1.01))

    def test_fit_rejects_invalid_pairs(self):
        for x,y in [([1,2],[1,2]),([1,2,3],[1,2,float('nan')]),
                    ([1,2,3],[1,3,2]),([1,1,2],[1,2,3])]:
            with self.assertRaises(ValueError): fit(x,y)

    def test_period_population_preserves_phase_advances_and_delays(self):
        rises = [0.]
        for i in range(100):
            # One fewer source cycle, followed much later by one extra cycle.
            cycles = 14 if i == 20 else 16 if i == 70 else 15
            rises.append(rises[-1]+cycles/16000000)
        r = summarize(rises, [(rises[1], rises[-1])])['blocks'][0]
        self.assertEqual(r['periods'], 99)
        self.assertEqual(sum(r['histogram_ns'].values()), 99)
        self.assertEqual((r['short_periods'], r['long_periods']), (1,1))
        self.assertAlmostEqual(r['short_mean_ns'], 875)
        self.assertAlmostEqual(r['long_mean_ns'], 1000)
        self.assertAlmostEqual(r['mean_period_ns'], 937.5)
        self.assertAlmostEqual(r['short_deficit_us'], .0625)
        with self.assertRaises(ValueError): summarize(rises, [(0, rises[-1])])
        with self.assertRaises(ValueError): summarize(rises, [(rises[1], rises[-1]+.001)])


class MeasuredCounterexamples(unittest.TestCase):
    def independent_payloads(self, record):
        folder = ROOT/'bench/daisy/measured/daisy/2026-10-20-independent-clock-reference'
        result = {}
        for key, value in record['payloads'].items():
            packed = (folder/value['file']).read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(), value['compressed_sha256'])
            raw = gzip.decompress(packed)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), value['sha256'])
            self.assertEqual(len(raw), value['bytes'])
            result[key] = raw
        return result

    def test_complete_independent_receivers_preserve_different_results(self):
        folder = ROOT/'bench/daisy/measured/daisy/2026-10-20-independent-clock-reference'
        meta = json.loads((folder/'campaign.json').read_text())
        self.assertEqual([r['name'] for r in meta['cases']],
                         ['idle-before', 'dma-only-k16', 'dsp-only-v16',
                          'combined-v16-k16', 'idle-after'])
        checked = rejected = 0
        for record in meta['cases']:
            with self.subTest(case=record['name']):
                data = self.independent_payloads(record)
                generator = pulse_generator.parse(data['generator'], meta['generator_build_id'],
                                                   meta['times_us'])
                initial, edges = read_digital(data['hysteretic'])
                result = pulse_generator.inspect_physical(generator, initial, edges)
                self.assertEqual(result['status'], 'pass')
                self.assertEqual(result['edges'], 64)
                for key in ('scale', 'max_residual_us', 'max_interval_error_us'):
                    self.assertAlmostEqual(result[key], record['reference'][key], places=4)
                checked += result['edges']
                initial, edges = read_digital(data['raw_probe'])
                if record['raw_reference']['status'] == 'pass':
                    self.assertEqual(pulse_generator.inspect_physical(
                        generator, initial, edges)['status'], 'pass')
                else:
                    self.assertEqual(record['raw_reference']['status'], 'fail')
                    self.assertEqual(len(edges), record['raw_reference']['observed_edges'])
                    with self.assertRaisesRegex(ValueError, 'incomplete physical pulse sequence'):
                        pulse_generator.inspect_physical(generator, initial, edges)
                    rejected += 1
        self.assertEqual(checked, 320)
        self.assertEqual(rejected, 4)

    def test_separate_reference_attempts_with_extra_edges_stay_rejected(self):
        folder = ROOT/'bench/daisy/measured/daisy/2026-10-20-independent-clock-reference'
        meta = json.loads((folder/'campaign.json').read_text())
        self.assertEqual([r['observed_edges'] for r in meta['rejected']], [76, 86])
        for record in meta['rejected']:
            data = self.independent_payloads(record)
            generator = pulse_generator.parse(data['generator'], meta['generator_build_id'],
                                               meta['times_us'])
            initial, edges = read_digital(data['raw_probe'])
            self.assertEqual(len(edges), record['observed_edges'])
            self.assertEqual(sum(b-a < 1e-6 for a,b in zip(edges, edges[1:])),
                             record['extra_edges'])
            with self.assertRaisesRegex(ValueError, 'incomplete physical pulse sequence'):
                pulse_generator.inspect_physical(generator, initial, edges)

    def test_observed_nanosecond_excursions_remain_rejected(self):
        folder = ROOT/'bench/daisy/measured/daisy/2026-10-20-clock-investigation'
        meta = json.loads((folder/'shared-node-noise.json').read_text())
        payloads = {}
        for key, value in meta['payloads'].items():
            packed = (folder/value['file']).read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(), value['compressed_sha256'])
            raw = gzip.decompress(packed)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), value['sha256'])
            self.assertEqual(len(raw), value['bytes'])
            payloads[key] = raw
        generator = pulse_generator.parse(payloads['generator'], meta['generator_build_id'],
                                          meta['generator_times_us'])
        channels = {}
        for key in ('sense', 'probe', 'service'):
            initial, edges = read_digital(payloads[key])
            channels[key] = dict(initial_high=initial, edges_s=edges)
        start = channels['service']['edges_s'][0]
        with self.assertRaisesRegex(ValueError, 'Unexplained or missing'):
            inspect(generator, channels['sense'], channels['probe'], (start-.001, start+.5))
        # All nine brief excursions are retained, not deglitched to a pass.
        se = channels['sense']['edges_s']
        self.assertEqual(sum(b-a < 1e-6 for a,b in zip(se, se[1:])), 18)

    def test_complete_previously_published_clock_exposes_rare_short_periods(self):
        folder = ROOT/'bench/daisy/measured/daisy/2026-10-20-jack-clock-reference'
        name = 'dsp-b16-v16-k16'
        meta = json.loads((folder/(name+'.json')).read_text())
        packed = (folder/meta['clock_file']).read_bytes()
        self.assertEqual(hashlib.sha256(packed).hexdigest(), meta['clock_compressed_sha256'])
        raw = lzma.decompress(packed)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['clock_sha256'])
        initial, edges = read_digital(raw)
        self.assertFalse(initial)
        rises = edges[::2]
        r = summarize(rises, [(rises[1], rises[-1])])['blocks'][0]
        self.assertEqual(r['periods'], 10666668)
        self.assertEqual(sum(r['histogram_ns'].values()), r['periods'])
        self.assertEqual((r['short_periods'], r['long_periods']), (17707, 0))
        self.assertAlmostEqual(r['short_mean_ns'], 875.4596487, places=3)
        self.assertAlmostEqual(r['ordinary_mean_ns'], 937.5367618, places=3)
        self.assertAlmostEqual(r['short_deficit_us'], 1098.5485, places=3)
        # The original external timing rejection is still part of the evidence.
        self.assertEqual(meta['review']['clock_stability']['failures'], ['global_fit'])


if __name__ == '__main__': unittest.main()
