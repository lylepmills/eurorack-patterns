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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples/daisy'))
import load_capture as load
import load_campaign as campaign
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


class LoadTests(unittest.TestCase):
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

    def fake(self, td, *, mismatch=False, pending=False, ack_bad=False, disconnect=False):
        data=synthetic(); writes=[]
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
                else:
                    token=command.split(b',')[1]
                    payload=b''.join(lines[1:]).replace(b'START,42,',b'START,'+token+b',').replace(b'END,42,',b'END,'+token+b',')
                    self.pending=rehash(lines[0]+payload).split(b'\n',1)[1]
                    if ack_bad: self.pending=self.pending.replace(b',0,6000,250,-1,16,0,0\n',b',0,5000,250,-1,16,0,0\n',1)
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
        manifest.write_text(json.dumps(dict(kind='eurorack-patterns-daisy-bench',protocol=2,load_protocol=1,
              build_id='synthetic',artifacts_sha256={'patterns_daisy.bin':hashlib.sha256(b'test').hexdigest()})))
        a=argparse.Namespace(manifest=manifest,port='mock-only',out=root/'capture',seconds=6,mode='trace',target=.25,
              audio_permille=-1,block_size=16,usb_hz=0,stationary=False,download_timeout=2,replay=REPLAY)
        with patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=Serial)}),contextlib.redirect_stdout(io.StringIO()):
            if mismatch or pending or ack_bad or disconnect:
                with self.assertRaises((ValueError,OSError)):load.record(a)
            else:self.assertEqual(load.record(a),0)
        return a.out,writes

    def test_mock_serial_complete(self):
        with tempfile.TemporaryDirectory() as td:
            out,writes=self.fake(td)
            self.assertEqual(len(writes),2)
            self.assertEqual(json.loads((out/'metadata.json').read_text())['status'],'complete')

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
