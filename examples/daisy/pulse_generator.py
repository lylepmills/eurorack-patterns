#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Drive an explicitly identified second Daisy; never discover ports or flash.

Serial timing records are apparatus diagnostics. Use inspect_physical with
Saleae edges before accepting the stimulus as physical evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import sys
import time

from capture import LineReader, require


def validate_times(times):
    require(isinstance(times, list) and 2 <= len(times) <= 64 and len(times) % 2 == 0,
            'require 1–32 complete press/release pairs')
    require(all(type(t) is int and 100000 <= t <= 30000000 for t in times)
            and all(b-a >= 100 for a, b in zip(times, times[1:])), 'invalid edge timetable')


def load_manifest(path):
    m = json.loads(path.read_text())
    require(m.get('kind') == 'eurorack-patterns-daisy-pulse-generator'
            and m.get('protocol') == 1 and m.get('board') == 'seed3', 'wrong generator manifest')
    binary = path.parent/'patterns_pulse_generator.bin'
    require(hashlib.sha256(binary.read_bytes()).hexdigest() ==
            m['artifacts_sha256']['patterns_pulse_generator.bin'], 'generator image hash mismatch')
    return m


def fields(line, prefix, count):
    words = line.decode('ascii').rstrip('\n').split(',')
    require(words[0] == prefix and len(words) == count+1
            and all(w.isascii() and w.isdigit() for w in words[1:]), 'invalid '+prefix)
    values = list(map(int, words[1:]))
    require(all(v <= 0xffffffff for v in values), 'out-of-range '+prefix)
    return values


def identity(line, build_id):
    require(line.startswith(b'GENINFO,'), 'unexpected device; no pulse requested')
    info = json.loads(line[8:])
    require(info.get('kind') == 'daisy-pulse-generator' and info.get('protocol') == 1
            and info.get('board') == 'seed3' and info.get('build_id') == build_id
            and info.get('released') is True and info.get('armed') is False
            and info.get('max_edges') == 64 and info.get('max_us') == 30000000
            and info.get('max_late_us') == 25 and 0 < info.get('timer_hz', 0) <= 0xffffffff,
            'generator identity/state mismatch; no pulse requested')
    return info


def parse(raw, build_id, times):
    validate_times(times)
    require(raw.endswith(b'\n'), 'truncated generator capture')
    lines = raw.splitlines(keepends=True)
    require(len(lines) == len(times)+4, 'incomplete generator record')
    info = identity(lines[0], build_id)
    token, count, last = fields(lines[1], 'GENARMED', 3)
    require((count, last) == (len(times), times[-1]), 'arm acknowledgement mismatch')
    require(fields(lines[2], 'GENSTART', 2) == [token, count], 'start acknowledgement mismatch')
    edges = []
    for i, line in enumerate(lines[3:-1]):
        seq, due, before, after, pressed = fields(line, 'GENEDGE', 5)
        require(seq == i and due == times[i] and pressed == (i % 2 == 0)
                and due <= before <= after <= due+25, 'generator edge/deadline mismatch')
        edges.append(dict(seq=seq, due_us=due, before_us=before, after_us=after, pressed=pressed))
    end_token, actual, status, end_us = fields(lines[-1], 'GENEND', 4)
    require([end_token, actual, status] == [token, count, 0], 'generator aborted or incomplete')
    require(edges[-1]['after_us'] <= end_us <= edges[-1]['after_us']+1000, 'invalid run end')
    return dict(schema=1, status='software timing passed; physical verification pending',
        info=info, token=token, edges=edges, end_us=end_us,
        max_lateness_us=max(e['after_us']-e['due_us'] for e in edges),
        raw_sha256=hashlib.sha256(raw).hexdigest())


