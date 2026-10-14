#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Capture a Daisy bench window or analyze an existing raw capture. Never flash."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import statistics
import subprocess
import sys
import time

COLUMNS = ('seq,time_us,adc_us,work_us,raw,adc_valid,injected,pressed,external_milli,'
           'cadence_valid,accepted_ppm,value_ppm,target_ppm,state,debounced,gesture,'
           'changed,actions,missed').split(',')
SCENARIOS = {'manual': 0, 'targets': 1, 'gap': 2, 'stall': 3, 'load': 4}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def fnv(data, value=2166136261):
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value

def parse(data, build_id=None):
    """Strict, complete protocol validation, independent of the control code."""
    require(data.endswith(b'\n'), 'truncated final line')
    lines = data.splitlines(keepends=True)
    require(len(lines) >= 5 and lines[0].startswith(b'INFO,'), 'missing identity')
    info = json.loads(lines[0][5:])
    require(info.get('protocol') == 1 and info.get('board') == 'seed3' and
            info.get('ready') is True, 'unsupported protocol or board not ready')
    require(info.get('period_us') == 1000 and info.get('max_records') == 30000 and
            info.get('sample_cycles_x2') == 1621 and info.get('oversampling') == 1,
            'unexpected acquisition configuration')
    if build_id: require(info.get('build_id') == build_id, 'firmware build identity mismatch')
    start = lines[1].decode('ascii').strip().split(',')
    require(len(start) == 6 and start[0] == 'START', 'missing START')
    token, scenario, duration, target, held = map(int, start[1:])
    require(0 <= token <= 0xffffffff and scenario in SCENARIOS.values() and
            1000 <= duration <= 30000 and 0 <= target <= 1000 and held in (0, 1),
            'invalid run configuration')
    require(lines[2].decode('ascii').strip() == 'COLUMNS,' + ','.join(COLUMNS), 'column mismatch')
    end = lines[-1].decode('ascii').strip().split(',')
    require(len(end) == 9 and end[0] == 'END', 'missing END (capture incomplete)')
    end_token, count, missed, failures, rx_dropped, overflow, checksum, elapsed = map(int, end[1:])
    require(end_token == token and 0 < count <= 30000 and len(lines) == count + 4,
            'run token or record count mismatch')
    require(min(missed, failures, rx_dropped, overflow) >= 0 and elapsed >= duration * 1000,
            'invalid completion counters')
    rows, digest, actions, adc_failures = [], 2166136261, 0, 0
    previous_time = None
    target_epoch = 0
    for i, line in enumerate(lines[3:-1]):
        require(line.startswith(b'D,') and line.endswith(b'\n'), 'malformed data record')
        digest = fnv(line, digest)
        fields = line[2:].decode('ascii').strip().split(',')
        require(len(fields) == len(COLUMNS), 'record width mismatch')
        r = dict(zip(COLUMNS, map(int, fields)))
        require(r['seq'] == i, 'duplicate, dropped or reordered record')
        us = r['time_us']
        require(0 <= us < duration * 1000 and (previous_time is None or us > previous_time),
                'nonmonotonic or out-of-window time')
        require(0 <= r['adc_us'] <= r['work_us'] and us + r['work_us'] <= elapsed,
                'invalid work/acquisition duration')
        require(0 <= r['raw'] <= 65535, 'ADC code out of range')
        for name in ['adc_valid', 'injected', 'pressed', 'cadence_valid', 'debounced', 'changed']:
            require(r[name] in (0, 1), 'non-boolean ' + name)
        require(r['state'] in range(4) and r['gesture'] in range(3), 'unknown state/event')
        require(r['accepted_ppm'] == -1 or 0 <= r['accepted_ppm'] <= 1000000, 'invalid accepted value')
        require(0 <= r['value_ppm'] <= 1000000 and 0 <= r['target_ppm'] <= 1000000, 'invalid value')
        expected_injection = scenario == 2 and 5000000 <= us < 5250000
        require(bool(r['injected']) == expected_injection and not (r['injected'] and r['adc_valid']),
                'injection evidence mismatch')
        expected_external = -1
        if scenario == 1 and us // 5000000 != target_epoch:
            target_epoch = us // 5000000
            expected_external = 750 if target_epoch % 2 else 250
        require(r['external_milli'] == expected_external, 'target schedule mismatch')
        cadence = previous_time is None or us - previous_time <= 10000
        require(bool(r['cadence_valid']) == cadence, 'cadence flag mismatch')
        require(r['missed'] == us // 1000 - i, 'missed-deadline accounting mismatch')
        require(not r['changed'] or (r['adc_valid'] and r['state'] == 2), 'invalid/unowned sample applied')
        require(r['adc_valid'] or r['accepted_ppm'] == -1, 'invalid sample retained as accepted')
        actions += bool(r['gesture'])
        require(r['actions'] == actions, 'action-count mismatch')
        adc_failures += not r['adc_valid'] and not r['injected']
        previous_time = us
        rows.append(r)
    require(digest == checksum, 'record checksum mismatch')
    require(rows[-1]['missed'] == missed and adc_failures == failures, 'completion count mismatch')
    return info, dict(token=token, scenario=scenario, duration_ms=duration, target_milli=target,
                      startup_held=bool(held), elapsed_us=elapsed, missed=missed,
                      adc_failures=failures, rx_dropped=rx_dropped, buffer_overflow=overflow), rows

def percentile(values, percent):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * percent / 100) - 1)] if values else None

