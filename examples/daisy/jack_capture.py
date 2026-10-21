#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Capture/replay the jack fixture. USB evidence alone is not physical validation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time
from capture import LineReader, fnv, require
import dma_memory

COLUMNS = ('seq,slot,drive_us,sample_us,adc_end_us,end_us,missed,windows,raw,'
           'last_mismatches,bad_windows,probe,adc_valid,injected,evidence,'
           'window_done,ready,patched').split(',')
CONFIG = dict(period_us=500, settle_us=150, window_size=64,
              mismatch_threshold=3, bad_windows_required=8, low_code=16384,
              high_code=49151, max_records=600000, sample_cycles_x2=1621)
TRIGGERS = ('elapsed', 'insertion-evidence', 'before-patched', 'after-patched',
            'removal-evidence', 'before-unpatched', 'after-unpatched')


def validate_plan(duration, fault, policy, trigger=0, delay=0, fault_us=25000):
    require(1000 <= duration <= 300000 and fault in (0, 1, 2) and policy in (0, 1)
            and (not fault or duration >= 3000) and 0 <= trigger < len(TRIGGERS)
            and 0 <= delay <= 64 and 500 <= fault_us <= 100000 and fault_us % 500 == 0
            and (trigger or delay == 0) and (not trigger or (fault and policy == 1))
            and (fault or fault_us == 25000), 'invalid plan')


def add_fault_arguments(parser):
    parser.add_argument('--fault', type=int, choices=(0, 1, 2), default=0,
                        help='0 none, 1 invalidate ADC evidence, 2 pause acquisition (foreground on protocols before 5)')
    parser.add_argument('--policy', type=int, choices=(0, 1), default=1)
    parser.add_argument('--trigger', type=int, choices=range(len(TRIGGERS)), default=0,
                        help=', '.join(f'{i} {name}' for i, name in enumerate(TRIGGERS)))
    parser.add_argument('--fault-delay-slots', type=int, default=0,
                        help='0–64 extra 500 us slots after the trigger observation; protocol 3')
    parser.add_argument('--fault-us', type=int, default=25000,
                        help='500–100000 us, in 500 us increments; protocol 3')


def audio_arguments(args):
    return tuple(getattr(args, k, 0) for k in ('audio_block', 'audio_permille', 'audio_off_ms'))


def validate_audio(duration, block, permille, off_ms):
    require((block, permille, off_ms) == (0, 0, 0) or
            (block in (16, 48, 96) and 0 <= permille <= 700 and
             1000 <= off_ms <= duration - 1000), 'invalid audio plan')


def add_audio_arguments(parser):
    parser.add_argument('--audio-block', type=int, choices=(0,16,48,96), default=0)
    parser.add_argument('--audio-permille', type=int, default=0)
    parser.add_argument('--audio-off-ms', type=int, default=0,
                        help='Stop audio before the final unloaded second; 0 with audio disabled')


def dsp_arguments(args):
    return tuple(getattr(args, k, 0) for k in ('dsp_voices', 'dma_kib'))


def validate_dsp(duration, block, permille, voices, kib):
    require(0 <= voices <= 32 and kib in (0, 4, 16) and
            (not (voices or kib) or (block and not permille and duration <= 30000)),
            'invalid DSP/DMA plan')


def add_dsp_arguments(parser):
    parser.add_argument('--dsp-voices', type=int, default=0)
    parser.add_argument('--dma-kib', type=int, choices=(0,4,16), default=0)
    parser.add_argument('--dma-region', type=int, choices=range(10), default=0, help='0 low SDRAM, 1 AXI SRAM (protocol 7+), 2 high SDRAM (protocol 8+), 3–9 alignment views (protocol 9; see dma_alignment.py)')
    parser.add_argument('--dma-period-us', type=int, choices=(1000,2000), default=1000)


def digital_layout(protocol, clock_diagnostic=False, diagnostic_audio=False, clock_reference=False):
    # MSO single-ended probes have four local channels per port. User-facing
    # D4 is port 1 / channel 0, exported as digital_2_0.bin by the MSO server.
    require(not clock_reference or (protocol in (6, 7, 8, 9) and not clock_diagnostic and not diagnostic_audio),
            'clock reference requires its own protocol-6/7/8/9 layout')
    require(not diagnostic_audio or (clock_diagnostic and protocol in (6, 7, 8, 9)),
            'separate diagnostic audio marker requires clock diagnostic mode')
    return [(name, i//4, i%4) for i,name in enumerate(
        ['sense','service','presence','probe'] +
        (['clock' if clock_diagnostic or clock_reference else 'audio'] if protocol >= 4 else []) +
        (['audio'] if diagnostic_audio or clock_reference else []))]


