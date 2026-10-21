#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Synthetic load protocol and mocked USB only; no hardware is opened."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import load_capture as load
import load_campaign as campaign
import button_campaign
REPLAY = Path(sys.argv.pop(1)).resolve()


def rehash(data):
    lines = data.splitlines(keepends=True)
    token = lines[1].split(b',')[1]
    lines[-1] = b'LOADEND,'+token+b','+str(load.capture.fnv(b''.join(lines[1:-1]))).encode()+b'\n'
    return b''.join(lines)


def synthetic(soak=False):
    lines = subprocess.check_output([str(REPLAY), '--synthetic-v2', '0']).splitlines(keepends=True)
    info = json.loads(lines[0][5:]); info.update(load_protocol=1, timer_hz=120000000)
    identity = b'INFO,'+json.dumps(info).encode()+b'\n'
    if soak:
        header = b'LOADSTART,42,1,2000,250,650,16,0,0\n'
        body = b''.join(f'S,{i},1000,{i*1000000},{i*1000000+999000},0,0,0,0,40,1000,1234,1235\n'.encode() for i in range(2))
        stats = b'LOADSTATS,2000,0,0,0,0,2000000,6000,26000,40000,0,0,0,0,0,0,0,40000,120000000\n'
    else:
        header = b'LOADSTART,42,0,6000,250,-1,16,0,0\n'
        body = b''.join(lines[1:])
        stats = b'LOADSTATS,6000,0,0,0,0,6000000,0,0,0,0,0,0,0,0,0,0,0,120000000\n'
    return rehash(identity+header+body+stats+b'LOADEND,42,0\n')


def fault_trace(scenario, edit=None, delay=0):
    """Synthetic controls and synthetic load counters, never measured evidence."""
    command = [str(REPLAY), '--synthetic-timed', str(scenario), str(delay)] if delay else [str(REPLAY), '--synthetic-v2', str(scenario)]
    data = subprocess.check_output(command)
    info, run, rows = load.capture.parse(data)
    info.update(load_protocol=1, load_faults=1, timer_hz=120000000)
    if edit: edit(run, rows)
    # Re-encode and rehash so rejection tests reach semantic checks, not just CRC.
    stimulus = 'STIMULUS,' + ','.join(str(run['stimulus'][k]) for k in ('trigger_us','begin_us','end_us')) + '\n'
    if delay: stimulus += f"FAULTTIMING,{delay}\n"
    records = []
    for i, r in enumerate(rows):
        r['seq'] = i; r['missed'] = r['time_us']//1000-i
        r['cadence_valid'] = int(i == 0 or r['time_us']-rows[i-1]['time_us'] <= 10000)
        records.append(('D,' + ','.join(str(r[k]) for k in load.capture.COLUMNS) + '\n').encode())
    digest = load.capture.fnv(stimulus.encode()+b''.join(records))
    missed = rows[-1]['missed']
    header = f'TIMEDFAULTLOADSTART,42,0,6000,250,650,16,500,0,{scenario},{delay}\n' if delay else f'FAULTLOADSTART,42,0,6000,250,650,16,500,0,{scenario}\n'
    return rehash(b'INFO,' + json.dumps(info).encode()+b'\n' +
        (header + f'START,42,{scenario},6000,250,0\n').encode() +
        stimulus.encode() + ('COLUMNS,'+','.join(load.capture.COLUMNS)+'\n').encode() + b''.join(records) +
        f'END,42,{len(rows)},{missed},0,0,0,{digest},6000000\n'.encode() +
        f'LOADSTATS,{len(rows)},{missed},0,0,0,6000000,18000,26000,40000,0,0,0,2700,172800,0,0,40000,120000000\nLOADEND,42,0\n'.encode())


