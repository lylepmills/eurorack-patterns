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
SCENARIOS = {'manual': 0, 'targets': 1, 'gap': 2, 'stall': 3, 'load': 4,
             'press-stall': 5, 'hold-stall': 6, 'release-stall': 7, 'press-adc-gap': 8,
             'pickup-gap-up': 9, 'pickup-gap-down': 10, 'moving-target': 11, 'startup': 12}
EVENT_SCENARIOS = range(5, 12)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def fnv(data, value=2166136261):
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value

def acquisition_capacity(info):
    """Accept the original and expanded buffers; reject unknown configurations."""
    capacity = info.get('max_records')
    require(info.get('period_us') == 1000 and capacity in (30000, 150000) and
            (info.get('protocol') == 2 or capacity == 30000) and
            info.get('sample_cycles_x2') == 1621 and info.get('oversampling') == 1,
            'unexpected acquisition configuration')
    return capacity

def parse(data, build_id=None):
    """Strict, complete protocol validation, independent of the control code."""
    require(data.endswith(b'\n'), 'truncated final line')
    lines = data.splitlines(keepends=True)
    require(len(lines) >= 5 and lines[0].startswith(b'INFO,'), 'missing identity')
    info = json.loads(lines[0][5:])
    require(info.get('protocol') in (1, 2) and info.get('board') == 'seed3' and
            info.get('ready') is True, 'unsupported protocol or board not ready')
    capacity = acquisition_capacity(info)
    if build_id: require(info.get('build_id') == build_id, 'firmware build identity mismatch')
    protocol = info['protocol']
    start = lines[1].decode('ascii').strip().split(',')
    require(len(start) == 6 and start[0] == 'START', 'missing START')
    token, scenario, duration, target, held = map(int, start[1:])
    require(0 <= token <= 0xffffffff and scenario in SCENARIOS.values() and
            1000 <= duration <= capacity and 0 <= target <= 1000 and held in (0, 1),
            'invalid run configuration')
    require(protocol == 2 or scenario <= 4, 'scenario requires protocol 2')
    require(scenario != 12 or (duration == 20000 and target == 250), 'invalid startup configuration')
    require(scenario not in (9, 10, 11) or target == 250, 'invalid movement scenario target')
    stimulus = [-1, -1, -1]
    fault_delay_us = 0
    column_index = 2
    if protocol == 2:
        fields = lines[2].decode('ascii').strip().split(',')
        require(len(fields) == 4 and fields[0] == 'STIMULUS', 'missing stimulus evidence')
        stimulus = list(map(int, fields[1:]))
        column_index = 3
        if lines[column_index].startswith(b'FAULTTIMING,'):
            timing = lines[column_index].decode('ascii').strip().split(',')
            require(len(timing) == 2 and info.get('fault_timing') == 1, 'invalid fault timing capability/record')
            fault_delay_us = int(timing[1])
            require(5 <= scenario <= 8 and 1 <= fault_delay_us <= 1000000, 'invalid fault delay')
            column_index += 1
    require(lines[column_index].decode('ascii').strip() == 'COLUMNS,' + ','.join(COLUMNS), 'column mismatch')
    end = lines[-1].decode('ascii').strip().split(',')
    require(len(end) == 9 and end[0] == 'END', 'missing END (capture incomplete)')
    end_token, count, missed, failures, rx_dropped, overflow, checksum, elapsed = map(int, end[1:])
    require(end_token == token and 0 < count <= capacity and len(lines) == count + column_index + 2,
            'run token or record count mismatch')
    require(min(missed, failures, rx_dropped, overflow) >= 0 and elapsed >= duration * 1000,
            'invalid completion counters')
    rows, digest, actions, adc_failures = [], 2166136261, 0, 0
    if protocol == 2: digest = fnv(b''.join(lines[2:column_index]), digest)
    previous_time = None
    target_epoch = 0
    for i, line in enumerate(lines[column_index + 1:-1]):
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
        if scenario in (8, 9, 10):
            expected_injection = stimulus[1] >= 0 and us >= stimulus[1] and (stimulus[2] < 0 or us < stimulus[2])
        require(bool(r['injected']) == expected_injection and not (r['injected'] and r['adc_valid']),
                'injection evidence mismatch')
        expected_external = -1
        if scenario == 1 and us // 5000000 != target_epoch:
            target_epoch = us // 5000000
            expected_external = 750 if target_epoch % 2 else 250
        if scenario == 11 and us == stimulus[0]: expected_external = 750
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
    stimulus_status = validate_stimulus(scenario, stimulus, rows, bool(held), elapsed, fault_delay_us)
    return info, dict(token=token, scenario=scenario, duration_ms=duration, target_milli=target,
                      startup_held=bool(held), elapsed_us=elapsed, missed=missed,
                      stimulus=dict(zip(('trigger_us', 'begin_us', 'end_us'), stimulus)),
                      **({'fault_delay_us': fault_delay_us} if fault_delay_us else {}),
                      stimulus_status=stimulus_status,
                      adc_failures=failures, rx_dropped=rx_dropped, buffer_overflow=overflow), rows

