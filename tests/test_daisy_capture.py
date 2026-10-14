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
    end[-2] = str(capture.fnv(b''.join(lines[3:-1])))
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

    def fake_capture(self, td, *, disconnect=False, wrong_identity=False):
        data = self.data
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
                else:
                    token = command.decode().split(',')[1]
                    lines[1] = lines[1].replace(b'START,42,', ('START,' + token + ',').encode())
                    lines[-1] = lines[-1].replace(b'END,42,', ('END,' + token + ',').encode())
                    self.pending = b''.join(lines[1:])
                    if disconnect: self.pending = self.pending[:-100]
                return len(command)
            def read_until(self, terminator, size):
                if not self.pending: raise OSError('synthetic disconnect')
                stop = min(len(self.pending), size, 17)
                nl = self.pending.find(b'\n', 0, stop)
                if nl >= 0: stop = nl + 1
                result, self.pending = self.pending[:stop], self.pending[stop:]
                return result
        root = Path(td); binary = root / 'patterns_daisy.bin'; binary.write_bytes(b'synthetic binary')
        manifest = root / 'manifest.json'
        manifest.write_text(json.dumps(dict(kind='eurorack-patterns-daisy-bench', protocol=1,
            build_id='synthetic', artifacts_sha256={'patterns_daisy.bin': hashlib.sha256(binary.read_bytes()).hexdigest()})))
        a = argparse.Namespace(manifest=manifest, out=root / 'capture', port='mock-only',
            scenario='manual', seconds=6, target=0.25, pot_ohms=100000, capacitor_nf=0,
            probe='synthetic', notes='synthetic', download_timeout=5, replay=REPLAY)
        with patch.dict(sys.modules, {'serial': types.SimpleNamespace(Serial=Serial)}), contextlib.redirect_stdout(io.StringIO()):
            if disconnect or wrong_identity:
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
        port = types.SimpleNamespace(read_until=lambda *args: b'partial')
        with patch.object(capture.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                capture.read_line(port, raw, 1)
        self.assertEqual(raw.getvalue(), b'partial')

    def test_unknown_firmware_never_receives_run_command(self):
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake_capture(td, wrong_identity=True)
            self.assertEqual(writes, [b'?\n'])
            self.assertEqual(json.loads((out / 'metadata.json').read_text())['status'], 'incomplete')

if __name__ == '__main__':
    unittest.main()
