#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Synthetic protocol and mocked-serial tests. Never opens a hardware device."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture', ROOT / 'examples/daisy/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
REPLAY = Path(sys.argv.pop(1)).resolve()

def synthetic(scenario=0):
    return subprocess.check_output([str(REPLAY), '--synthetic', str(scenario)])

def rehash(data):
    lines = data.splitlines(keepends=True)
    end = lines[-1].decode().strip().split(',')
    end[-2] = str(capture.fnv(b''.join(x for x in lines if x.startswith((b'STIMULUS,', b'D,')))))
    lines[-1] = (','.join(end) + '\n').encode()
    return b''.join(lines)

class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = synthetic()

    def test_all_scenarios_roundtrip(self):
        for scenario in range(5):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as td:
                out = Path(td); data = synthetic(scenario)
                self.assertNotIn(b'\r', data) # Firmware emits LF on every host OS.
                (out / 'raw.txt').write_bytes(data)
                summary = capture.save_analysis(data, out, 'synthetic', REPLAY)
                self.assertEqual(summary['protocol_integrity'], 'verified')
                self.assertIn('PASS:', summary['replay'])
                self.assertEqual(summary['taps'], 1)
                self.assertEqual(summary['holds'], 1)
                self.assertEqual(summary['invalid_samples'], 250 if scenario == 2 else 0)
                self.assertEqual(summary['run']['missed'], 25 if scenario == 3 else 0)
                self.assertEqual(summary['cadence_breaks'], 1 if scenario == 3 else 0)
                self.assertTrue((out / 'samples.csv').is_file())

    def test_original_scenarios_with_protocol_two(self):
        for scenario in range(5):
            data = subprocess.check_output([str(REPLAY), '--synthetic-v2', str(scenario)])
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as td:
                out = Path(td); (out / 'raw.txt').write_bytes(data)
                summary = capture.save_analysis(data, out, 'synthetic', REPLAY)
                self.assertEqual(summary['run']['stimulus_status'], 'not_applicable')
                self.assertEqual(capture.result_code(summary), 0)

    def test_missing_startup_is_not_replaced_with_new_run(self):
        with tempfile.TemporaryDirectory() as td:
            _, writes = self.fake_capture(td, scenario=12, startup_unavailable=True)
            self.assertEqual(writes, [b'?\n'])

    def test_event_and_startup_scenarios_roundtrip(self):
        expected_actions = {5: (1, 0), 6: (1, 0), 7: (1, 0), 8: (2, 0),
                            9: (0, 0), 10: (0, 0), 11: (0, 0), 12: (1, 0)}
        for scenario in range(5, 13):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as td:
                out = Path(td); data = synthetic(scenario)
                (out / 'raw.txt').write_bytes(data)
                summary = capture.save_analysis(data, out, 'synthetic', REPLAY)
                self.assertEqual((summary['taps'], summary['holds']), expected_actions[scenario])
                self.assertEqual(summary['run']['stimulus_status'], 'not_applicable' if scenario == 12 else 'completed')
                self.assertEqual(capture.result_code(summary), 0)
                if scenario == 12:
                    self.assertTrue(summary['run']['startup_held'])
                    self.assertEqual(summary['samples'], 20000)

    def test_event_evidence_is_checked_and_checksummed(self):
        data = synthetic(5)
        corrupt = data.replace(b'STIMULUS,200000,300000,325000', b'STIMULUS,200001,300000,325000')
        with self.assertRaisesRegex(ValueError, 'checksum'): capture.parse(corrupt)
        with self.assertRaisesRegex(ValueError, 'trigger'): capture.parse(rehash(corrupt))
        early = data.replace(b'STIMULUS,200000,300000,325000', b'STIMULUS,200000,299999,325000')
        with self.assertRaisesRegex(ValueError, 'deadline'): capture.parse(rehash(early))
        missing = data.replace(b'STIMULUS,200000,300000,325000', b'STIMULUS,-1,-1,-1')
        with self.assertRaisesRegex(ValueError, 'trigger'): capture.parse(rehash(missing))

    def test_unexercised_or_incomplete_scenario_is_not_success(self):
        rows = [dict(time_us=0, pressed=0, adc_valid=1, raw=0),
                dict(time_us=990000, pressed=1, adc_valid=1, raw=0)]
        status = capture.validate_stimulus(5, [990000, -1, -1], rows, False, 1000000)
        self.assertEqual(status, 'incomplete')
        rows[-1]['pressed'] = 0
        self.assertEqual(capture.validate_stimulus(5, [-1, -1, -1], rows, False, 1000000), 'not_triggered')
        for status in ('incomplete', 'not_triggered'):
            summary = dict(run=dict(adc_failures=0, rx_dropped=0, buffer_overflow=0, stimulus_status=status))
            self.assertEqual(capture.result_code(summary), 3)

    def test_startup_download_uses_retained_capture_command(self):
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake_capture(td, scenario=12)
            self.assertEqual(writes[0], b'?\n')
            self.assertTrue(writes[1].startswith(b'B,'))
            self.assertFalse(any(w.startswith(b'R,') for w in writes))
            summary = json.loads((out / 'summary.json').read_text())
            self.assertTrue(summary['run']['startup_held'])

    def test_pending_startup_cannot_be_overwritten_by_normal_run(self):
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake_capture(td, scenario=5, startup_pending=True)
            self.assertEqual(writes, [b'?\n'])
            self.assertEqual(json.loads((out / 'metadata.json').read_text())['status'], 'incomplete')

    def test_corrupt_or_incomplete_capture_rejected(self):
        lines = self.data.splitlines(keepends=True)
        bad = [self.data[:-1], b''.join(lines[:-1]), b''.join(lines[:3] + lines[4:]),
               b''.join(lines[:4] + [lines[3]] + lines[4:]), self.data + b'junk\n',
               self.data.replace(b'"protocol":1', b'"protocol":2')]
        corrupt = self.data.replace(b'D,0,0,35,40,0,', b'D,0,0,35,40,1,', 1)
        bad.append(corrupt)
        for data in bad:
            with self.subTest(size=len(data)), self.assertRaises((ValueError, json.JSONDecodeError)):
                capture.parse(data)
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            capture.parse(self.data, 'wrong')

    def test_invalid_application_and_accounting_rejected(self):
        for column, value in [('raw', '65536'), ('missed', '1'), ('actions', '1'),
                              ('cadence_valid', '0'), ('adc_valid', '0')]:
            lines = self.data.splitlines(keepends=True)
            row = lines[3].decode().strip().split(',')
            row[capture.COLUMNS.index(column) + 1] = value
            lines[3] = (','.join(row) + '\n').encode()
            with self.subTest(column=column), self.assertRaises(ValueError):
                capture.parse(rehash(b''.join(lines)))

    def test_replay_detects_semantic_difference_even_with_valid_checksum(self):
        lines = self.data.splitlines(keepends=True)
        row = lines[3].decode().strip().split(',')
        row[capture.COLUMNS.index('value_ppm') + 1] = '250100'
        lines[3] = (','.join(row) + '\n').encode()
        data = rehash(b''.join(lines))
        capture.parse(data) # Transport integrity alone cannot prove behavior.
        with tempfile.TemporaryDirectory() as td:
            out = Path(td); (out / 'raw.txt').write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'replay failed'):
                capture.save_analysis(data, out, replay=REPLAY)

    def fake_capture(self, td, *, disconnect=False, wrong_identity=False, scenario=0, startup_pending=False, startup_unavailable=False):
        data = synthetic(scenario)
        class Serial:
            writes = []
            def __init__(self, **kwargs): self.pending = b''
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def flush(self): pass
            def write(self, command):
                self.writes.append(command)
                lines = data.splitlines(keepends=True)
                if command == b'?\n':
                    self.pending = lines[0]
                    if wrong_identity: self.pending = self.pending.replace(b'synthetic', b'unknown')
                    if startup_pending: self.pending = self.pending.replace(b'"startup_available":false', b'"startup_available":true')
                    if startup_unavailable: self.pending = self.pending.replace(b'"startup_available":true', b'"startup_available":false')
                else:
                    token = command.decode().strip().split(',')[1]
                    lines[1] = lines[1].replace(b'START,42,', ('START,' + token + ',').encode())
                    lines[-1] = lines[-1].replace(b'END,42,', ('END,' + token + ',').encode())
                    self.pending = b''.join(lines[1:])
                    if disconnect: self.pending = self.pending[:-100]
                return len(command)
            @property
            def in_waiting(self): return len(self.pending)
            def read(self, size):
                if not self.pending: raise OSError('synthetic disconnect')
                stop = min(len(self.pending), size, 17)
                result, self.pending = self.pending[:stop], self.pending[stop:]
                return result
        root = Path(td); binary = root / 'patterns_daisy.bin'; binary.write_bytes(b'synthetic binary')
        manifest = root / 'manifest.json'
        manifest.write_text(json.dumps(dict(kind='eurorack-patterns-daisy-bench', protocol=2 if scenario >= 5 else 1,
            build_id='synthetic', artifacts_sha256={'patterns_daisy.bin': hashlib.sha256(binary.read_bytes()).hexdigest()})))
        a = argparse.Namespace(manifest=manifest, out=root / 'capture', port='mock-only',
            scenario=next(k for k,v in capture.SCENARIOS.items() if v == scenario), seconds=20 if scenario == 12 else 6, target=0.25, pot_ohms=100000, capacitor_nf=0,
            probe='synthetic', notes='synthetic', download_timeout=5, replay=REPLAY)
        with patch.dict(sys.modules, {'serial': types.SimpleNamespace(Serial=Serial)}), contextlib.redirect_stdout(io.StringIO()):
            if disconnect or wrong_identity or startup_pending or startup_unavailable:
                with self.assertRaises((ValueError, OSError)): capture.capture(a)
            else:
                self.assertEqual(capture.capture(a), 0)
        return a.out, Serial.writes

    def test_mock_serial_capture_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake_capture(td)
            self.assertEqual(len(writes), 2)
            metadata = json.loads((out / 'metadata.json').read_text())
            self.assertEqual(metadata['status'], 'complete')
            self.assertNotIn('mock-only', (out / 'metadata.json').read_text())

    def test_disconnect_preserves_partial_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            out, _ = self.fake_capture(td, disconnect=True)
            self.assertEqual(json.loads((out / 'metadata.json').read_text())['status'], 'incomplete')
            self.assertGreater((out / 'raw.txt').stat().st_size, 1000)
            self.assertFalse((out / 'summary.json').exists())

    def test_timeout_preserves_partial_line(self):
        raw = io.BytesIO()
        port = types.SimpleNamespace(in_waiting=7, read=lambda size: b'partial')
        with patch.object(capture.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                capture.LineReader(port, raw).read_line(1)
        self.assertEqual(raw.getvalue(), b'partial')

    def test_fragmented_and_coalesced_lines_preserved(self):
        chunks = iter([b'fi', b'rst\nsecond\npar', b'tial'])
        port = types.SimpleNamespace(in_waiting=64, read=lambda size: next(chunks))
        raw = io.BytesIO(); reader = capture.LineReader(port, raw)
        self.assertEqual(reader.read_line(float('inf')), b'first\n')
        self.assertEqual(reader.read_line(float('inf')), b'second\n')
        with patch.object(capture.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaises(TimeoutError): reader.read_line(1)
        self.assertEqual(raw.getvalue(), b'first\nsecond\npartial')

    def test_large_burst_uses_block_reads_without_losing_bytes(self):
        line = b'D,12345,12345000,139,140,32768\n'
        payload = line * 100000
        source = io.BytesIO(payload); reads = []
        def read(size):
            reads.append(size)
            return source.read(size)
        port = types.SimpleNamespace(in_waiting=len(payload), read=read)
        raw = io.BytesIO(); reader = capture.LineReader(port, raw)
        for _ in range(100000):
            self.assertEqual(reader.read_line(float('inf')), line)
        self.assertEqual(raw.getvalue(), payload)
        self.assertLess(len(reads), 100)
        self.assertFalse(reader.pending)

    def test_oversized_line_preserves_received_chunk(self):
        for malformed in (b'x' * 4096, b'x' * 4095 + b'\n'):
            chunk = b'ok\n' + malformed
            port = types.SimpleNamespace(in_waiting=len(chunk), read=lambda size: chunk)
            raw = io.BytesIO(); reader = capture.LineReader(port, raw)
            self.assertEqual(reader.read_line(float('inf')), b'ok\n')
            with self.assertRaisesRegex(ValueError, 'oversized'):
                reader.read_line(float('inf'))
            self.assertEqual(raw.getvalue(), chunk)

    def test_unknown_firmware_never_receives_run_command(self):
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake_capture(td, wrong_identity=True)
            self.assertEqual(writes, [b'?\n'])
            self.assertEqual(json.loads((out / 'metadata.json').read_text())['status'], 'incomplete')

if __name__ == '__main__':
    unittest.main()