def validate_stimulus(scenario, stimulus, rows, held, elapsed, fault_delay_us=0):
    """Independent checks against recorded input edges and elapsed times."""
    if scenario not in EVENT_SCENARIOS:
        require(stimulus == [-1, -1, -1], 'unexpected event stimulus')
        return 'not_applicable'
    trigger, begin, end = stimulus
    previous_pressed, saw_press, previous_raw = held, False, None
    expected_trigger = -1
    for r in rows:
        press = r['pressed'] and not previous_pressed
        release = not r['pressed'] and previous_pressed and saw_press
        saw_press = saw_press or press
        previous_pressed = bool(r['pressed'])
        event = (scenario in (5, 6, 8) and press) or (scenario == 7 and release)
        if r['adc_valid'] and previous_raw is not None:
            if scenario == 9: event = previous_raw < 9831 <= r['raw']
            if scenario == 10: event = previous_raw > 22937 >= r['raw']
            if scenario == 11: event = previous_raw < 32768 <= r['raw']
        previous_raw = r['raw'] if r['adc_valid'] else None
        if event and expected_trigger < 0: expected_trigger = r['time_us']
    require(trigger == expected_trigger, 'stimulus trigger does not match observed input')
    if trigger < 0:
        require(begin == end == -1, 'untriggered stimulus executed')
        return 'not_triggered'
    delay = {5: 100000, 6: 605000, 8: 20000, 11: 0}.get(scenario, 1)
    due = trigger + (fault_delay_us or delay)
    require(begin == -1 or due <= begin <= elapsed, 'stimulus began before its deadline')
    if begin < 0:
        require(end == -1 and all(r['time_us'] < due for r in rows), 'due stimulus not executed')
        return 'incomplete'
    require(end == -1 or begin <= end <= elapsed, 'invalid stimulus completion')
    if scenario in (8, 9, 10):
        eligible = [r['time_us'] for r in rows if r['time_us'] >= due]
        require(eligible and begin == eligible[0], 'ADC gap did not begin at first eligible observation')
        recovery = [r['time_us'] for r in rows if r['time_us'] >= begin + (250000 if scenario == 8 else 1000000)]
        require(end == (recovery[0] if recovery else -1), 'ADC gap recovery time mismatch')
    elif scenario in (5, 6, 7):
        require(end >= begin + 25000, 'incomplete/short service stall')
        require(not any(begin <= r['time_us'] < end for r in rows), 'observations inside service stall')
    else:
        require(trigger == begin == end, 'moving edit timestamp mismatch')
    return 'completed' if end >= 0 and any(r['time_us'] >= end for r in rows) else 'incomplete'


def result_code(summary):
    if any(summary['run'][key] for key in ('adc_failures', 'rx_dropped', 'buffer_overflow')): return 2
    if summary['run']['stimulus_status'] in ('not_triggered', 'incomplete'): return 3
    return 0

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
    require(manifest.get('kind') == 'eurorack-patterns-daisy-bench' and manifest.get('protocol') in (1, 2),
            'wrong build manifest')
    binary = path.parent / 'patterns_daisy.bin'
    require(hashlib.sha256(binary.read_bytes()).hexdigest() ==
            manifest['artifacts_sha256']['patterns_daisy.bin'], 'firmware binary/manifest mismatch')
    return manifest

