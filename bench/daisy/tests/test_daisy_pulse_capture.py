# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'examples/daisy'))
import pulse_generator as gen

TIMES = [100000, 220000, 400001, 1200001]
INFO = dict(protocol=1, kind='daisy-pulse-generator', board='seed3', build_id='test',
            timer_hz=240000000, armed=False, released=True, max_edges=64,
            max_us=30000000, max_late_us=25)


def fixture():
    lines = ['GENINFO,'+json.dumps(INFO), 'GENARMED,42,4,1200001', 'GENSTART,42,4']
    lines += [f'GENEDGE,{i},{t},{t},{t+1},{int(i%2==0)}' for i, t in enumerate(TIMES)]
    lines += ['GENEND,42,4,0,1200003']
    return ('\n'.join(lines)+'\n').encode()


class Port:
    def __init__(self, response):
        self.response, self.writes = response, []
    @property
    def in_waiting(self): return len(self.response)
    def write(self, data): self.writes.append(data)
    def flush(self): pass
    def read(self, n):
        out, self.response = self.response[:n], self.response[n:]
        return out


class Tests(unittest.TestCase):
    def test_complete_transcript_and_driver(self):
        wire = fixture()
        report = gen.parse(wire, 'test', TIMES)
        self.assertEqual(report['max_lateness_us'], 1)
        port, raw = Port(wire), io.BytesIO()
        driver = gen.Generator(port, raw, {'build_id':'test'})
        driver.prepare(TIMES, token=42); driver.start(); driver.finish()
        self.assertEqual(port.writes, [b'?\n', b'P,42,4,100000,220000,400001,1200001\n', b'R,42\n'])
        self.assertEqual(raw.getvalue(), wire)
        self.assertFalse(driver.started)

    def test_identity_before_mutation(self):
        port = Port(fixture().replace(b'"test"', b'"wrong"'))
        driver = gen.Generator(port, io.BytesIO(), {'build_id':'test'})
        with self.assertRaises(ValueError): driver.prepare(TIMES)
        with self.assertRaises(ValueError): driver.abort()
        self.assertEqual(port.writes, [b'?\n'])

    def test_lost_start_ack_can_abort(self):
        port = Port(fixture().replace(b'GENSTART,42,4', b'GENSTART,43,4'))
        driver = gen.Generator(port, io.BytesIO(), {'build_id':'test'})
        driver.prepare(TIMES, token=42)
        with self.assertRaises(ValueError): driver.start()
        self.assertTrue(driver.started)
        driver.abort(); self.assertEqual(port.writes[-1], b'X\n')

    def test_invalid_schedules(self):
        for times in [[], [100000], [99999,200000], [100000,100099], [100001,100000],
                      [100000,30000001], [100000,True], [100000,200000.0], [100000,200000,300000],
                      list(range(100000,166000,1000))]:
            with self.assertRaises(ValueError): gen.validate_times(times)

    def test_corrupt_or_aborted_capture(self):
        wire = fixture()
        for data in [wire[:-1], wire.replace(b'GENEDGE,2', b'GENEDGE,1'),
                     wire.replace(b'1200002', b'1200027'),
                     wire.replace(b'GENEND,42,4,0', b'GENEND,42,4,3'),
                     wire.replace(b'GENEND,42,4,0', b'GENEND,42,3,0'),
                     wire.replace(b'GENARMED,42', b'GENARMED,43'),
                     wire.replace(b'GENEDGE,0,100000', b'GENEDGE,0,100001'),
                     wire.replace(b'GENEDGE,0,100000,100000,100001,1', b'GENEDGE,0,100000,100000,100001,0'),
                     wire.replace(b'GENEND,42,4,0,1200003', b'GENEND,42,4,0,0'),
                     wire.replace(b'GENSTART,42', b'GENSTART,-42')]:
            with self.assertRaises(ValueError): gen.parse(data, 'test', TIMES)

    def test_physical_evidence_rejects_extra_edges_and_jitter(self):
        report = gen.parse(fixture(), 'test', TIMES)
        edges = [10+t*1.00004/1e6 for t in TIMES]
        self.assertEqual(gen.inspect_physical(report, True, edges)['status'], 'pass')
        for initial, bad in [(False, edges), (True, edges[:-1]), (True, edges+[12]),
                             (True, edges[:2]+[float('nan')]+edges[3:]), (True, list(reversed(edges)))]:
            with self.assertRaises(ValueError): gen.inspect_physical(report, initial, bad)
        jitter = edges[:]; jitter[2] += 30e-6
        self.assertEqual(gen.inspect_physical(report, True, jitter)['status'], 'fail')
        fast = [10+t*1.002/1e6 for t in TIMES]
        self.assertIn('clock_scale', gen.inspect_physical(report, True, fast)['failures'])


if __name__ == '__main__': unittest.main()