CLOCK_REFERENCE = 'M command; HSE/15 on PC9; audio on PC8; max 10 seconds; faults allowed'


def validate_clock_reference(manifest, duration, permille):
    require(manifest.get('clock_reference') == CLOCK_REFERENCE and
            manifest.get('protocol') in (6, 7, 8, 9) and 1000 <= duration <= 10000 and not permille,
            'unsupported clock reference or plan')


def validate_diagnostic_audio(manifest, diagnostic, enabled):
    require(not enabled or (diagnostic and manifest.get('clock_diagnostic_audio') ==
            'PC8 / D4 / physical pin 5; K mode only'),
            'separate diagnostic audio marker is not supported by this mode/build')


def validate_clock_diagnostic(manifest, duration, fault, permille):
    require(manifest.get('clock_diagnostic') == 'HSE/15 on PC9; K command; max 10 seconds' and
            manifest.get('protocol') in (6, 7, 8, 9) and 1000 <= duration <= 10000 and not fault and not permille,
            'unsupported clock diagnostic or plan')


def publish_json(path, value):
    """Observers must never see a half-written acknowledgement or request."""
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        json.dump(value, f); f.write('\n')
    try: temp.replace(path)
    finally: temp.unlink(missing_ok=True)


def identity(line, build_id=None, *, clock_diagnostic=False, clock_reference=False):
    require(not (clock_diagnostic and clock_reference), 'conflicting clock modes')
    require(line.startswith(b'JINFO,'), 'unexpected device; no run requested')
    info = json.loads(line[6:])
    role = ('daisy-jack-clock-reference' if clock_reference else
            'daisy-jack-clock-diagnostic' if clock_diagnostic else 'daisy-jack-bench')
    require(info.get('kind') == role and info.get('board') == 'seed3'
            and info.get('ready') is True, 'wrong firmware role or initialization failed')
    require(all(info.get(k) == v for k, v in CONFIG.items()), 'unsupported jack configuration')
    require(info.get('protocol') in (1, 2, 3, 4, 5, 6, 7, 8, 9), 'unsupported jack protocol')
    require(not clock_diagnostic or info['protocol'] in (6, 7, 8, 9), 'clock diagnostic requires protocol 6–9')
    require(not clock_reference or info['protocol'] in (6, 7, 8, 9), 'clock reference requires protocol 6–9')
    require(isinstance(info.get('build_id'), str) and len(info['build_id']) == 24,
            'missing build identity')
    if build_id: require(info['build_id'] == build_id, 'build identity mismatch')
    require(info.get('timer_hz', 0) > 0 and info.get('adc_hz', 0) > 0, 'missing clocks')
    return info


def fields(line, prefix, count):
    require(line.endswith(b'\n') and not line.endswith(b'\r\n'), 'noncanonical line')
    parts = line[:-1].split(b',')
    require(parts[0] == prefix and len(parts) == count + 1, 'malformed ' + prefix.decode())
    require(all(x and x.isdigit() for x in parts[1:]), 'invalid unsigned fields')
    values = list(map(int, parts[1:]))
    require(all(x <= 0xffffffff for x in values), 'field overflow')
    return values