def summarize(info, run, rows):
    intervals = [b['time_us'] - a['time_us'] for a, b in zip(rows, rows[1:])]
    valid_raw = [r['raw'] for r in rows if r['adc_valid']]
    def stats(values):
        return dict(min=min(values), p50=percentile(values, 50), p99=percentile(values, 99),
                    max=max(values)) if values else None
    return dict(protocol_integrity='verified', hardware_validation='pending independent scope/behavior review',
                build_id=info['build_id'], run=run, samples=len(rows),
                interval_us=stats(intervals), adc_us=stats([r['adc_us'] for r in rows]),
                work_us=stats([r['work_us'] for r in rows]),
                invalid_samples=sum(not r['adc_valid'] for r in rows),
                cadence_breaks=sum(not r['cadence_valid'] for r in rows),
                taps=sum(r['gesture'] == 1 for r in rows), holds=sum(r['gesture'] == 2 for r in rows),
                raw_span=dict(min=min(valid_raw), max=max(valid_raw),
                              stddev=statistics.pstdev(valid_raw)) if valid_raw else None,
                raw_span_note='Spread across the entire window, not a noise estimate when the knob moves.')

def save_analysis(data, out, build_id=None, replay=None):
    info, run, rows = parse(data, build_id)
    summary = summarize(info, run, rows)
    summary['raw_sha256'] = hashlib.sha256(data).hexdigest()
    summary['replay'] = 'not run'
    if replay:
        checked = subprocess.run([str(replay.resolve()), str((out / 'raw.txt').resolve())],
                                 text=True, capture_output=True)
        require(checked.returncode == 0, 'C++ replay failed: ' + checked.stdout + checked.stderr)
        summary['replay'] = checked.stdout.strip()
    with (out / 'samples.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary

def load_manifest(path):
    manifest = json.loads(path.read_text())
    require(manifest.get('kind') == 'eurorack-patterns-daisy-bench' and manifest.get('protocol') == 1,
            'wrong build manifest')
    binary = path.parent / 'patterns_daisy.bin'
    require(hashlib.sha256(binary.read_bytes()).hexdigest() ==
            manifest['artifacts_sha256']['patterns_daisy.bin'], 'firmware binary/manifest mismatch')
    return manifest

def read_line(port, raw, deadline):
    data = bytearray()
    while time.monotonic() < deadline:
        part = port.read_until(b'\n', 4096 - len(data))
        raw.write(part) # Preserve partial reads, malformed data and failures too.
        data.extend(part)
        require(len(data) < 4096, 'oversized protocol line')
        if data.endswith(b'\n'): return bytes(data)
    raise TimeoutError('No complete response before timeout; raw data preserved')

def capture(a):
    manifest = load_manifest(a.manifest)
    try:
        import serial
    except ImportError as exc:
        raise ValueError('Install pyserial: python3 -m pip install pyserial==3.5') from exc
    require(a.out is not None and not a.out.exists(), 'output directory must be new')
    a.out.mkdir(parents=True)
    metadata = dict(schema=1, acquired_utc=datetime.now(timezone.utc).isoformat(),
                    evidence='hardware capture with any generated faults explicitly flagged',
                    status='incomplete', scenario=a.scenario, duration_s=a.seconds,
                    declared_fixture=dict(pot_ohms=a.pot_ohms, capacitor_nf=a.capacitor_nf,
                                          probe=a.probe, notes=a.notes),
                    build=manifest)
    # Do not persist port names/device serials, home paths or full command lines.
    meta_path = a.out / 'metadata.json'
    def save_meta(): meta_path.write_text(json.dumps(metadata, indent=2) + '\n')
    save_meta()
    try:
        port = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=2)
        port.dtr = False; port.rts = False
        if sys.platform != 'win32': port.exclusive = True
        port.port = a.port
        with port:
            with (a.out / 'raw.txt').open('wb') as raw:
                port.write(b'?\n'); port.flush()
                line = read_line(port, raw, time.monotonic() + 8)
                require(line.startswith(b'INFO,'), 'unexpected device response; no run requested')
                identity = json.loads(line[5:])
                require(identity.get('protocol') == 1 and identity.get('ready') is True and
                        identity.get('build_id') == manifest['build_id'],
                        'device identity mismatch or initialization failure; no run requested')
                token = secrets.randbits(32)
                scenario = SCENARIOS[a.scenario]
                target = round(a.target * 1000)
                command = f'R,{token},{scenario},{a.seconds * 1000},{target}\n'
                port.write(command.encode('ascii')); port.flush()
                start = read_line(port, raw, time.monotonic() + 8)
                fields = start.decode('ascii').strip().split(',')
                require(len(fields) == 6 and fields[:5] ==
                        ['START', str(token), str(scenario), str(a.seconds * 1000), str(target)],
                        'run acknowledgement mismatch')
                print(f'Capturing {a.seconds} seconds ({a.scenario}); perform the planned gesture now.', flush=True)
                print('Then downloading buffered records. Scope D0 is the timing reference.', flush=True)
                deadline = time.monotonic() + a.seconds + a.download_timeout
                while True:
                    line = read_line(port, raw, deadline)
                    require(not line.startswith(b'ERROR,'), line.decode('ascii').strip())
                    if line.startswith(b'END,'): break
        summary = save_analysis((a.out / 'raw.txt').read_bytes(), a.out, manifest['build_id'], a.replay)
        metadata['status'] = 'complete'
        metadata['raw_sha256'] = summary['raw_sha256']
        save_meta()
        print(json.dumps(summary, indent=2))
        return 2 if any(summary['run'][key] for key in ['adc_failures', 'rx_dropped', 'buffer_overflow']) else 0
    except BaseException:
        # Keep status incomplete on interruption, parsing failure or disconnect.
        save_meta()
        raise

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--port', required=True, help='Explicit serial port; no auto-discovery')
    c.add_argument('--manifest', type=Path, required=True)
    c.add_argument('--out', type=Path, required=True)
    c.add_argument('--scenario', choices=SCENARIOS, default='manual')
    c.add_argument('--seconds', type=int, default=20)
    c.add_argument('--target', type=float, default=0.25)
    c.add_argument('--pot-ohms', type=int, default=100000)
    c.add_argument('--capacitor-nf', type=float, default=0)
    c.add_argument('--probe', default='10x scope probe on wiper; common ground')
    c.add_argument('--notes', default='')
    c.add_argument('--download-timeout', type=float, default=120)
    c.add_argument('--replay', type=Path)
    v = sub.add_parser('analyze')
    v.add_argument('raw', type=Path)
    v.add_argument('--out', type=Path, required=True)
    v.add_argument('--replay', type=Path)
    v.add_argument('--build-id')
    a = p.parse_args()
    try:
        if a.mode == 'capture':
            require(1 <= a.seconds <= 30, 'seconds must be 1..30')
            require(math.isfinite(a.target) and 0 <= a.target <= 1, 'target must be 0..1')
            require(a.pot_ohms > 0 and math.isfinite(a.capacitor_nf) and a.capacitor_nf >= 0,
                    'invalid fixture values')
            require(math.isfinite(a.download_timeout) and a.download_timeout > 0, 'invalid timeout')
            require(a.scenario not in ('gap', 'stall', 'targets') or a.seconds >= 6,
                    'this scenario needs at least 6 seconds')
            return capture(a)
        require(not a.out.exists(), 'analysis output directory must be new')
        data = a.raw.read_bytes()
        a.out.mkdir(parents=True)
        (a.out / 'raw.txt').write_bytes(data)
        summary = save_analysis(data, a.out, a.build_id, a.replay)
        print(json.dumps(summary, indent=2))
        return 2 if any(summary['run'][key] for key in ['adc_failures', 'rx_dropped', 'buffer_overflow']) else 0
    except (ValueError, OSError, KeyError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
