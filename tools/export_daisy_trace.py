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
import math
from pathlib import Path
import re
import sys
from daisy_scope import match_service

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture', ROOT / 'examples/daisy/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
sys.path.insert(0, str(ROOT / 'examples/daisy'))
import load_capture

def check_identity(info, load=False):
    assert info['board'] == 'seed3' and info['protocol'] in (1, 2) and info['ready'] is True
    allowed = {'protocol', 'build_id', 'board', 'ready', 'cpu_hz', 'timer_hz', 'adc_hz',
               'mcu_revision', 'sample_cycles_x2', 'oversampling', 'period_us', 'max_records'}
    if info['protocol'] == 2:
        allowed |= {'startup_available', 'startup_duration_ms'}
    if load:
        allowed.add('load_protocol')
    assert set(info) == allowed, 'Review new identity fields before publishing'
    assert re.fullmatch('[0-9a-f]{24}', info['build_id'])
    assert all(type(v) in (int, bool) for k, v in info.items() if k not in ('build_id', 'board'))


def public_identity(data, load=False):
    # Keep the original wire bytes, so reject duplicate fields that a normal
    # dict parser would discard before the public-data allowlist sees them.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, 'Duplicate identity field'
            result[key] = value
        return result
    line = data.split(b'\n', 1)[0]
    assert line.startswith(b'INFO,')
    info = json.loads(line[5:], object_pairs_hook=unique)
    check_identity(info, load)
    return info


def public_writer(writer):
    assert writer['error'] is None, 'Do not publish arbitrary host error text'
    assert all(type(writer[k]) is int and writer[k] >= 0 for k in ('packets', 'skipped_slots'))
    assert (type(writer['max_lateness_s']) in (int, float)
            and math.isfinite(writer['max_lateness_s']) and writer['max_lateness_s'] >= 0)
    return {k: writer[k] for k in ('packets', 'skipped_slots', 'max_lateness_s')}