class LoadTests(unittest.TestCase):
    def test_timed_boundaries_independent_raw_dwell_oracle(self):
        cases = {5: [(8000,[2,1]),(10000,[2,1]),(12000,[1])],
                 6: [(608000,[1]),(610000,[1]),(612000,[2,1])],
                 7: [(8000,[1]),(10000,[1]),(12000,[1,1])],
                 8: [(8000,[1,1]),(610000,[1,1])]}
        for scenario, delays in cases.items():
            for delay, expected in delays:
                with self.subTest(scenario=scenario, delay=delay), tempfile.TemporaryDirectory() as td:
                    data = fault_trace(scenario, delay=delay)
                    summary = load.save_analysis(data, Path(td), 'synthetic', REPLAY)
                    self.assertEqual(summary['checks']['status'], 'pass')
                    _, control_data, _ = load.parse(data)
                    _, run, rows = load.capture.parse(control_data)
                    self.assertEqual(run['fault_delay_us'], delay)
                    name = next(k for k,v in load.FAULT_SCENARIOS.items() if v == scenario)
                    review = button_campaign.review_controls(summary, rows, name)
                    self.assertEqual(review['expected_gestures'], expected)
                    # The oracle cannot infer its expectation from actual outputs.
                    output_free = [{k:v for k,v in r.items() if k in ('time_us','pressed')} for r in rows]
                    oracle = button_campaign.timed_expectations(output_free, scenario, run['stimulus'])
                    self.assertEqual(oracle, review['boundary'])
                    first = next(r for r in rows if r['gesture'])
                    first['gesture'] = 1 if first['gesture'] == 2 else 2
                    with self.assertRaisesRegex(ValueError, 'actions/deadlines'):
                        button_campaign.review_controls(summary, rows, name)

    def test_timed_evidence_and_capability_cannot_be_relabelled(self):
        data = fault_trace(5, delay=8000)
        # Recompute the outer checksum to exercise inner checksum and exact
        # envelope matching, rather than accidentally stopping at LOADEND.
        variants = [
            data.replace(b'FAULTTIMING,8000', b'FAULTTIMING,8001'),
            data.replace(b',0,5,8000\n', b',0,5,8001\n'),
            data.replace(b'"fault_timing": 1', b'"fault_timing": 0'),
            data.replace(b'FAULTTIMING,8000\n', b'FAULTTIMING,8000\nFAULTTIMING,8000\n'),
            data.replace(b'FAULTTIMING,8000\n', b''),
        ]
        for variant in variants:
            with self.assertRaises(ValueError): load.parse(rehash(variant))
        c = dict(mode=0,duration_ms=6000,target_milli=250,audio_permille=650,
                 block_size=16,usb_hz=500,startup_held=0,scenario=5)
        for delay in (-1,1000001,True,1.5):
            with self.assertRaises(ValueError): load.validate_config(dict(c,fault_delay_us=delay))
        for scenario in (0,9,10):
            with self.assertRaises(ValueError): load.validate_config(dict(c,scenario=scenario,fault_delay_us=1))

    def test_loaded_faults_replay_and_keep_load_checks(self):
        for scenario in range(5, 11):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as td:
                s = load.save_analysis(fault_trace(scenario), Path(td), 'synthetic', REPLAY)
                self.assertEqual(s['checks']['status'], 'pass')
                self.assertEqual(s['fault']['stimulus_status'], 'completed')
                self.assertEqual(s['fault']['allowed_missed'], 25 if scenario < 8 else 0)
                self.assertEqual(s['fault']['injected_adc_samples'], 0 if scenario < 8 else 250 if scenario == 8 else 1000)
                self.assertFalse(s['checks']['independent_hardware_review'])
                for key in ('callback_over_budget', 'late_callback_intervals', 'usb_sequence_errors', 'adc_failures'):
                    bad = json.loads(json.dumps(s)); bad['counters'][key] = 1
                    self.assertFalse(load.assess(bad)); self.assertIn(key, bad['checks']['failures'])

    def test_loaded_fault_does_not_hide_unrelated_missed_slots(self):
        for scenario in range(5, 11):
            # A single extra missing slot is below the 10-ms cadence threshold.
            data = fault_trace(scenario, lambda run, rows: rows.pop(next(i for i, r in enumerate(rows) if r['time_us'] == 3000000)))
            s, _, _ = load.parse(data)
            self.assertFalse(load.assess(s))
            self.assertIn('unexpected missed service slots', s['checks']['failures'])

    def test_stall_entry_partway_through_serviceable_slot(self):
        # Hardware exposed the difference between a late sample within its
        # 1-ms slot and a missed slot. Stall() precedes Due()/Take(); an IRQ
        # can defer it to partway through the slot that the stall then consumes.
        def phase(offset):
            def edit(run, rows):
                for key in run['stimulus']: run['stimulus'][key] += offset
                for r in rows: r['time_us'] += offset
            return edit
        for scenario in (5, 6, 7):
            for offset in (1, 204, 700):
                with self.subTest(scenario=scenario, offset=offset), tempfile.TemporaryDirectory() as td:
                    data = fault_trace(scenario, phase(offset))
                    s = load.save_analysis(data, Path(td), 'synthetic', REPLAY)
                    self.assertEqual(s['checks']['status'], 'pass')
                    self.assertEqual(s['fault']['allowed_missed'], 25)
        # A COMPLETE missed slot before entry or after recovery is still bad.
        for when in (299000, 326000):
            def extra(run, rows):
                rows.pop(next(i for i, r in enumerate(rows) if r['time_us'] == when))
                phase(204)(run, rows)
            s, _, _ = load.parse(fault_trace(5, extra))
            self.assertFalse(load.assess(s))
        # A delayed recovery that loses another slot is not excused by rounding.
        def late_recovery(run, rows):
            phase(204)(run, rows)
            rows.pop(next(i for i, r in enumerate(rows) if r['time_us'] == 325204))
        s, _, _ = load.parse(fault_trace(5, late_recovery))
        self.assertFalse(load.assess(s))
        self.assertIn('late service recovery', s['fault']['failures'])

    def test_predecessor_jitter_is_not_a_missing_service_slot(self):
        # Measured counterexample: entry958041 - predecessor957033 =1008us.
        # Both lie in adjacent schedule slots. Do not turn legitimate phase
        # movement into loss; an entire missing predecessor slot still fails.
        def shifted_entry(run, rows):
            run['stimulus']['begin_us'] += 8
            run['stimulus']['end_us'] += 8
            recovery = next(r for r in rows if r['time_us'] >= run['stimulus']['end_us']-8)
            recovery['time_us'] += 8
        data = fault_trace(5, shifted_entry, delay=8000)
        summary, _, _ = load.parse(data)
        self.assertTrue(load.assess(summary),summary['checks'])
        def lost_predecessor(run, rows):
            shifted_entry(run,rows)
            begin = run['stimulus']['begin_us']
            previous = next(r for r in reversed(rows) if r['time_us'] < begin)
            rows.remove(previous)
        summary, _, _ = load.parse(fault_trace(5,lost_predecessor,delay=8000))
        self.assertFalse(load.assess(summary))
        self.assertIn('missing service before fault',summary['checks']['failures'])

    def test_missing_or_incomplete_loaded_stimulus_is_not_success(self):
        def no_press(run, rows):
            run['stimulus'] = dict.fromkeys(run['stimulus'], -1)
            for r in rows: r['pressed'] = 0; r['injected'] = 0; r['adc_valid'] = 1
        s, _, _ = load.parse(fault_trace(8, no_press))
        self.assertFalse(load.assess(s)); self.assertIn('not_triggered', s['fault']['failures'][0])
        _, run, rows = load.capture.parse(subprocess.check_output([str(REPLAY), '--synthetic-v2', '5']))
        for status in ('not_triggered', 'incomplete'):
            f = load.fault_evidence(dict(run, stimulus_status=status), rows)
            self.assertEqual(f['allowed_missed'], 0); self.assertTrue(f['failures'])

    def test_stall_allowance_is_tied_to_actual_bounds(self):
        _, run, rows = load.capture.parse(subprocess.check_output([str(REPLAY), '--synthetic-v2', '5']))
        for key, delta in [('begin_us', 1001), ('end_us', -1000), ('trigger_us', -2000)]:
            bad = dict(run, stimulus=dict(run['stimulus']))
            bad['stimulus'][key] += delta
            self.assertTrue(load.fault_evidence(bad, rows)['failures'])
        long_rows = json.loads(json.dumps(rows))
        begin = run['stimulus']['begin_us']
        for r in long_rows:
            if r['time_us'] >= begin: r['time_us'] += 3000
        bad = dict(run, stimulus=dict(run['stimulus'], end_us=run['stimulus']['end_us']+3000))
        self.assertIn('service stall duration', load.fault_evidence(bad, long_rows)['failures'])

    def test_fault_envelope_capability_and_scenario_must_match(self):
        data = fault_trace(5)
        for old, new in [(b'"load_faults": 1', b'"load_faults": 0'),
                         (b',500,0,5\n', b',500,0,6\n'),
                         (b',500,0,5\n', b',500,0,0\n'),
                         (b'FAULTLOADSTART,42,0,', b'FAULTLOADSTART,42,1,')]:
            with self.subTest(new=new), self.assertRaises(ValueError): load.parse(rehash(data.replace(old, new)))
        c = dict(mode=0, duration_ms=6000, target_milli=250, audio_permille=650, block_size=16, usb_hz=500, startup_held=0)
        for scenario in (1, 4, 11, 12):
            with self.assertRaises(ValueError): load.validate_config(dict(c, scenario=scenario))
        with self.assertRaises(ValueError): load.validate_config(dict(c, scenario=9, target_milli=750))

    def test_trace_replays_exact_original_controls(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td); data = synthetic()
            s = load.save_analysis(data, out, 'synthetic', REPLAY)
            self.assertEqual(s['checks']['status'], 'pass')
            self.assertIn('6000 samples', s['replay'])
            self.assertEqual(s['actions'], 2)
            self.assertFalse(load.assess(s, stationary=True))

    def test_continuous_soak_aggregates_and_no_replay_claim(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td); s = load.save_analysis(synthetic(True), out, 'synthetic', REPLAY, True)
            self.assertEqual(s['checks']['status'], 'pass')
            self.assertIn('aggregates', s['replay'])
            self.assertEqual(len((out/'buckets.csv').read_text().splitlines()), 3)

    def test_bounds(self):
        c = dict(mode=1, duration_ms=3600000, target_milli=250, audio_permille=700,
                 block_size=96, usb_hz=500, startup_held=1)
        load.validate_config(c)
        for key, value in [('duration_ms',3601000),('duration_ms',1501),('mode',3),
                           ('audio_permille',701),('audio_permille',-2),('block_size',17),
                           ('usb_hz',1),('startup_held',2),('target_milli',1001)]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                load.validate_config(dict(c, **{key:value}))

    def test_corrupt_and_truncated_evidence_fails(self):
        data = synthetic(True); lines = data.splitlines(keepends=True)
        for bad in [data[:-1], b''.join(lines[:-1]), data+b'extra\n',
                    data.replace(b'S,0,1000',b'S,0,1001'), data.replace(b'LOADEND,42',b'LOADEND,43')]:
            with self.subTest(size=len(bad)), self.assertRaises(ValueError): load.parse(bad)

    def test_rehashed_but_invalid_bucket_timeline_fails(self):
        data = synthetic(True)
        replacements = [(b'S,1,', b'S,2,'), (b'S,0,1000,0,999000',b'S,0,1000,1,999'),
                        (b'S,0,1000,0,999000,0',b'S,0,1000,0,999000,1'),
                        (b'LOADSTATS,2000',b'LOADSTATS,1999'),
                        (b',40000,120000000\n',b',40001,120000000\n')]
        for old,new in replacements:
            with self.subTest(old=old),self.assertRaises(ValueError): load.parse(rehash(data.replace(old,new)))
        with self.assertRaisesRegex(ValueError,'buckets'): load.parse(rehash(b''.join(data.splitlines(keepends=True)[:2]+data.splitlines(keepends=True)[3:])))

    def test_failed_measurement_is_retained_but_not_a_pass(self):
        s,_,_ = load.parse(synthetic(True))
        for key in ('callback_over_budget','late_callback_intervals','bad_callback_size',
                    'usb_malformed','usb_sequence_errors','rx_dropped','buffer_overflow'):
            altered = json.loads(json.dumps(s)); altered['counters'][key] = 1
            self.assertFalse(load.assess(altered))
            self.assertIn(key,altered['checks']['failures'])
        for count in (0,3000,12000):
            altered=json.loads(json.dumps(s)); altered['counters']['callbacks']=count
            self.assertFalse(load.assess(altered))

    def test_tail_missing_slot_is_not_success(self):
        s,_,_ = load.parse(synthetic(True)); s['counters']['samples']-=1
        self.assertFalse(load.assess(s))
        self.assertIn('incomplete service-slot coverage',s['checks']['failures'])

    def test_usb_stimulus_proof_required(self):
        s,_,_=load.parse(synthetic(True)); s['configuration']['usb_hz']=100
        self.assertFalse(load.assess(s))
        s['counters']['usb_packets']=130
        writer=dict(packets=130,skipped_slots=0,error=None)
        self.assertTrue(load.assess(s,writer=writer))
        self.assertTrue(load.assess(s,writer=dict(writer,skipped_slots=1)))
        for key,value in [('packets',131),('skipped_slots',40),('error','write timeout'),('max_lateness_s',.06)]:
            self.assertFalse(load.assess(s,writer=dict(writer,**{key:value})))

    def test_one_hour_of_buckets_is_complete(self):
        lines=synthetic(True).splitlines(keepends=True)
        lines[1]=b'LOADSTART,42,1,3600000,250,650,16,0,0\n'
        body=[f'S,{i},1000,{i*1000000},{i*1000000+999000},0,0,0,0,40,1000,1234,1235\n'.encode() for i in range(3600)]
        stats=b'LOADSTATS,3600000,0,0,0,0,3600000000,10800000,26000,40000,0,0,0,0,0,0,0,40000,120000000\n'
        s,controls,buckets=load.parse(rehash(b''.join(lines[:2]+body+[stats,lines[-1]])))
        self.assertTrue(load.assess(s,stationary=True)); self.assertIsNone(controls)
        self.assertEqual(len(buckets),3600)

    def test_packet_bytes_and_short_writes(self):
        for seq in (0,1,255,0xffffffff):
            p=load.packet(seq)
            self.assertEqual(len(p),64); self.assertEqual(p[0],0xa5); self.assertEqual(p[-1],0x5a)
            self.assertEqual(int.from_bytes(p[1:5],'little'),seq)
            self.assertEqual(p[5:63],bytes((seq+i)&255 for i in range(5,63)))
        port=types.SimpleNamespace(write=lambda data: 1)
        writer=load.TrafficWriter(port,100,1)
        writer.start_at=0; writer.end_at=100
        writer.stop_event=types.SimpleNamespace(wait=lambda delay:False)
        with patch.object(load.time,'monotonic',return_value=0): writer.run()
        self.assertIn('partial',writer.result['error']); self.assertEqual(writer.result['packets'],0)

    def fake(self, td, *, mismatch=False, pending=False, ack_bad=False, disconnect=False,
             fault=False, no_cap=False, wrong_scenario=False, delay=0, no_timing=False, wrong_delay=False):
        data=fault_trace(5, delay=delay) if fault else synthetic(); writes=[]
        if fault:
            # Exercise the serial handshake with audio/USB disabled; their load
            # accounting is covered separately without a real-time mock writer.
            data=rehash(data.replace(b',650,16,500,0,5',b',-1,16,0,0,5').replace(
                b',18000,26000,40000,0,0,0,2700,172800,0,0,40000,120000000\n',
                b',0,0,0,0,0,0,0,0,0,0,0,120000000\n'))
        class Serial:
            def __init__(self,**kw): self.pending=b''
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def flush(self): pass
            def write(self,command):
                writes.append(command)
                lines=data.splitlines(keepends=True)
                if command==b'?\n':
                    self.pending=lines[0]
                    if mismatch: self.pending=self.pending.replace(b'synthetic',b'wrong')
                    if pending: self.pending=self.pending.replace(b'"startup_available": false',b'"startup_available": true')
                    if no_timing: self.pending=self.pending.replace(b'"fault_timing": 1',b'"fault_timing": 0')
                    if no_cap: self.pending=self.pending.replace(b'"load_faults": 1',b'"load_faults": 0')
                else:
                    token=command.split(b',')[1]
                    payload=b''.join(lines[1:]).replace(b'START,42,',b'START,'+token+b',').replace(b'END,42,',b'END,'+token+b',')
                    self.pending=rehash(lines[0]+payload).split(b'\n',1)[1]
                    if ack_bad: self.pending=self.pending.replace(b',0,6000,250,-1,16,0,0\n',b',0,5000,250,-1,16,0,0\n',1)
                    if wrong_scenario: self.pending=self.pending.replace(b',0,0,5\n',b',0,0,6\n',1)
                    if wrong_delay: self.pending=self.pending.replace(b',0,5,8000\n',b',0,5,9000\n',1)
                    if disconnect:self.pending=self.pending[:200]
                return len(command)
            @property
            def in_waiting(self):return len(self.pending)
            def read(self,n):
                if not self.pending:raise OSError('mock disconnect')
                part,self.pending=self.pending[:min(n,19)],self.pending[min(n,19):]
                return part
        root=Path(td); binary=root/'patterns_daisy.bin'; binary.write_bytes(b'test')
        manifest=root/'manifest.json'
        manifest.write_text(json.dumps(dict(kind='eurorack-patterns-daisy-bench',protocol=2,load_protocol=1,load_faults=1,fault_timing=1,
              build_id='synthetic',artifacts_sha256={'patterns_daisy.bin':hashlib.sha256(b'test').hexdigest()})))
        a=argparse.Namespace(manifest=manifest,port='mock-only',out=root/'capture',seconds=6,mode='trace',target=.25,
              audio_permille=-1,block_size=16,usb_hz=0,stationary=False,download_timeout=2,replay=REPLAY,
              scenario='press-stall' if fault else 'manual',fault_delay_us=delay)
        began=[]
        with patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=Serial)}),contextlib.redirect_stdout(io.StringIO()):
            if mismatch or pending or ack_bad or disconnect or no_cap or wrong_scenario or no_timing or wrong_delay:
                with self.assertRaises((ValueError,OSError)):load.record(a,on_started=lambda:began.append(True))
            else:self.assertEqual(load.record(a,on_started=lambda:began.append(True)),0)
        self.assertEqual(len(began),int(not (mismatch or pending or ack_bad or no_cap or wrong_scenario or no_timing or wrong_delay)))
        return a.out,writes

    def test_timed_serial_ack_and_old_image_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake(td, fault=True, delay=8000)
            self.assertTrue(writes[1].startswith(b'T,'))
            self.assertTrue(writes[1].endswith(b',8000\n'))
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake(td, fault=True, delay=8000, no_timing=True)
            self.assertEqual(writes, [b'?\n'])
        with tempfile.TemporaryDirectory() as td:
            out, writes = self.fake(td, fault=True, delay=8000, wrong_delay=True)
            self.assertEqual(json.loads((out/'metadata.json').read_text())['status'], 'incomplete')

    def test_mock_serial_complete(self):
        with tempfile.TemporaryDirectory() as td:
            out,writes=self.fake(td)
            self.assertEqual(len(writes),2)
            self.assertEqual(json.loads((out/'metadata.json').read_text())['status'],'complete')

    def test_fault_serial_handshake_and_old_firmware_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            out,writes=self.fake(td,fault=True)
            self.assertTrue(writes[1].startswith(b'F,'))
            self.assertEqual(writes[1].split(b',')[2],b'5')
            self.assertEqual(json.loads((out/'summary.json').read_text())['configuration']['scenario'],5)
        with tempfile.TemporaryDirectory() as td:
            out,writes=self.fake(td,fault=True,no_cap=True)
            self.assertEqual(writes,[b'?\n'])
        with tempfile.TemporaryDirectory() as td:
            out,_=self.fake(td,fault=True,wrong_scenario=True)
            self.assertEqual(json.loads((out/'metadata.json').read_text())['status'],'incomplete')

    def test_preflight_mismatch_never_requests_run(self):
        for kw in ({'mismatch':True},{'pending':True}):
            with tempfile.TemporaryDirectory() as td:
                out,writes=self.fake(td,**kw)
                self.assertEqual(writes,[b'?\n'])
                self.assertEqual(json.loads((out/'metadata.json').read_text())['status'],'incomplete')

    def test_interruptions_preserve_raw(self):
        for kw in ({'ack_bad':True},{'disconnect':True}):
            with tempfile.TemporaryDirectory() as td:
                out,_=self.fake(td,**kw)
                self.assertTrue((out/'raw.txt').read_bytes())
                self.assertEqual(json.loads((out/'metadata.json').read_text())['status'],'incomplete')

    def test_campaign_stops_at_failure_and_marks_completion(self):
        for fail_at in (None,3):
            with tempfile.TemporaryDirectory() as td:
                calls=[]; out=Path(td)/'campaign'
                def record(a):
                    calls.append(a)
                    self.assertTrue((out/'campaign.json').exists())
                    self.assertTrue(a.stationary)
                    return 2 if len(calls)==fail_at else 0
                args=['load_campaign','--port','mock-only','--manifest','mock.json',
                      '--out',str(out),'--replay',str(REPLAY),'--soak-seconds','2']
                with patch.object(sys,'argv',args),patch.object(campaign.load_capture,'record',record),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(campaign.main(),2 if fail_at else 0)
                journal=json.loads((out/'campaign.json').read_text())
                self.assertEqual(len(calls),fail_at or 8)
                self.assertEqual(journal['status'],'incomplete' if fail_at else 'complete')
                if not fail_at:self.assertEqual((calls[-1].mode,calls[-1].seconds),('soak',2))


if __name__=='__main__': unittest.main()
