#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Inspect saved timing evidence without opening hardware or changing acceptance.

The digital reader implements Saleae's documented little-endian version 1
format: https://github.com/saleae/gitbook-docs/blob/master/getting-help/troubleshooting/technical-faq/binary-and-csv-export-formats-2025-update.md
Only one continuous digital chunk is supported; gaps are never joined.
"""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import load_capture
from daisy_scope import inspect_service, inspect_aggregate_service, inspect_timing_service


def read_digital(raw):
    if len(raw) < 60:
        raise ValueError('Truncated digital header')
    if struct.unpack_from('<8siiQ', raw) != (b'<SALEAE>', 1, 0, 1):
        raise ValueError('Require version 1 digital data with exactly one continuous chunk')
    initial, rate, begin, end, count = struct.unpack_from('<IdddQ', raw, 24)
    if (initial not in (0, 1) or not all(math.isfinite(v) for v in (rate, begin, end))
            or rate <= 0 or end <= begin or len(raw) != 60 + count*8):
        raise ValueError('Invalid digital chunk dimensions')
    edges = array('d'); edges.frombytes(raw[60:])
    if sys.byteorder != 'little': edges.byteswap()
    if (any(not math.isfinite(t) or t < begin or t > end for t in edges)
            or any(a >= b for a, b in zip(edges, edges[1:]))):
        raise ValueError('Invalid digital transitions')
    return bool(initial), edges


def inspect(raw, digital):
    initial, edges = read_digital(digital)
    summary, controls, buckets = load_capture.parse(raw)
    if controls is not None:
        _, _, rows = load_capture.capture.parse(controls)
        report = inspect_service(rows, edges, initial, local_seconds=1)[2]
    else:
        report = dict(aggregate=inspect_aggregate_service(buckets, edges, initial))
        report['status'] = 'fail' if report['aggregate']['mismatched_buckets'] else 'pass'
        if summary['configuration']['mode'] == 2:
            report['witnesses'] = inspect_timing_service(buckets, edges, summary['counters']['timer_hz'], initial)
    return dict(schema=1, wire_sha256=hashlib.sha256(raw).hexdigest(),
        digital_sha256=hashlib.sha256(digital).hexdigest(), timing=report,
        limitation='Timing inspection only. A pass does not qualify behavior, load, or identify a fault source; local fits never override global acceptance.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--digital', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    report = inspect(a.raw.read_bytes(), a.digital.read_bytes())
    # Preserve failed diagnostics; never overwrite an earlier review.
    with a.out.open('x') as out:
        out.write(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print('Timing:', report['timing']['status'], '(diagnostic report saved; original evidence unchanged)')
    return 1 if report['timing']['status'] == 'fail' else 0


if __name__ == '__main__':
    sys.exit(main())