def export(source, prefix, startup_kind=None, load=False, pot_ohms=None, capacitor_nf=None):
    import numpy as np
    from saleae.mso_api.capture import Capture, DigitalData, AnalogData
    data = (source / 'usb/raw.txt').read_bytes()
    metadata = json.loads((source / 'usb/metadata.json').read_text())
    workload = None
    control_data = data
    if load:
        workload, control_data, _ = load_capture.parse(data)
        assert control_data is not None, 'Aggregate soaks have no individual scope-matched control trace'
        assert metadata['status'] == 'complete'
        assert metadata['stationary'] is True, 'This load exporter expects a stationary reference window'
        assert load_capture.assess(workload, metadata['stationary'], metadata['writer']), 'Failed load window'
        assert pot_ohms == 100000 and capacitor_nf == 0, 'Declare the recorded reference fixture explicitly'
    _, run, rows = capture.parse(control_data)
    info = public_identity(data, load)
    if load:
        assert all(not r['pressed'] and not r['gesture'] for r in rows), 'Expected released button throughout'
    assert all(run[k] == 0 for k in ('adc_failures', 'rx_dropped', 'buffer_overflow'))
    assert (startup_kind in ('reset', 'usb-power-cycle')) == (run['scenario'] == 12)
    assert run.get('stimulus_status', 'not_applicable') in ('completed', 'not_applicable')
    build = metadata['build']
    assert build['build_id'] == info['build_id'], 'Manifest and recorded build differ'
    assert re.fullmatch('[0-9a-f]{40}', build['source_commit'])
    assert re.fullmatch('[0-9a-f]{64}', build['artifacts_sha256']['patterns_daisy.bin'])
    native = Capture.from_dir(source / 'scope')
    service, button, gesture = [native.digital_data[k] for k in ('service', 'button', 'gesture')]
    assert all(isinstance(x, DigitalData) for x in (service, button, gesture))
    assert not service.initial_state
    rises, falls, alignment = match_service(rows, service.transition_times,
                                            bool(service.initial_state), run['scenario'] == 12)
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
    analog = native.analog_data['pot']
    assert isinstance(analog, AnalogData), 'Discontinuous analog trace'
    # Derived voltage evidence only: retain 10 ms block medians, not private
    # vendor metadata. Rounding does not imply microvolt measurement accuracy.
    block = int(analog.sample_rate * .010)
    start = int((origin - analog.begin_time) * analog.sample_rate)
    end = int((last - analog.begin_time) * analog.sample_rate)
    assert block > 0 and 0 <= start < end <= analog.num_samples
    n = (end - start) // block
    medians = np.median(np.asarray(analog.voltages[start:start+n*block]).reshape(n, block), axis=1)
    assert np.all(np.isfinite(medians)), 'Invalid analog evidence'
    analog_evidence = dict(period_s=block/analog.sample_rate,
                          first_center_s=analog.begin_time+(start+block/2)/analog.sample_rate-origin,
                          median_volts=[round(float(v), 6) for v in medians],
                          note='10 ms block medians rounded to six decimals; not calibrated voltage accuracy.')
    pre_analog = None
    if startup_kind:
        count = start // block
        assert count > 0
        before = np.median(np.asarray(analog.voltages[:count*block]).reshape(count, block), axis=1)
        assert np.all(np.isfinite(before)), 'Invalid pre-application analog evidence'
        pre_analog = dict(period_s=block/analog.sample_rate,
                         first_center_s=analog.begin_time+block/2/analog.sample_rate-origin,
                         median_volts=[round(float(v), 6) for v in before])
    compressed = gzip.compress(data, compresslevel=9, mtime=0)
    raw_path = prefix.with_suffix('.txt.gz')
    meta_path = prefix.with_suffix('.json')
    assert not raw_path.exists() and not meta_path.exists(), 'Use a fresh export prefix'
    evidence = dict(
        schema=2, evidence='measured physical inputs; software-injected ADC gaps remain explicitly flagged',
        transformation='Original USB wire bytes, complete window, gzip with mtime=0. Scope times relative to first application service edge; 10 ms analog medians rounded to six decimals; metadata copied only from explicit allowlist.',
        acquired_utc=datetime.fromisoformat(metadata['acquired_utc']).isoformat(),
        firmware_commit=build['source_commit'], firmware_build_id=info['build_id'],
        firmware_binary_sha256=build['artifacts_sha256']['patterns_daisy.bin'],
        raw_sha256=hashlib.sha256(data).hexdigest(), compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        samples=len(rows), scenario=run['scenario'], startup_kind=startup_kind,
        fixture=dict(board='Daisy Seed3', pot_ohms=100000, capacitor_nf=0,
                     service_hz=1000, adc_bits=16, sample_cycles=810.5, probe_attenuation=10,
                     scope_api='saleae-mso-api 0.5.8', analog_sample_rate_hz=float(analog.sample_rate)),
        scope=dict(service_pulses=len(rises), sampled_button_disagreements=0,
                   button_initial_high=bool(button.initial_state) ^ (sum(t < origin for t in edges) % 2 == 1),
                   button_edges_s=[t - origin for t in edges if origin <= t <= last],
                   action_edges_s=[t - origin for t in actions],
                   action_service_windows_s=[[float(rises[i])-origin, float(falls[i])-origin] for i in action_rows],
                   alignment=alignment,
                   pre_application_button_edges_s=[t-origin for t in edges if t < origin],
                   outside_application_action_edges_s=[float(t)-origin for t in gesture.transition_times if not origin <= t <= last],
                   service_gaps=[dict(after_seq=i-1, start_s=rises[i-1]-origin,
                                      end_s=rises[i]-origin, interval_us=(rises[i]-rises[i-1])*1e6)
                                 for i in range(1, len(rises)) if rises[i]-rises[i-1] > .0015],
                   invalid_adc_windows_s=[[rises[i]-origin, rises[j]-origin]
                       for i, j in capture_invalid_intervals(rows)],
                   analog=analog_evidence, pre_application_analog=pre_analog),
        native_scope_file_sha256=[hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((source/'scope').rglob('*')) if p.is_file()],
        limits='One fixture and bounded manual runs. Startup covers application sampling after peripheral initialization. No calibrated voltage, rail-rise/brownout, universal threshold, audio/IRQ-load or jack-detection claim. Native originals retained privately; published scope data are derived subsets.')
    if workload is not None:
        evidence['evidence'] = 'Measured stationary controls under declared audio-DMA and inbound USB load'
        evidence['load'] = dict(configuration=workload['configuration'], counters=workload['counters'],
                               host_writer=public_writer(metadata['writer']))
        for key, values in [('service_interval_us', np.diff(rises) * 1e6),
                            ('service_width_us', (np.asarray(falls) - np.asarray(rises)) * 1e6)]:
            evidence['scope'][key] = dict(min=float(np.min(values)), max=float(np.max(values)),
                                         median=float(np.median(values)), p99=float(np.percentile(values, 99)))
        evidence['limits'] = ('One fixture and bounded stationary run. Callback timing excludes SDK conversion and IRQ overhead; '
                              'padding is synthetic occupancy, not production DSP or audio-quality qualification. '
                              'Host USB pacing is best effort. No calibrated voltage, rail/brownout, jack-detection or universal timing claim. '
                              'Native originals retained privately; published scope data are derived subsets.')
    else:
        assert metadata['declared_fixture']['pot_ohms'] == 100000
        assert metadata['declared_fixture']['capacitor_nf'] == 0
    prefix.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(compressed)
    meta_path.write_text(json.dumps(evidence, indent=2) + '\n')
    assert gzip.decompress(raw_path.read_bytes()) == data
    print(prefix.name, len(rows), 'samples, public allowlist and paired coverage verified')

def capture_invalid_intervals(rows):
    intervals, start = [], None
    for i, row in enumerate(rows):
        if not row['adc_valid'] and start is None:
            start = i
        elif row['adc_valid'] and start is not None:
            intervals.append((start, i)); start = None
    assert start is None, 'Incomplete invalid interval'
    return intervals

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--out-prefix', type=Path, required=True)
    parser.add_argument('--startup-kind', choices=('reset', 'usb-power-cycle'))
    parser.add_argument('--load', action='store_true', help='Export a complete load-protocol trace, not a soak')
    parser.add_argument('--pot-ohms', type=int, help='Required explicit fixture declaration for load traces')
    parser.add_argument('--capacitor-nf', type=float, help='Required explicit fixture declaration for load traces')
    args = parser.parse_args()
    export(args.capture, args.out_prefix, args.startup_kind, args.load, args.pot_ohms, args.capacitor_nf)
