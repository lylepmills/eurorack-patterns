# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Synthetic protocol-3 faults; these traces do not claim hardware validation."""
import contextlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'examples/daisy'), str(ROOT/'tools')]
import jack_capture as jack
import review_daisy_jacks as physical
BINARY = sys.argv[1]


def trace(fault, trigger, delay=0, duration=25000, scenario=0):
    return subprocess.check_output([BINARY, '--trace', *map(str, (fault, trigger, delay, duration, scenario))])


def rehash(lines):
    end = lines[-1][:-1].split(b',')
    end[-1] = str(jack.fnv(b''.join(lines[2:-1]))).encode()
    lines[-1] = b','.join(end) + b'\n'
    return b''.join(lines)


def scope(parsed):
    _, run, rows, _ = parsed
    channels = {name: dict(initial_high=False, edges_s=[], begin_s=0., end_s=12.)
                for name in ('sense', 'service', 'presence', 'probe')}
    analog = dict(sample_rate_hz=250000, begin_s=0., end_s=12., samples=3000000,
                  first_indices=[], last_indices=[], minimum_volts=[], maximum_volts=[],
                  representation='Native extrema over each service aperture, including boundary samples')
    previous = {name: False for name in channels}
    for r in rows:
        for name, value, time in [('probe', bool(r['probe']), r['drive_us']),
                                 ('sense', r['raw'] >= 49151, r['drive_us']),
                                 ('presence', bool(r['ready'] and r['patched']), r['adc_end_us'])]:
            if value != previous[name]: channels[name]['edges_s'].append(1+time/1e6)
            previous[name] = value
        a, b = 1+r['sample_us']/1e6, 1+r['end_us']/1e6
        channels['service']['edges_s'] += [a, b]
        analog['first_indices'].append(math.floor(a*250000))
        analog['last_indices'].append(math.ceil(b*250000))
        v = 3.3 if r['raw'] >= 49151 else 0.
        analog['minimum_volts'].append(v); analog['maximum_volts'].append(v)
    for name in ('probe', 'sense'):
        if previous[name]: channels[name]['edges_s'].append(1+run['elapsed_us']/1e6)
    return channels, analog