def inspect_physical(report, initial_high, transitions):
    """Whole-record matching: no trimming extras or fitting separate short windows.

    Relative clock fit (<=1000 ppm) allows different oscillator frequencies.
    Five-us residual/interval gates retain jitter; none of these clocks is
    asserted to be an absolute calibrated time reference.
    """
    edges = list(transitions)
    require(initial_high and len(edges) == len(report['edges']) and len(edges) >= 4
            and all(math.isfinite(t) for t in edges)
            and all(a < b for a, b in zip(edges, edges[1:])), 'incomplete physical pulse sequence')
    x = [(r['before_us']+r['after_us'])/2 for r in report['edges']]
    y = [(t-edges[0])*1e6 for t in edges]
    mx, my = sum(x)/len(x), sum(y)/len(y)
    slope = sum((a-mx)*(b-my) for a, b in zip(x, y)) / sum((a-mx)**2 for a in x)
    intercept = my-slope*mx
    residual = max(abs(b-(slope*a+intercept)) for a, b in zip(x, y))
    interval = max(abs((y[i]-y[i-1])-slope*(x[i]-x[i-1])) for i in range(1, len(x)))
    failures = []
    if abs(slope-1) > .001: failures.append('clock_scale')
    if residual > 5: failures.append('global_fit')
    if interval > 5: failures.append('interval')
    return dict(status='fail' if failures else 'pass', failures=failures, edges=len(edges),
        scale=slope, max_residual_us=residual, max_interval_error_us=interval,
        physical_press_us=[(b-a)*1e6 for a, b in zip(edges[::2], edges[1::2])],
        limitation='Stimulus-only check; does not qualify DUT behavior or service phase coverage.')


class Generator:
    """Caller owns the exclusive port and capture reservation, including aborts."""
    def __init__(self, port, raw, manifest):
        self.port, self.reader, self.manifest = port, LineReader(port, raw), manifest
        self.started = False
        self.identified = False

    def exchange(self, command, timeout=5):
        self.port.write(command); self.port.flush()
        return self.reader.read_line(time.monotonic()+timeout)

    def prepare(self, times, token=None):
        validate_times(times)
        self.times = times[:]
        self.token = secrets.randbits(32) if token is None else token
        require(type(self.token) is int and 0 <= self.token <= 0xffffffff, 'invalid token')
        identity(self.exchange(b'?\n'), self.manifest['build_id'])
        self.identified = True
        command = 'P,'+','.join(map(str, [self.token, len(times)]+times))+'\n'
        reply = self.exchange(command.encode('ascii'))
        require(fields(reply, 'GENARMED', 3) == [self.token, len(times), times[-1]],
                'arm acknowledgement mismatch')

    def start(self):
        # Mark before I/O so a lost acknowledgement still triggers abort cleanup.
        self.started = True
        require(fields(self.exchange(f'R,{self.token}\n'.encode('ascii')), 'GENSTART', 2)
                == [self.token, len(self.times)], 'start acknowledgement mismatch')

    def finish(self):
        deadline = time.monotonic()+self.times[-1]/1e6+10
        while True:
            line = self.reader.read_line(deadline)
            require(not line.startswith(b'GENERROR,'), 'generator reported an error')
            if line.startswith(b'GENEND,'):
                self.started = False
                return

    def abort(self):
        # Idempotent release/disarm. Never send to a device before identity has
        # been validated by the caller's completed prepare phase.
        require(self.identified, 'cannot abort an unidentified device')
        self.port.write(b'X\n'); self.port.flush()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--times', type=Path, required=True, help='JSON list of alternating press/release times in microseconds')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    manifest = load_manifest(a.manifest)
    times = json.loads(a.times.read_text()); validate_times(times)
    a.out.mkdir(parents=True, exist_ok=False)
    metadata = dict(schema=1, status='incomplete', build=manifest, times_us=times,
                    acquired_utc=datetime.now(timezone.utc).isoformat())
    meta_path = a.out/'metadata.json'
    meta_path.write_text(json.dumps(metadata, indent=2)+'\n')
    import serial
    port = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=2)
    port.dtr = False; port.rts = False
    if sys.platform != 'win32': port.exclusive = True
    port.port = a.port
    with port, (a.out/'raw.txt').open('wb') as raw:
        gen = Generator(port, raw, manifest)
        gen.prepare(times)
        try:
            gen.start(); gen.finish()
        except BaseException:
            try: gen.abort()
            except Exception: pass  # Preserve original error and incomplete evidence.
            raise
    report = parse((a.out/'raw.txt').read_bytes(), manifest['build_id'], times)
    (a.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    metadata['status'] = report['status']; meta_path.write_text(json.dumps(metadata, indent=2)+'\n')
    print(report['status'])


if __name__ == '__main__':
    main()
