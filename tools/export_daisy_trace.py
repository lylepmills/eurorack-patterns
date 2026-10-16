#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Export a complete paired capture using a strict public-data allowlist.

Needs saleae-mso-api only to read the saved native capture; opens no hardware.
Original wire bytes are losslessly compressed, never trimmed or synthesized.
"""
import argparse
from datetime import datetime
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture', ROOT / 'examples/daisy/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

def export(source, prefix):
    from saleae.mso_api.capture import Capture, DigitalData
    data = (source / 'usb/raw.txt').read_bytes()
    info, run, rows = capture.parse(data)
    allowed = {'protocol', 'build_id', 'board', 'ready', 'cpu_hz', 'timer_hz', 'adc_hz',
               'mcu_revision', 'sample_cycles_x2', 'oversampling', 'period_us', 'max_records'}
    assert set(info) == allowed, 'Review new identity fields before publishing'
    assert re.fullmatch('[0-9a-f]{24}', info['build_id'])
    assert all(type(v) in (int, bool) for k, v in info.items() if k not in ('build_id', 'board'))
    assert all(run[k] == 0 for k in ('adc_failures', 'rx_dropped', 'buffer_overflow'))
    metadata = json.loads((source / 'usb/metadata.json').read_text())
    build = metadata['build']
    assert re.fullmatch('[0-9a-f]{40}', build['source_commit'])
    assert re.fullmatch('[0-9a-f]{64}', build['artifacts_sha256']['patterns_daisy.bin'])
    native = Capture.from_dir(source / 'scope')
    service, button, gesture = [native.digital_data[k] for k in ('service', 'button', 'gesture')]
    assert all(isinstance(x, DigitalData) for x in (service, button, gesture))
    assert not service.initial_state
    rises, falls = service.transition_times[::2], service.transition_times[1::2]
    assert len(rises) == len(falls) == len(rows)
    assert rises[0] > service.begin_time and falls[-1] < service.end_time
    assert all(a < b for a, b in zip(rises, falls))
    origin, last = float(rises[0]), float(falls[-1])
    actions = [float(t) for t in gesture.transition_times if origin <= t <= last]
    action_rows = [i for i, row in enumerate(rows) if row['gesture']]
    assert len(actions) == len(action_rows)
    assert all(rises[i] <= t <= falls[i] for i, t in zip(action_rows, actions))
    edges = [float(t) for t in button.transition_times]
    state, j = bool(button.initial_state), 0
    for rise, row in zip(rises, rows):
        while j < len(edges) and edges[j] <= rise:
            state = not state
            j += 1
        assert int(not state) == row['pressed'], 'Scope/button disagreement'
    compressed = gzip.compress(data, compresslevel=9, mtime=0)
    raw_path = prefix.with_suffix('.txt.gz')
    meta_path = prefix.with_suffix('.json')
    assert not raw_path.exists() and not meta_path.exists(), 'Use a fresh export prefix'
    evidence = dict(
        schema=1, evidence='measured physical inputs; software-injected ADC gaps remain explicitly flagged',
        transformation='Original USB wire bytes, complete window, gzip with mtime=0. Scope edge times relative to first service rising edge; metadata copied only from explicit allowlist.',
        acquired_utc=datetime.fromisoformat(metadata['acquired_utc']).isoformat(),
        firmware_commit=build['source_commit'], firmware_build_id=info['build_id'],
        firmware_binary_sha256=build['artifacts_sha256']['patterns_daisy.bin'],
        raw_sha256=hashlib.sha256(data).hexdigest(), compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        samples=len(rows), scenario=run['scenario'],
        fixture=dict(board='Daisy Seed3', pot_ohms=100000, capacitor_nf=0,
                     service_hz=1000, adc_bits=16, sample_cycles=810.5, probe_attenuation=10,
                     scope_api='saleae-mso-api 0.5.8', analog_sample_rate_hz=1000000),
        scope=dict(service_pulses=len(rises), sampled_button_disagreements=0,
                   button_initial_high=bool(button.initial_state) ^ (sum(t < origin for t in edges) % 2 == 1),
                   button_edges_s=[t - origin for t in edges if origin <= t <= last],
                   action_edges_s=[t - origin for t in actions],
                   action_service_windows_s=[[float(rises[i])-origin, float(falls[i])-origin] for i in action_rows]),
        native_scope_file_sha256=[hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((source/'scope').rglob('*')) if p.is_file()],
        limits='One fixture. Scope timings include its clock scale relative to the MCU. No calibrated voltage, universal threshold, power-cycle, audio-load or jack-detection claim. Full private native originals retained; published digital edges are a derived subset.')
    assert metadata['declared_fixture']['pot_ohms'] == 100000
    assert metadata['declared_fixture']['capacitor_nf'] == 0
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(compressed)
    meta_path.write_text(json.dumps(evidence, indent=2) + '\n')
    assert gzip.decompress(raw_path.read_bytes()) == data
    print(prefix.name, len(rows), 'samples, public allowlist and paired coverage verified')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--out-prefix', type=Path, required=True)
    args = parser.parse_args()
    export(args.capture, args.out_prefix)