class Faults(unittest.TestCase):
    def test_phase_delay_and_duration_matrix(self):
        for trigger in range(1, 7):
            for fault in (1, 2):
                for delay in (0, 1, 64):
                    for duration in (500, 25000, 100000):
                        with self.subTest(trigger=trigger, fault=fault, delay=delay, duration=duration):
                            _, run, rows, changes = jack.parse(trace(fault, trigger, delay, duration))
                            self.assertEqual([c['patched'] for c in changes], [False, True, False])
                            self.assertEqual(run['fault_due_us'], (rows[run['trigger_seq']]['slot']+1+delay)*500)
                            self.assertEqual(run['trigger_us'], rows[run['trigger_seq']]['end_us'])
                            self.assertEqual(run['count']+run['missed'], 20000)
                            self.assertEqual(run['missed'], 0 if fault == 1 else duration//500)
                            self.assertEqual(sum(r['injected'] for r in rows), duration//500 if fault == 1 else 0)
                            self.assertEqual(sum(r['evidence'] == 2 for r in rows), duration//500 if fault == 1 else 1)
                            for i, r in enumerate(rows):
                                if r['evidence'] == 2:
                                    self.assertEqual(r['patched'], rows[i-1]['patched'])
                                    self.assertEqual(r['bad_windows'], 0)
                            # At the slot before qualification, zero delay cancels
                            # the pending window; one extra slot lets it publish first.
                            first = next(r for r in rows if r['sample_us'] >= run['fault_begin_us'])
                            if trigger == 2: self.assertEqual(bool(first['patched']), delay > 0)
                            if trigger == 5: self.assertEqual(bool(first['patched']), delay == 0)

    def test_maximum_bounds_and_legacy_elapsed_mode(self):
        for fault in (1, 2):
            for trigger in (2, 5):
                _, run, _, _ = jack.parse(trace(fault, trigger, 64, 100000))
                self.assertEqual(run['fault_duration_us'], 100000)
                self.assertEqual(run['fault_delay_slots'], 64)
            _, run, _, _ = jack.parse(trace(fault, 0))
            self.assertEqual(run['trigger_seq'], 0xffffffff)
            self.assertEqual(run['fault_due_us'], 2000000)
        self.assertEqual(jack.parse(trace(0, 0))[1]['fault_due_us'], 0)

    def test_untriggered_or_unknown_start_is_not_success(self):
        for scenario in (1, 2):
            for trigger in range(1, 7):
                with self.subTest(scenario=scenario, trigger=trigger), self.assertRaisesRegex(ValueError, 'missing/incomplete fault'):
                    jack.parse(trace(1, trigger, scenario=scenario))

    def test_corrected_checksums_cannot_hide_wrong_timing(self):
        data = trace(1, 2)
        original = data.splitlines(keepends=True)
        for field in range(1, 7):
            lines = list(original); values = lines[3][:-1].split(b',')
            values[field] = str(int(values[field])+1).encode()
            lines[3] = b','.join(values)+b'\n'
            with self.subTest(field=field), self.assertRaises(ValueError): jack.parse(rehash(lines))
        for field, value in [(1, 0), (2, 0)]:
            lines = list(original); values = lines[4][:-1].split(b','); values[field] = str(value).encode()
            lines[4] = b','.join(values)+b'\n'
            with self.assertRaises(ValueError): jack.parse(rehash(lines))
        lines = list(original)
        index = next(i for i, line in enumerate(lines) if line.startswith(b'JDATA,') and line[:-1].split(b',')[14] == b'1')
        for field, value in [(14, b'0'), (18, b'1')]:
            changed = list(original); values = changed[index][:-1].split(b','); values[field] = value
            changed[index] = b','.join(values)+b'\n'
            with self.assertRaises(ValueError): jack.parse(rehash(changed))
        lines = list(original); del lines[-2]
        end = lines[-1][:-1].split(b','); end[2] = str(int(end[2])-1).encode(); lines[-1] = b','.join(end)+b'\n'
        with self.assertRaisesRegex(ValueError, 'missing final'): jack.parse(rehash(lines))

    def test_protocol_three_early_finish_and_file_request(self):
        lines = trace(1, 2).splitlines(keepends=True)
        lines[1] = lines[1].replace(b',10000,', b',300000,', 1)
        lines[2] = b'JFINISH,17,9999999,10000000,1\n'
        self.assertEqual(jack.parse(rehash(lines))[1]['finish_reason'], 'operator')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'metadata.json').write_text(json.dumps(dict(status='incomplete', build=dict(
                kind='eurorack-patterns-daisy-jack-bench', protocol=3))))
            (out/'started.json').write_text('{"token":17}')
            self.assertIn('Finish requested', jack.request_finish(out))
            self.assertEqual(json.loads((out/'finish-request.json').read_text()), dict(token=17))

    def test_complete_physical_contract_and_scope_mutations(self):
        for trigger in range(1, 7):
            for fault in (1, 2):
                data = trace(fault, trigger); parsed = jack.parse(data); channels, analog = scope(parsed)
                with patch.object(physical.jack_capture, 'parse', return_value=parsed):
                    report = physical.review_fault_motion(data, channels, analog)
                    self.assertEqual(report['presence_edges'], 2)
                    self.assertEqual(report['cycles'], 1)
                    with self.assertRaisesRegex(ValueError, 'acquisition failure'):
                        physical.review_motion(data, channels, analog, cycles=1)
                    # A false output transition during the fault must remain visible.
                    at = 1+parsed[1]['fault_begin_us']/1e6
                    channels['presence']['edges_s'] += [at+.00001, at+.00002]
                    channels['presence']['edges_s'].sort()
                    with self.assertRaisesRegex(ValueError, 'qualified patched output'):
                        physical.review_fault_motion(data, channels, analog)
                    channels, analog = scope(parsed)
                    channels['service']['edges_s'].pop()
                    with self.assertRaises(ValueError): physical.review_fault_motion(data, channels, analog)

    def test_capture_sends_extended_plan_and_preserves_download(self):
        data = trace(1, 2); lines = data.splitlines(keepends=True)
        class Port:
            def __init__(self): self.buffer = b''; self.commands = []
            def __enter__(self): return self
            def __exit__(self, *args): pass
            @property
            def in_waiting(self): return len(self.buffer)
            def write(self, value):
                self.commands.append(value)
                self.buffer += lines[0] if value == b'?\n' else b''.join(lines[1:])
                return len(value)
            def flush(self): pass
            def read(self, n): result, self.buffer = self.buffer[:n], self.buffer[n:]; return result
        port = Port()
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp)/'manifest.json'
            manifest.write_text(json.dumps(dict(kind='eurorack-patterns-daisy-jack-bench', protocol=3,
                                                build_id='0123456789abcdef01234567')))
            args = SimpleNamespace(manifest=manifest, out=Path(tmp)/'capture', notes='synthetic only',
                seconds=10, fault=1, policy=1, trigger=2, fault_delay_slots=0, fault_us=25000,
                port='mock', download_timeout=30)
            with patch.dict(sys.modules, {'serial': SimpleNamespace(Serial=lambda **kw: port)}), \
                 patch.object(jack.secrets, 'randbits', return_value=17), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(jack.capture(args), 0)
            self.assertEqual(port.commands, [b'?\n', b'J,17,10000,1,1,2,0,25000\n'])
            self.assertEqual((args.out/'raw.txt').read_bytes(), data)
            self.assertEqual(json.loads((args.out/'metadata.json').read_text())['status'], 'complete')
            manifest.write_text(manifest.read_text().replace('"protocol": 3', '"protocol": 2'))
            args.out = Path(tmp)/'unsupported'
            with self.assertRaisesRegex(ValueError, 'requires protocol 3'): jack.capture(args)
            self.assertFalse(args.out.exists())


if __name__ == '__main__': unittest.main(argv=[sys.argv[0]])
