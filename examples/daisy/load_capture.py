#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Record/analyze audio-DMA + USB load experiments. Never flash or discover ports."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import sys
import threading
import time

import capture
import diagnostics
from capture import require

CONFIG = 'token,mode,duration_ms,target_milli,audio_permille,block_size,usb_hz,startup_held'.split(',')
STATS = ('samples,missed,adc_failures,buffer_overflow,rx_dropped,elapsed_us,'
         'callbacks,max_callback_ticks,max_callback_interval_ticks,callback_over_budget,'
         'late_callback_intervals,bad_callback_size,usb_packets,usb_bytes,usb_malformed,'
         'usb_sequence_errors,callback_period_ticks,timer_hz').split(',')
BUCKETS = ('second,samples,first_us,last_us,missed,adc_failures,cadence_breaks,actions,'
           'max_work_us,max_interval_us,raw_min,raw_max').split(',')


def fields(line, prefix, names):
    words = line.decode('ascii').rstrip('\n').split(',')
    require(words[0] == prefix and len(words) == len(names)+1, 'invalid ' + prefix)
    values = list(map(int, words[1:]))
    require(all(0 <= v <= 0xffffffff for n, v in zip(names, values) if n != 'audio_permille'),
            'out-of-range ' + prefix)
    return dict(zip(names, values))


def validate_config(c):
    require(c['mode'] in (0, 1, 2) and 1000 <= c['duration_ms'] <= (150000 if c['mode'] == 0 else 3600000)
            and c['duration_ms'] % 1000 == 0 and 0 <= c['target_milli'] <= 1000
            and -1 <= c['audio_permille'] <= 700 and c['block_size'] in (16, 48, 96)
            and c['usb_hz'] in (0, 100, 500) and c['startup_held'] in (0, 1), 'invalid workload configuration')


