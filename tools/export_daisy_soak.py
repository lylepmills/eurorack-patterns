#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Export a complete digital-paired aggregate soak through an explicit allowlist.

Reads saved Saleae data only. Opens no hardware. Failed stimulus or local timing
checks can be retained as explicit counterexamples; incomplete pulse coverage cannot.
"""
import argparse
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
from daisy_scope import inspect_aggregate_service
from export_daisy_trace import public_identity, public_writer, load_capture


def export(source, prefix, pot_ohms, capacitor_nf, expected_status='pass', expected_scope_status='pass'):
    import numpy as np
    from saleae.mso_api.capture import Capture, DigitalData
    assert pot_ohms == 100000 and capacitor_nf == 0, 'Declare the recorded reference fixture explicitly'
    data = (source/'usb/raw.txt').read_bytes()
    summary, controls, buckets = load_capture.parse(data)
    assert controls is None, 'Expected aggregate soak, not a full trace'
    info = public_identity(data, load=True)
    metadata = json.loads((source/'usb/metadata.json').read_text())
    assert metadata['status'] == 'complete' and metadata['stationary'] is True
    writer = public_writer(metadata['writer'])
    load_capture.assess(summary, stationary=True, writer=dict(writer, error=None))
    assert summary['checks']['status'] == expected_status, 'Unexpected quality outcome; review before publishing'
    build = metadata['build']
    assert re.fullmatch('[0-9a-f]{40}', build['source_commit'])
    binary_hash = build['artifacts_sha256']['patterns_daisy.bin']
    assert re.fullmatch('[0-9a-f]{64}', binary_hash)
    assert build['build_id'] == info['build_id']
    native = Capture.from_dir(source/'scope')
    service, button, gesture = [native.digital_data[k] for k in ('service', 'button', 'gesture')]
    assert all(isinstance(ch, DigitalData) for ch in (service, button, gesture))
    scope = inspect_aggregate_service(buckets, service.transition_times, service.initial_state)
    scope_status = 'fail' if scope['mismatched_buckets'] else 'pass'
    assert scope_status == expected_scope_status, 'Unexpected scope outcome; review before publishing'
    edges = np.asarray(service.transition_times)
    first, last = float(edges[0]), float(edges[-1])
    assert first > service.begin_time and last < service.end_time, 'Missing capture margins'
    button_edges = np.asarray(button.transition_times)
    high = bool(button.initial_state) ^ (int(np.count_nonzero(button_edges < first)) % 2 == 1)
    assert high and not np.any((button_edges >= first) & (button_edges <= last)), 'Button moved'
    actions = np.asarray(gesture.transition_times)
    assert not np.any((actions >= first) & (actions <= last)), 'Unexpected action edge'
    scope.update(button_released_throughout=True, action_edges=0)
    excerpt = None
    if scope_status == 'fail':
        # Preserve the first offending second and its preceding context. This
        # is a declared excerpt, never a substitute for full-window coverage.
        last_second = scope['mismatched_buckets'][0]['second']
        first_second = max(0, last_second-1)
        lo, hi = first_second*2000, (last_second+1)*2000
        origin = float(edges[lo]); base_us = first_second*1000000
        normalized = [dict(b, second=b['second']-first_second,
                           first_us=b['first_us']-base_us, last_us=b['last_us']-base_us)
                      for b in buckets[first_second:last_second+1]]
        excerpt = dict(first_original_second=first_second, buckets=normalized,
                       service_edges_s=[float(t)-origin for t in edges[lo:hi]],
                       transformation='Contiguous offending-second excerpt plus preceding second where available. Bucket times subtract the first second boundary; scope times subtract the first selected rising edge. The interval from the preceding excluded pulse is unavailable.')
    compressed = gzip.compress(data, compresslevel=9, mtime=0)
    evidence = dict(schema=1, evidence='Complete stationary aggregate soak with independent digital service pulses',
        acquired_utc=datetime.fromisoformat(metadata['acquired_utc']).isoformat(),
        transformation='Original complete wire bytes, gzip mtime=0. Scope publishes derived counts/extrema/clock scales only. Metadata uses an explicit allowlist.',
        firmware_commit=build['source_commit'], firmware_build_id=info['build_id'],
        firmware_binary_sha256=binary_hash, raw_sha256=hashlib.sha256(data).hexdigest(),
        compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        configuration=summary['configuration'], counters=summary['counters'], host_writer=writer,
        quality_status=summary['checks']['status'], quality_failures=summary['checks']['failures'],
        scope_status=scope_status,
        validation_status='pass' if scope_status == 'pass' and summary['checks']['status'] == 'pass' else 'fail',
        fixture=dict(board='Daisy Seed3', pot_ohms=pot_ohms, capacitor_nf=capacitor_nf,
                     service_hz=1000, scope_api='saleae-mso-api 0.5.8', analog_captured=False),
        scope=scope, mismatch_excerpt=excerpt,
        native_scope_file_sha256=[hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((source/'scope').rglob('*')) if p.is_file()],
        limits='One fixture and declared stationary workload. Aggregates do not retain individual observations or prove pickup/gesture behavior during movement. Digital-only scope; analog preflights are separate. Synthetic callback padding, not production DSP or audio-quality qualification. Host pacing is best effort; reported quality failures remain failures.')
    raw_path, meta_path = prefix.with_suffix('.txt.gz'), prefix.with_suffix('.json')
    assert not raw_path.exists() and not meta_path.exists(), 'Use a fresh export prefix'
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(compressed); meta_path.write_text(json.dumps(evidence, indent=2)+'\n')
    assert gzip.decompress(raw_path.read_bytes()) == data
    print(prefix.name, scope['samples'], 'aggregate samples; machine:', expected_status, 'scope:', scope_status)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--out-prefix', type=Path, required=True)
    p.add_argument('--pot-ohms', type=int, required=True)
    p.add_argument('--capacitor-nf', type=float, required=True)
    p.add_argument('--expected-status', choices=('pass', 'fail'), default='pass')
    p.add_argument('--expected-scope-status', choices=('pass', 'fail'), default='pass')
    a = p.parse_args()
    export(a.capture, a.out_prefix, a.pot_ohms, a.capacitor_nf, a.expected_status, a.expected_scope_status)