def parse(data, build_id=None, *, clock_diagnostic=False, clock_reference=False):
    lines = data.splitlines(keepends=True)
    require(len(lines) >= 6 and data.endswith(b'\n'), 'incomplete capture')
    info = identity(lines[0], build_id, clock_diagnostic=clock_diagnostic, clock_reference=clock_reference)
    protocol = info['protocol']
    plan = fields(lines[1], b'MSTART' if clock_reference else b'KSTART' if clock_diagnostic else b'JSTART', 14 if protocol >= 7 else 12 if protocol >= 6 else 10 if protocol >= 4 else 7 if protocol >= 3 else 4)
    token, duration, fault, policy = plan[:4]
    trigger, delay, fault_us = plan[4:7] if protocol >= 3 else (0, 0, 25000)
    validate_plan(duration, fault, policy, trigger, delay, fault_us)
    audio_plan = plan[7:10] if protocol >= 4 else [0, 0, 0]
    dsp_plan = plan[10:12] if protocol >= 6 else [0, 0]
    memory_plan = plan[12:14] if protocol >= 7 else [0, 1000]
    dma_memory.validate_plan(dsp_plan[1], *memory_plan, protocol)
    memory = None
    validate_dsp(duration, audio_plan[0], audio_plan[1], *dsp_plan)
    validate_audio(duration, *audio_plan)
    require(not clock_diagnostic or (duration <= 10000 and not fault and not audio_plan[1]),
            'unsupported clock diagnostic plan')
    require(not clock_reference or (duration <= 10000 and not audio_plan[1]),
            'unsupported clock reference plan')
    column = 3
    limit, request, reason = duration * 1000, 0, 0
    if protocol >= 2:
        finish_token, request, limit, reason = fields(lines[2], b'JFINISH', 4)
        require(finish_token == token and reason in (0, 1), 'invalid finish identity/reason')
        if reason:
            minimum = 3000000 if fault else 1000000
            boundary = (request // 500 + 1) * 500 if protocol >= 5 else ((request + 499) // 500) * 500
            require(request < duration * 1000 and limit == min(duration * 1000,
                    max(minimum, boundary)), 'invalid finish boundary')
        else:
            require(request == 0 and limit == duration * 1000, 'shortened run without finish')
        column += 1
    timing = None
    if protocol >= 3:
        values = fields(lines[column-1], b'JTIMING', 6)
        require(values[:3] == [trigger, delay, fault_us], 'fault timing plan differs')
        timing = tuple(values[3:])
        column += 1
    load = None
    if protocol >= 4:
        values = fields(lines[column-1], b'JLOAD', 12)
        require(values[:3] == audio_plan, 'audio plan differs')
        load = dict(zip(('block','permille','off_ms','end_us','callbacks','max_work_ticks',
                         'max_interval_ticks','over_budget','late_intervals','bad_size',
                         'period_ticks','timer_hz'), values))
        require(load['timer_hz'] == info['timer_hz'], 'audio clock differs')
        if not load['block']:
            require(not any(values[:11]), 'audio activity while disabled')
        else:
            require(load['callbacks'] > 1 and load['period_ticks'] == info['timer_hz'] * load['block'] // 48000,
                    'missing audio callbacks or wrong period')
            require(load['max_work_ticks'] >= load['period_ticks'] * load['permille'] // 1000,
                    'requested audio work did not run')
            require(load['max_interval_ticks'] > 0 and all(load[k] <= load['callbacks']
                    for k in ('over_budget','late_intervals','bad_size')), 'invalid audio counters')
        column += 1
    acquisition = None
    if protocol >= 5:
        values = fields(lines[column-1], b'JACQ', 14)
        acquisition = dict(zip(('tick_us','timer_priority','adc_priority','audio_priority',
            'timer_irqs','adc_irqs','max_timer_ticks','max_adc_ticks','work_ticks_low',
            'work_ticks_high','timeouts','overruns','unexpected_irqs','cpu_padding'), values))
        require(values[:4] == [50,0,0,1] and values[-1] == 1, 'unsupported acquisition scheduling')
        column += 1
    dsp = dma = None
    if protocol >= 6:
        dsp = dict(zip(('voices','frames','hash','peak','nonzero','macs'),
                       fields(lines[column-1], b'JDSP', 6)))
        require(dsp['voices'] == dsp_plan[0], 'DSP plan differs')
        if dsp['voices']:
            require(dsp['frames'] == load['callbacks']*load['block'] and
                    dsp['macs'] == dsp['frames']*dsp['voices']*32 and
                    0 < dsp['peak'] <= 10923 and 0 < dsp['nonzero'] <= dsp['frames'],
                    'DSP frame coverage or range differs')
        else:
            require(dsp == dict(voices=0,frames=0,hash=2166136261,peak=0,nonzero=0,macs=0),
                    'DSP activity while disabled')
        column += 1
        values = fields(lines[column-1], b'JDMA', 18)
        dma = dict(zip(('kib','period_us','started','completed','verified','bytes','errors',
            'corrupt_words','timeouts','skipped','first_us','last_us','max_gap_us',
            'max_transfer_ticks','irqs','max_irq_wall_ticks','irq_priority','stream'), values))
        require(dma['kib'] == dsp_plan[1], 'DMA plan differs')
        if dma['kib']:
            require(dma['period_us'] == memory_plan[1] and dma['irq_priority'] == 2 and dma['stream'] == 6,
                    'DMA configuration differs')
            require(0 < dma['started'] == dma['completed'] == dma['verified'] == dma['irqs'] and
                    dma['bytes'] == dma['verified']*dma['kib']*1024 and
                    not any(dma[k] for k in ('errors','corrupt_words','timeouts')),
                    'DMA incomplete, corrupted or failed')
            require(0 < dma['first_us'] < dma['last_us'] and dma['max_gap_us'] > 0 and
                    0 < dma['max_transfer_ticks'] <= info['timer_hz']//200 and
                    0 < dma['max_irq_wall_ticks'] <= info['timer_hz']//100,
                    'DMA timing outside bounded operation')
        else:
            require(not any(values), 'DMA activity while disabled')
        column += 1
    if protocol >= 7:
        memory = dma_memory.report(fields(lines[column-1], b'JMEM', 5), dsp_plan[1], memory_plan[0])
        column += 1
    begin, end = fields(lines[column-1], b'JFAULT', 2)
    require(lines[column] == ('JCOLUMNS,' + ','.join(COLUMNS) + '\n').encode(), 'columns differ')
    end_token, count, status, missed, failures, elapsed, digest = fields(lines[-1], b'JEND', 7)
    require(token == end_token and 0 < count <= 600000 and len(lines) == count + column + 2,
            'token/count mismatch')
    require(status == 0 and elapsed >= limit, 'aborted or unfinished run')
    require(fnv(b''.join(lines[2:-1])) == digest, 'checksum mismatch')
    if load and load['block']:
        require(0 < load['end_us'] <= elapsed + 1000, 'audio measurement window differs')
    if fault == 0: require(begin == end == 0, 'unexpected fault')
    else: require(0 < begin < end < elapsed, 'missing/incomplete fault')
    if fault == 2: require(end - begin >= fault_us, 'short service stall')
    obs = mismatch = streak = windows = last_mismatch = 0
    first = True
    ready = patched = False
    state = 0xace1
    previous = None
    rows, changes = [], []
    total_failures = 0
    armed = bool(fault and trigger == 0)
    expected_timing = (0xffffffff, 0, 2000000 if armed else 0)
    seen_empty = seen_patched = False
    for i, line in enumerate(lines[column+1:-1]):
        r = dict(zip(COLUMNS, fields(line, b'JDATA', len(COLUMNS))))
        require(r['seq'] == i, 'missing/duplicate/reordered record')
        drive, sample, adc_end, finish = (r[k] for k in ('drive_us', 'sample_us', 'adc_end_us', 'end_us'))
        require(drive < limit and drive <= sample <= adc_end <= finish <= elapsed,
                'invalid observation times')
        require(r['slot'] == drive // 500 and r['missed'] == r['slot'] - i,
                'slot or missed count mismatch')
        if previous: require(previous['end_us'] < drive and previous['slot'] < r['slot'], 'nonmonotonic observations')
        require(r['raw'] <= 65535, 'ADC out of range')
        for k in ('probe', 'adc_valid', 'injected', 'window_done', 'ready', 'patched'):
            require(r[k] in (0, 1), 'nonboolean ' + k)
        bit = state & 1
        state = (state >> 1) ^ (0xb400 if bit else 0)
        require(r['probe'] == bit, 'probe sequence mismatch')
        due = expected_timing[2]
        injected = fault == 1 and armed and due <= sample < due + fault_us
        require(r['injected'] == injected, 'injection mismatch')
        if fault == 2: require(not begin <= drive < end, 'observation inside stall')
        gap = r['missed'] != (previous['missed'] if previous else 0)
        invalid = (gap or not r['adc_valid'] or injected or sample - drive < 150 or
                   adc_end >= (r['slot'] + 1) * 500 or 16384 < r['raw'] < 49151)
        evidence = 2 if invalid else int((r['raw'] >= 49151) != bool(bit))
        require(r['evidence'] == evidence, 'evidence classification mismatch')
        completed = False
        before = (ready, patched)
        if invalid: obs = mismatch = streak = 0
        else:
            obs += 1
            mismatch += evidence == 1
            if obs == 64:
                completed = True
                windows += 1
                last_mismatch = mismatch
                obs = mismatch = 0
                if last_mismatch < 3:
                    streak = 0
                    ready, patched = True, False
                else:
                    streak = min(8, streak + 1)
                    if (first and policy == 0) or streak >= 8: ready, patched = True, True
                first = False
        require((r['window_done'], r['windows'], r['last_mismatches'], r['bad_windows'], r['ready'], r['patched']) ==
                (completed, windows, last_mismatch, streak, ready, patched), f'presence replay mismatch at seq {i}: wire {(r["window_done"], r["windows"], r["last_mismatches"], r["bad_windows"], r["ready"], r["patched"])} vs reference {(completed, windows, last_mismatch, streak, ready, patched)}')
        if fault and trigger and not armed:
            empty = seen_empty and ready and not patched
            inserted = seen_patched and ready and patched
            candidates = (
                False, empty and evidence == 1,
                empty and streak == 7 and obs == 63 and mismatch >= 3,
                seen_empty and ready and patched and not before[1],
                inserted and evidence == 0 and bit == 1,
                inserted and obs == 63 and mismatch < 3,
                seen_patched and ready and not patched and before[1])
            if candidates[trigger]:
                armed = True
                expected_timing = (i, finish, (r['slot'] + 1 + delay) * 500)
        seen_empty |= ready and not patched
        seen_patched |= seen_empty and ready and patched
        if before != (ready, patched): changes.append(dict(seq=i, time_us=adc_end, ready=ready, patched=patched))
        total_failures += not r['adc_valid']
        rows.append(r)
        previous = r
    require(missed == rows[-1]['missed'] and failures == total_failures, 'completion counter mismatch')
    # Catch a whole missing tail slot, while allowing a last conversion to finish past the deadline.
    require(rows[-1]['slot'] == (limit - 1) // 500, 'missing final scheduled slot')
    if protocol >= 3: require(timing == expected_timing, 'fault trigger differs from first eligible observation')
    if fault: require(armed and begin >= expected_timing[2], 'requested fault never armed or began early')
    if fault == 1:
        invalid_rows = [r for r in rows if r['injected']]
        recovery = [r for r in rows if r['sample_us'] >= expected_timing[2] + fault_us]
        require(invalid_rows and recovery and begin == invalid_rows[0]['sample_us'] and
                end == recovery[0]['sample_us'], 'ADC fault boundary mismatch')
    if fault == 2:
        before = [r for r in rows if r['drive_us'] < begin]
        after = [r for r in rows if r['drive_us'] >= end]
        require(before and after and before[-1]['end_us'] <= begin and
                before[-1]['drive_us'] < expected_timing[2] and
                after[0]['missed'] > before[-1]['missed'], 'stall missing from schedule')
    run = dict(token=token, duration_ms=duration, fault=fault, policy=policy,
               count=count, missed=missed, adc_failures=failures, elapsed_us=elapsed,
               fault_begin_us=begin, fault_end_us=end)
    if protocol >= 2:
        run.update(finish_reason='operator' if reason else 'duration',
                   finish_request_us=request, acquisition_limit_us=limit)
    if protocol >= 3:
        run.update(trigger=trigger, fault_delay_slots=delay, fault_duration_us=fault_us,
                   trigger_seq=timing[0], trigger_us=timing[1], fault_due_us=timing[2])
    if load is not None: run['audio'] = load
    if dsp is not None: run.update(dsp=dsp, dma=dma)
    if memory is not None: run['dma_memory'] = memory
    if acquisition is not None:
        require(acquisition['adc_irqs'] == count and acquisition['timer_irqs'] >= count * 9,
                'acquisition interrupt coverage differs')
        require(not any(acquisition[k] for k in ('timeouts','overruns','unexpected_irqs')),
                'acquisition peripheral failure')
        run['acquisition'] = acquisition
    return info, run, rows, changes


def analyze(data, build_id=None, *, clock_diagnostic=False, clock_reference=False):
    info, run, rows, changes = parse(data, build_id, clock_diagnostic=clock_diagnostic, clock_reference=clock_reference)
    return dict(protocol_integrity='verified', replay='passed',
                hardware_validation=('clock diagnostic only; no behavior qualification' if clock_diagnostic
                                     else 'pending independent scope and fixture review'),
                build_id=info['build_id'], run=run, state_changes=changes,
                invalid_observations=sum(r['evidence'] == 2 for r in rows),
                raw_min=min(r['raw'] for r in rows), raw_max=max(r['raw'] for r in rows),
                final_ready=bool(rows[-1]['ready']), final_patched=bool(rows[-1]['patched']),
                raw_sha256=hashlib.sha256(data).hexdigest())


class FinishRequest:
    """The serial owner alone sends a finish; another process only writes a file."""
    def __init__(self, path, token, port):
        self.path, self.token, self.port = path, token, port
        self.sent = False

    def poll(self):
        if self.sent or not self.path.exists(): return
        request = json.loads(self.path.read_text())
        require(type(request.get('token')) is int and request == {'token': self.token},
                'finish request token differs')
        command = f'JF,{self.token}\n'.encode()
        require(self.port.write(command) == len(command), 'incomplete finish write')
        self.port.flush()
        self.sent = True


def request_finish(out):
    meta = json.loads((out / 'metadata.json').read_text())
    require(meta['build'].get('kind') == 'eurorack-patterns-daisy-jack-bench' and
            meta['build'].get('protocol') in (2, 3, 4, 5, 6, 7, 8, 9), 'firmware has no clean finish support')
    if (out / 'acquisition-complete.json').exists() or meta['status'] == 'complete':
        return 'Acquisition already finished; download/review may still be running.'
    started = json.loads((out / 'started.json').read_text())
    token = started['token']
    require(type(token) is int and 0 <= token <= 0xffffffff, 'invalid started token')
    path = out / 'finish-request.json'
    publish_json(path, {'token': token})
    return 'Finish requested; the serial owner will close acquisition and preserve its download.'


def capture(a):
    manifest = json.loads(a.manifest.read_text())
    diagnostic = getattr(a, 'clock_diagnostic', False)
    reference = getattr(a, 'clock_reference', False)
    require(not (reference and diagnostic), 'conflicting clock modes')
    if reference: validate_clock_reference(manifest, a.seconds*1000, a.audio_permille)
    if diagnostic: validate_clock_diagnostic(manifest, a.seconds*1000, a.fault, a.audio_permille)
    require(manifest.get('kind') == 'eurorack-patterns-daisy-jack-bench' and manifest.get('protocol') in (1, 2, 3, 4, 5, 6, 7, 8, 9),
            'wrong manifest role')
    validate_plan(a.seconds * 1000, a.fault, a.policy, a.trigger, a.fault_delay_slots, a.fault_us)
    require(manifest['protocol'] >= 3 or (a.trigger, a.fault_delay_slots, a.fault_us) == (0, 0, 25000),
            'configurable fault timing requires protocol 3')
    audio_plan = audio_arguments(a)
    validate_audio(a.seconds * 1000, *audio_plan)
    require(manifest['protocol'] >= 4 or audio_plan == (0, 0, 0), 'audio load requires protocol 4')
    dsp_plan = dsp_arguments(a)
    memory_plan = dma_memory.arguments(a)
    dma_memory.validate_plan(dsp_plan[1], *memory_plan, manifest['protocol'])
    validate_dsp(a.seconds*1000, audio_plan[0], audio_plan[1], *dsp_plan)
    require(manifest['protocol'] >= 6 or dsp_plan == (0,0), 'DSP/DMA requires protocol 6–9')
    require(not a.out.exists(), 'output must be new')
    import serial
    a.out.mkdir(parents=True)
    meta = dict(schema=1, acquired_utc=datetime.now(timezone.utc).isoformat(), status='incomplete',
                build=manifest, declared_fixture=a.notes)
    def save(): (a.out / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    save()
    try:
        port = serial.Serial(port=None, baudrate=115200, timeout=.2, write_timeout=2)
        port.dtr = False; port.rts = False
        if sys.platform != 'win32': port.exclusive = True
        port.port = a.port
        with port, (a.out / 'raw.txt').open('wb') as raw:
            reader = LineReader(port, raw)
            port.write(b'M?\n' if reference else b'K?\n' if diagnostic else b'?\n'); port.flush()
            info = identity(reader.read_line(time.monotonic() + 8), manifest['build_id'], clock_diagnostic=diagnostic, clock_reference=reference)
            require(info['protocol'] == manifest['protocol'], 'manifest protocol differs')
            token = secrets.randbits(32)
            prefix = 'M' if reference else 'K' if diagnostic else 'J'
            command = f'{prefix},{token},{a.seconds * 1000},{a.fault},{a.policy}'
            if info['protocol'] >= 3: command += f',{a.trigger},{a.fault_delay_slots},{a.fault_us}'
            if info['protocol'] >= 4: command += ',' + ','.join(map(str, audio_plan))
            if info['protocol'] >= 6: command += ',' + ','.join(map(str, dsp_plan))
            if info['protocol'] >= 7: command += ',' + ','.join(map(str, memory_plan))
            command = (command + '\n').encode()
            port.write(command); port.flush()
            ack = reader.read_line(time.monotonic() + 8)
            require(ack == command.replace(prefix.encode()+b',', prefix.encode()+b'START,', 1), 'run acknowledgement differs')
            publish_json(a.out / 'started.json', dict(token=token, seconds=a.seconds))
            finish = FinishRequest(a.out / 'finish-request.json', token, port)
            poll = finish.poll if info['protocol'] >= 2 else None
            print(f'Recording up to {a.seconds} seconds; buffered download follows.', flush=True)
            deadline = time.monotonic() + a.seconds + a.download_timeout
            while True:
                line = reader.read_line(deadline, poll=poll)
                require(not line.startswith(b'JERROR,'), 'firmware error')
                if line.startswith(b'JFINISH,'):
                    ft, requested, limit, reason = fields(line, b'JFINISH', 4)
                    require(info['protocol'] >= 2 and ft == token and reason in (0, 1),
                            'invalid acquisition completion')
                    poll = None
                    publish_json(a.out / 'acquisition-complete.json', dict(
                        token=token, request_us=requested, limit_us=limit, reason=reason,
                        status='acquisition ended; complete download and checksum pending'))
                if line.startswith(b'JEND,'): break
        summary = analyze((a.out / 'raw.txt').read_bytes(), manifest['build_id'], clock_diagnostic=diagnostic, clock_reference=reference)
        dma_memory.verify_manifest(summary['run'], manifest)
        (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        meta['status'] = 'complete'; meta['raw_sha256'] = summary['raw_sha256']; save()
        print(json.dumps(summary, indent=2))
        return 2 if summary['run']['adc_failures'] else 0
    except BaseException:
        save(); raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--port', required=True); c.add_argument('--manifest', type=Path, required=True)
    c.add_argument('--out', type=Path, required=True); c.add_argument('--seconds', type=int, default=10)
    add_fault_arguments(c)
    add_audio_arguments(c)
    add_dsp_arguments(c)
    c.add_argument('--clock-diagnostic', action='store_true', help='Explicit K command; D4 carries HSE/15, not audio callbacks')
    c.add_argument('--clock-reference', action='store_true', help='Explicit M command; separate scheduling and external clock checks')
    c.add_argument('--download-timeout', type=int, default=300); c.add_argument('--notes', required=True)
    v = sub.add_parser('analyze'); v.add_argument('raw', type=Path); v.add_argument('--build-id')
    v.add_argument('--clock-diagnostic', action='store_true')
    v.add_argument('--clock-reference', action='store_true')
    f = sub.add_parser('finish'); f.add_argument('out', type=Path)
    a = p.parse_args()
    try:
        if a.mode == 'capture':
            validate_plan(a.seconds * 1000, a.fault, a.policy, a.trigger, a.fault_delay_slots, a.fault_us)
            require(a.download_timeout > 0, 'invalid download timeout')
            return capture(a)
        if a.mode == 'finish': print(request_finish(a.out)); return 0
        print(json.dumps(analyze(a.raw.read_bytes(), a.build_id, clock_diagnostic=a.clock_diagnostic, clock_reference=a.clock_reference), indent=2)); return 0
    except (ValueError, OSError, TimeoutError, KeyError) as e:
        print('ERROR:', str(e), file=sys.stderr); return 2

if __name__ == '__main__': raise SystemExit(main())