class LineReader:
    """Drain USB bursts in blocks, retaining surplus bytes for the next line."""
    def __init__(self, port, raw):
        self.port, self.raw = port, raw
        self.pending = bytearray()

    def read_line(self, deadline, poll=None):
        while True:
            newline = self.pending.find(b'\n')
            size = newline + 1 if newline >= 0 else len(self.pending)
            require(size < 4096, 'oversized protocol line')
            if newline >= 0:
                line = bytes(self.pending[:size])
                del self.pending[:size]
                return line
            if time.monotonic() >= deadline:
                raise TimeoutError('No complete response before timeout; raw data preserved')
            if poll is not None:
                poll()
            # pyserial.read_until performs a separate read for every byte.
            # Buffered draining avoids that overhead during multi-megabyte
            # downloads. A one-byte read waits when no bytes are ready.
            part = self.port.read(min(65536, max(1, self.port.in_waiting)))
            self.raw.write(part) # Preserve every received byte before validation.
            self.pending.extend(part)

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
                reader = LineReader(port, raw)
                port.write(b'?\n'); port.flush()
                line = reader.read_line(time.monotonic() + 8)
                require(line.startswith(b'INFO,'), 'unexpected device response; no run requested')
                identity = json.loads(line[5:])
                require(identity.get('protocol') == manifest['protocol'] and identity.get('ready') is True and
                        identity.get('build_id') == manifest['build_id'],
                        'device identity mismatch or initialization failure; no run requested')
                require(1 <= a.seconds * 1000 <= acquisition_capacity(identity),
                        'requested duration exceeds firmware capacity; no run requested')
                token = secrets.randbits(32)
                scenario = SCENARIOS[a.scenario]
                target = round(a.target * 1000)
                require(scenario <= 4 or identity['protocol'] == 2, 'scenario requires new firmware')
                require(scenario not in (9, 10, 11) or target == 250, 'movement-triggered scenarios require target 0.25')
                if scenario == 12:
                    require(a.seconds == 20 and target == 250, 'startup capture is fixed at 20 seconds and target 0.25')
                    require(identity.get('startup_available') is True, 'no unread startup capture; reset/power-cycle only when the scope is ready')
                    command = f'B,{token}\n'
                else:
                    require(not identity.get('startup_available'), 'download the startup capture first (--scenario startup)')
                    command = f'R,{token},{scenario},{a.seconds * 1000},{target}\n'
                port.write(command.encode('ascii')); port.flush()
                start = reader.read_line(time.monotonic() + 8)
                fields = start.decode('ascii').strip().split(',')
                require(len(fields) == 6 and fields[:5] ==
                        ['START', str(token), str(scenario), str(a.seconds * 1000), str(target)],
                        'run acknowledgement mismatch')
                if scenario == 12:
                    print('Downloading the retained post-initialization startup capture; no new acquisition requested.', flush=True)
                else:
                    print(f'Capturing {a.seconds} seconds ({a.scenario}); perform the planned gesture now.', flush=True)
                print('Then downloading buffered records. The Daisy D0 service marker is the timing reference.', flush=True)
                deadline = time.monotonic() + a.seconds + a.download_timeout
                while True:
                    line = reader.read_line(deadline)
                    require(not line.startswith(b'ERROR,'), line.decode('ascii').strip())
                    if line.startswith(b'END,'): break
        summary = save_analysis((a.out / 'raw.txt').read_bytes(), a.out, manifest['build_id'], a.replay)
        metadata['status'] = 'complete'
        metadata['raw_sha256'] = summary['raw_sha256']
        save_meta()
        print(json.dumps(summary, indent=2))
        return result_code(summary)
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
            require(1 <= a.seconds <= 150, 'seconds must be 1..150 (subject to firmware capacity)')
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
        return result_code(summary)
    except (ValueError, OSError, KeyError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
