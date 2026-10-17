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
REPLAY = Path(sys.argv[1])
DATA = ROOT/'tests/measured/daisy/2026-10-16-load'

for name, padding, usb in [('baseline', -1, 0), ('audio-dma', 0, 0), ('combined', 650, 500)]:
    meta = json.loads((DATA/(name+'.json')).read_text())
    compressed = (DATA/(name+'.txt.gz')).read_bytes()
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(compressed).hexdigest() == meta['compressed_sha256']
    assert hashlib.sha256(raw).hexdigest() == meta['raw_sha256']
    writer = dict(meta['load']['host_writer'], error=None)
    with tempfile.TemporaryDirectory() as td:
        summary = load_capture.save_analysis(raw, Path(td), meta['firmware_build_id'], REPLAY, True, writer)
    assert summary['checks']['status'] == 'pass', summary['checks']
    assert '10000 samples replayed' in summary['replay']
    assert summary['configuration'] == meta['load']['configuration']
    assert summary['counters'] == meta['load']['counters']
    c = summary['configuration']
    assert (c['mode'], c['duration_ms'], c['audio_permille'], c['block_size'], c['usb_hz']) == (0, 10000, padding, 16, usb)
    assert summary['counters']['samples'] == meta['samples'] == 10000
    _, controls, _ = load_capture.parse(raw)
    _, _, rows = load_capture.capture.parse(controls)
    assert all(r['adc_valid'] and not r['pressed'] and not r['gesture'] for r in rows)
    assert all(r['state'] == 1 and r['value_ppm'] == 250000 and not r['changed'] for r in rows)
    scope = meta['scope']
    assert scope['service_pulses'] == 10000 and scope['sampled_button_disagreements'] == 0
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
    print('PASS:', name, '10000 measured controls replayed; scope counts/timing/inputs checked')