def parse(data, build_id=None):
    require(data.endswith(b'\n'), 'truncated load capture')
    lines = data.splitlines(keepends=True)
    require(len(lines) >= 5 and lines[0].startswith(b'INFO,'), 'missing load identity')
    info = json.loads(lines[0][5:])
    require(info.get('protocol') == 2 and info.get('load_protocol') == 1
            and info.get('board') == 'seed3' and info.get('ready') is True,
            'unsupported load firmware')
    capture.acquisition_capacity(info)
    if build_id: require(info.get('build_id') == build_id, 'firmware build identity mismatch')
    c = fields(lines[1], 'LOADSTART', CONFIG); validate_config(c)
    if c['mode'] == 2:
        require(info.get('timing_diagnostics') == 1, 'firmware lacks timing diagnostics')
    s = fields(lines[-2], 'LOADSTATS', STATS)
    end = fields(lines[-1], 'LOADEND', ['token', 'checksum'])
    require(end['token'] == c['token'] and end['checksum'] == capture.fnv(b''.join(lines[1:-1])),
            'load token/checksum mismatch')
    require(s['samples'] > 0 and s['elapsed_us'] >= c['duration_ms']*1000, 'incomplete load interval')
    require(s['timer_hz'] == info.get('timer_hz') and s['timer_hz'] > 0, 'timer identity mismatch')
    require(s['usb_bytes'] == 64*(s['usb_packets']+s['usb_malformed']), 'USB accounting mismatch')
    control_data, buckets = None, []
    if c['mode'] == 0:
        control_data = lines[0] + b''.join(lines[2:-2])
        _, run, rows = capture.parse(control_data, build_id)
        require(run['scenario'] == 0 and run['duration_ms'] == c['duration_ms']
                and run['token'] == c['token'] and run['target_milli'] == c['target_milli']
                and run['startup_held'] == bool(c['startup_held']), 'control/load configuration mismatch')
        require(s['samples'] == len(rows) and all(run[k] == s[k] for k in
                ('missed', 'adc_failures', 'buffer_overflow', 'rx_dropped', 'elapsed_us')),
                'control/load counters mismatch')
        actions = sum(r['gesture'] != 0 for r in rows)
        cadence = sum(not r['cadence_valid'] for r in rows)
        work = max(r['work_us'] for r in rows)
        interval = max((b['time_us']-a['time_us'] for a, b in zip(rows, rows[1:])), default=0)
    else:
        if c['mode'] == 1:
            require(len(lines[2:-2]) == c['duration_ms']//1000, 'missing soak buckets')
        body = iter(lines[2:-2])
        def take():
            line = next(body, None)
            require(line is not None, 'missing soak buckets/diagnostics')
            return line
        accounted = base_seq = 0
        origin = None
        for i in range(c['duration_ms']//1000):
            b = fields(take(), 'S', BUCKETS)
            require(b['second'] == i, 'reordered soak bucket')
            require(b['samples'] <= 1000 and b['adc_failures'] <= b['samples']
                    and b['cadence_breaks'] <= b['samples'] and b['actions'] <= b['samples'],
                    'invalid bucket counters')
            if b['samples']:
                require(i*1000000 <= b['first_us'] <= b['last_us'] < (i+1)*1000000
                        and b['samples'] <= (b['last_us']//1000 - b['first_us']//1000 + 1)
                        and b['first_us']//1000 >= accounted, 'invalid bucket timeline')
                accounted += b['samples'] + b['missed']
                require(accounted == b['last_us']//1000+1, 'bucket skipped-slot mismatch')
                if b['adc_failures'] < b['samples']:
                    require(0 <= b['raw_min'] <= b['raw_max'] <= 65535, 'invalid bucket ADC range')
            else:
                require(all(b[k] == 0 for k in BUCKETS[1:-2]) and b['raw_min'] == 65535
                        and b['raw_max'] == 0, 'invalid empty bucket')
            if c['mode'] == 2:
                b['timing'], origin = diagnostics.parse_bucket(take, b, base_seq, s['timer_hz'],
                                                               c['duration_ms']*1000, origin)
            base_seq += b['samples']
            buckets.append(b)
        require(next(body, None) is None, 'extra soak buckets/diagnostics')
        for key in ('samples', 'missed', 'adc_failures'):
            require(sum(b[key] for b in buckets) == s[key], 'bucket total mismatch: ' + key)
        actions = sum(b['actions'] for b in buckets)
        cadence = sum(b['cadence_breaks'] for b in buckets)
        work = max(b['max_work_us'] for b in buckets)
        interval = max(b['max_interval_us'] for b in buckets)
    if c['audio_permille'] < 0:
        require(all(s[k] == 0 for k in STATS[6:12]) and s['callback_period_ticks'] == 0,
                'audio activity in disabled run')
    else:
        require(s['callback_period_ticks'] == s['timer_hz']*c['block_size']//48000,
                'audio period configuration mismatch')
    summary = dict(protocol_integrity='verified', hardware_validation='pending independent scope/behavior review',
                   build_id=info['build_id'], configuration=c, counters=s, actions=actions,
                   cadence_breaks=cadence, max_control_work_us=work, max_control_interval_us=interval,
                   raw_sha256=hashlib.sha256(data).hexdigest(),
                   representation='complete control trace' if not c['mode'] else 'continuous per-second aggregates; no per-sample replay',
                   callback_timing_note='Application callback body only; excludes SDK conversion and DMA IRQ overhead. Late interval means >1.5 nominal periods, not a codec underrun detector.')
    if c['mode'] == 2:
        summary['timing_diagnostics'] = dict(version=1, buckets=len(buckets),
            retained_witnesses=sum(len(b['timing']['witnesses']) for b in buckets),
            max_bookkeeping_ticks=max(b['timing']['max_bookkeeping_ticks'] for b in buckets),
            note='Selected samples and predecessors, not a complete per-sample trace; CPU GPIO brackets need physical review.')
    return summary, control_data, buckets


def assess(summary, stationary=False, writer=None):
    c, s = summary['configuration'], summary['counters']
    failures = []
    for key in ('missed', 'adc_failures', 'buffer_overflow', 'rx_dropped', 'callback_over_budget',
                'late_callback_intervals', 'bad_callback_size', 'usb_malformed', 'usb_sequence_errors'):
        if s[key]: failures.append(key)
    if s['samples'] + s['missed'] != c['duration_ms']: failures.append('incomplete service-slot coverage')
    if summary['cadence_breaks']: failures.append('control cadence breaks')
    if stationary and summary['actions']: failures.append('unexpected button action in stationary run')
    if c['audio_permille'] >= 0:
        expected = c['duration_ms']*48/c['block_size']
        # Two clocks need not be exactly commensurate. Report the observed rate;
        # this broad bound catches absent/stalled/wrong-rate callbacks.
        if abs(s['callbacks']-expected) > max(3, expected*.005): failures.append('callback coverage/rate')
        if s['max_callback_ticks'] < s['callback_period_ticks']*c['audio_permille']//1000:
            failures.append('requested callback padding not observed')
        if s['max_callback_ticks'] >= s['callback_period_ticks']: failures.append('callback body exceeds period')
    if c['usb_hz']:
        minimum = int(max(0, c['duration_ms']/1000-.7)*c['usb_hz']*.8)
        if s['usb_packets'] < minimum: failures.append('USB stimulus coverage')
    elif s['usb_packets']: failures.append('unexpected USB stimulus')
    if writer is not None:
        if writer['error']: failures.append('host USB writer error')
        if s['usb_packets'] != writer['packets']: failures.append('host/device USB packet mismatch')
        # Host scheduling is best effort, not a real-time clock. Keep every
        # skipped slot visible; fail materially sparse/broken stimulus.
        if writer['skipped_slots'] > writer['packets']/4:
            failures.append('host USB stimulus scheduling gaps')
        if writer.get('max_lateness_s', 0) > .05:
            failures.append('host USB stimulus pause exceeds 50 ms')
    summary['checks'] = dict(status='pass' if not failures else 'fail', failures=failures,
                             stationary=stationary, independent_hardware_review=False)
    return not failures


def save_analysis(data, out, build_id=None, replay=None, stationary=False, writer=None):
    summary, controls, buckets = parse(data, build_id)
    if controls is not None:
        folder = out/'controls'; folder.mkdir()
        (folder/'raw.txt').write_bytes(controls)
        result = capture.save_analysis(controls, folder, build_id, replay)
        summary['replay'] = result['replay']
    else:
        summary['replay'] = 'not applicable: aggregates do not retain individual samples'
        with (out/'buckets.csv').open('w', newline='') as f:
            csv_writer = csv.DictWriter(f, fieldnames=BUCKETS, extrasaction='ignore')
            csv_writer.writeheader(); csv_writer.writerows(buckets)
        if summary['configuration']['mode'] == 2:
            (out/'timing.json').write_text(json.dumps([b['timing'] for b in buckets], indent=2)+'\n')
    assess(summary, stationary, writer)
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def packet(seq):
    return b'\xa5' + seq.to_bytes(4, 'little') + bytes((seq+i) & 255 for i in range(5, 63)) + b'\x5a'


class TrafficWriter(threading.Thread):
    def __init__(self, port, hz, seconds):
        super().__init__(daemon=True)
        self.port, self.hz = port, hz
        self.start_at = time.monotonic()+.15
        self.end_at = self.start_at+seconds-.65
        self.stop_event = threading.Event()
        self.result = dict(packets=0, skipped_slots=0, max_lateness_s=0.0, error=None)

    def run(self):
        if not self.hz: return
        due = self.start_at
        try:
            while not self.stop_event.wait(max(0, due-time.monotonic())):
                now = time.monotonic()
                if now >= self.end_at: break
                late = max(0, now-due)
                skipped = int(late*self.hz)
                self.result['skipped_slots'] += skipped
                self.result['max_lateness_s'] = max(self.result['max_lateness_s'], late)
                due += (skipped+1)/self.hz
                require(self.port.write(packet(self.result['packets'])) == 64, 'partial USB traffic write')
                self.result['packets'] += 1
        except Exception as exc:
            self.result['error'] = type(exc).__name__ + ': ' + str(exc)

    def finish(self):
        self.stop_event.set(); self.join(timeout=3)
        require(not self.is_alive(), 'USB writer did not terminate')


def record(a):
    manifest = capture.load_manifest(a.manifest)
    require(manifest.get('load_protocol') == 1, 'manifest has no load firmware')
    require(a.replay is not None and a.replay.is_file(), 'build the C++ replay executable before capture')
    requested = dict(mode={'trace': 0, 'soak': 1, 'diagnostic': 2}[a.mode], duration_ms=a.seconds*1000,
                     target_milli=round(a.target*1000), audio_permille=a.audio_permille,
                     block_size=a.block_size, usb_hz=a.usb_hz, startup_held=0)
    validate_config(requested)
    if requested['mode'] == 2:
        require(manifest.get('timing_diagnostics') == 1, 'manifest lacks timing diagnostics')
    require(a.out is not None and not a.out.exists(), 'output directory must be new')
    import serial
    a.out.mkdir(parents=True)
    meta = dict(schema=1, status='incomplete', acquired_utc=datetime.now(timezone.utc).isoformat(),
                build=manifest, requested=requested, stationary=a.stationary)
    (a.out/'metadata.json').write_text(json.dumps(meta, indent=2)+'\n')
    writer = None
    try:
        port = serial.Serial(port=None, baudrate=115200, timeout=.2, write_timeout=2)
        port.dtr = False; port.rts = False
        if sys.platform != 'win32': port.exclusive = True
        port.port = a.port
        with port:
            try:
                with (a.out/'raw.txt').open('wb') as raw:
                    reader = capture.LineReader(port, raw)
                    port.write(b'?\n'); port.flush()
                    line = reader.read_line(time.monotonic()+8)
                    require(line.startswith(b'INFO,'), 'missing identity; no run requested')
                    info = json.loads(line[5:])
                    require(info.get('load_protocol') == 1 and info.get('protocol') == 2
                            and info.get('ready') is True and info.get('board') == 'seed3'
                            and info.get('build_id') == manifest['build_id'], 'firmware mismatch; no run requested')
                    if requested['mode'] == 2:
                        require(info.get('timing_diagnostics') == 1, 'device lacks timing diagnostics')
                    require(not info.get('startup_available'), 'download retained startup capture first')
                    capacity = capture.acquisition_capacity(info)
                    require(requested['mode'] or requested['duration_ms'] <= capacity,
                            'trace exceeds advertised capacity; no run requested')
                    token = secrets.randbits(32)
                    command = f"L,{token},{requested['mode']},{requested['duration_ms']},{requested['target_milli']},{a.audio_permille},{a.block_size},{a.usb_hz}\n"
                    port.write(command.encode()); port.flush()
                    ack = fields(reader.read_line(time.monotonic()+8), 'LOADSTART', CONFIG)
                    require(ack['token'] == token and all(ack[k] == v for k, v in requested.items() if k != 'startup_held'),
                            'workload acknowledgement mismatch')
                    writer = TrafficWriter(port, a.usb_hz, a.seconds); writer.start()
                    print(f"Recording {a.seconds}s {a.mode}; audio padding {a.audio_permille}/1000, block {a.block_size}, USB {a.usb_hz} packets/s.", flush=True)
                    deadline = time.monotonic()+a.seconds+a.download_timeout
                    while True:
                        line = reader.read_line(deadline)
                        require(not line.startswith(b'ERROR,'), 'device rejected load run')
                        if line.startswith(b'LOADEND,'): break
            finally:
                if writer: writer.finish()
        meta['writer'] = writer.result
        summary = save_analysis((a.out/'raw.txt').read_bytes(), a.out, manifest['build_id'], a.replay,
                                a.stationary, writer.result)
        meta['status'] = 'complete'; meta['raw_sha256'] = summary['raw_sha256']
        print(json.dumps(summary, indent=2), flush=True)
        return 0 if summary['checks']['status'] == 'pass' else 2
    finally:
        if writer: meta['writer'] = writer.result
        (a.out/'metadata.json').write_text(json.dumps(meta, indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--port', required=True)
    c.add_argument('--manifest', type=Path, required=True)
    c.add_argument('--out', type=Path, required=True)
    c.add_argument('--mode', choices=['trace', 'soak', 'diagnostic'], default='trace')
    c.add_argument('--seconds', type=int, default=30)
    c.add_argument('--target', type=float, default=.25)
    c.add_argument('--audio-permille', type=int, default=0, help='-1 disables audio; 0 runs DMA; 1..700 pads the callback body')
    c.add_argument('--block-size', type=int, choices=[16, 48, 96], default=16)
    c.add_argument('--usb-hz', type=int, choices=[0, 100, 500], default=0)
    c.add_argument('--download-timeout', type=float, default=180)
    c.add_argument('--stationary', action='store_true', help='Require no button actions')
    c.add_argument('--replay', type=Path, required=True)
    v = sub.add_parser('analyze')
    v.add_argument('raw', type=Path)
    v.add_argument('--out', type=Path, required=True)
    v.add_argument('--replay', type=Path, required=True)
    v.add_argument('--stationary', action='store_true')
    a = p.parse_args()
    try:
        if a.command == 'capture':
            require(math.isfinite(a.target) and 0 <= a.target <= 1, 'target must be 0..1')
            require(math.isfinite(a.download_timeout) and a.download_timeout > 0, 'invalid timeout')
            return record(a)
        require(not a.out.exists(), 'analysis directory must be new')
        data = a.raw.read_bytes(); a.out.mkdir(parents=True)
        (a.out/'raw.txt').write_bytes(data)
        summary = save_analysis(data, a.out, replay=a.replay, stationary=a.stationary)
        print(json.dumps(summary, indent=2))
        return 0 if summary['checks']['status'] == 'pass' else 2
    except (ValueError, OSError, KeyError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr); return 1


if __name__ == '__main__':
    sys.exit(main())
