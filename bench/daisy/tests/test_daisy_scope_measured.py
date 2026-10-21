#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Verify recorded scope metadata against the public export allowlist."""
import gzip
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
from export_daisy_trace import check_identity, public_identity


class MeasuredExportPrivacyTests(unittest.TestCase):
    def test_new_identity_fields_require_review(self):
        path = Path(__file__).resolve().parent/'measured/daisy/2026-10-16-load/baseline.txt.gz'
        info = json.loads(gzip.decompress(path.read_bytes()).splitlines()[0][5:])
        check_identity(info, load=True)
        check_identity(dict(info, timing_diagnostics=1), load=True)
        check_identity(dict(info, fault_timing=1), load=True)
        for value in (0, 2, True, '1', 'private text'):
            with self.assertRaises(AssertionError): check_identity(dict(info, fault_timing=value), load=True)
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


if __name__ == '__main__':
    unittest.main()
