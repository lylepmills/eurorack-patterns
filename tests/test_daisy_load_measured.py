#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Replay complete load windows and check the independently recorded scope evidence."""
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import load_capture
sys.path.insert(0, str(ROOT/'tools'))
from daisy_scope import inspect_aggregate_service, match_aggregate_service
REPLAY = Path(sys.argv[1])
DATA = ROOT/'tests/measured/daisy/2026-10-16-load'

for name, padding, usb, block, count, status in [
        ('baseline', -1, 0, 16, 10000, 'pass'), ('audio-dma', 0, 0, 16, 10000, 'pass'),
        ('combined', 650, 500, 16, 10000, 'pass'), ('boundary-96', 650, 0, 96, 8407, 'fail')]:
    meta = json.loads((DATA/(name+'.json')).read_text())
    compressed = (DATA/(name+'.txt.gz')).read_bytes()
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(compressed).hexdigest() == meta['compressed_sha256']
    assert hashlib.sha256(raw).hexdigest() == meta['raw_sha256']
    writer = dict(meta['load']['host_writer'], error=None)
    with tempfile.TemporaryDirectory() as td:
        summary = load_capture.save_analysis(raw, Path(td), meta['firmware_build_id'], REPLAY, True, writer)
    assert summary['checks']['status'] == status, summary['checks']
    assert summary['checks']['failures'] == ([] if status == 'pass' else ['missed'])
    assert meta['load'].get('quality_status', 'pass') == status
    assert meta['load'].get('quality_failures', []) == summary['checks']['failures']
    assert f'{count} samples replayed' in summary['replay']
    assert summary['configuration'] == meta['load']['configuration']
    assert summary['counters'] == meta['load']['counters']
    c = summary['configuration']
    assert (c['mode'], c['duration_ms'], c['audio_permille'], c['block_size'], c['usb_hz']) == (0, 10000, padding, block, usb)
    assert summary['counters']['samples'] == meta['samples'] == count
    _, controls, _ = load_capture.parse(raw)
    _, _, rows = load_capture.capture.parse(controls)
    assert all(r['adc_valid'] and not r['pressed'] and not r['gesture'] for r in rows)
    assert all(r['state'] == 1 and r['value_ppm'] == 250000 and not r['changed'] for r in rows)
    scope = meta['scope']
    assert scope['service_pulses'] == count and scope['sampled_button_disagreements'] == 0
    assert scope['button_initial_high'] and not scope['button_edges_s'] and not scope['action_edges_s']
    alignment = scope['alignment']
    assert not alignment['pre_application_high_intervals_s']
    assert alignment['max_fit_residual_us'] < 5 and alignment['max_interval_error_us'] < 5
    assert alignment['max_work_width_error_us'] < 3
    scale = 1 + alignment['clock_scale_ppm']/1e6
    assert abs(scope['service_interval_us']['max']/scale-summary['max_control_interval_us']) < 3
    assert abs(scope['service_width_us']['max']/scale-summary['max_control_work_us']) < 3
    # This recorded midpoint is a fixture observation, not an ADC calibration.
    medians = scope['analog']['median_volts']
    assert len(medians) >= 990 and all(1.4 < v < 1.65 for v in medians)
    adc_mid = statistics.median(r['raw'] for r in rows)/65535*3.3
    assert abs(statistics.median(medians)-adc_mid) < .15
    if status == 'fail':
        assert summary['counters']['missed'] == 1593
        assert summary['counters']['callback_over_budget'] == summary['counters']['late_callback_intervals'] == 0
    print('PASS:', name, count, 'controls replayed; observed workload quality:', status, '(expected)')

# A complete long soak can pass machine counters and still fail independent timing.
meta = json.loads((DATA/'soak-30m.json').read_text())
compressed = (DATA/'soak-30m.txt.gz').read_bytes(); raw = gzip.decompress(compressed)
assert hashlib.sha256(compressed).hexdigest() == meta['compressed_sha256']
assert hashlib.sha256(raw).hexdigest() == meta['raw_sha256']
summary, controls, buckets = load_capture.parse(raw, meta['firmware_build_id'])
assert controls is None and len(buckets) == 1800
assert load_capture.assess(summary, True, dict(meta['host_writer'], error=None))
assert meta['quality_status'] == 'pass' and meta['scope_status'] == meta['validation_status'] == 'fail'
assert summary['counters'] == meta['counters'] and summary['configuration'] == meta['configuration']
assert summary['counters']['samples'] == meta['scope']['samples'] == 1800000
assert sum(b['samples'] for b in buckets) == 1800000 and summary['actions'] == 0
assert [b['second'] for b in meta['scope']['mismatched_buckets']] == [1611, 1621, 1622, 1624, 1630, 1640, 1649, 1659, 1668]
# Whole-run maxima alone would miss these local disagreements.
assert abs(meta['scope']['max_service_interval_us']-summary['max_control_interval_us']) < 3
assert abs(meta['scope']['max_service_width_us']-summary['max_control_work_us']) < 3
excerpt = meta['mismatch_excerpt']; first = excerpt['first_original_second']
assert first == 1610 and len(excerpt['buckets']) == 2 and len(excerpt['service_edges_s']) == 4000
for i, b in enumerate(excerpt['buckets']):
    original = buckets[first+i]
    assert b == dict(original, second=i, first_us=original['first_us']-first*1000000, last_us=original['last_us']-first*1000000)
report = inspect_aggregate_service(excerpt['buckets'], excerpt['service_edges_s'])
assert any(b['second'] == 1 and b['work_width_error_us'] > 13 for b in report['mismatched_buckets'])
try:
    match_aggregate_service(excerpt['buckets'], excerpt['service_edges_s'])
except ValueError as error:
    assert 'maxima disagree' in str(error)
else:
    raise AssertionError('Recorded long-soak timing disagreement was silently accepted')
print('PASS: complete 30-minute machine trace retained; recorded scope disagreement rejected, not qualified')
