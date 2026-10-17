#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""C++ timing retention -> wire parser -> physical comparison, all synthetic."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import load_capture as load
from daisy_scope import inspect_timing_service
DIAGNOSTIC, REPLAY = [Path(sys.argv.pop(1)).resolve() for _ in range(2)]


def rehash(data):
    lines=data.splitlines(keepends=True)
    lines[-1]=f'LOADEND,42,{load.capture.fnv(b"".join(lines[1:-1]))}\n'.encode()
    return b''.join(lines)


def synthetic():
    first=subprocess.check_output([str(REPLAY),'--synthetic-v2','0']).splitlines()[0]
    info=json.loads(first[5:]); info.update(load_protocol=1,timing_diagnostics=1,timer_hz=240000000)
    return rehash(b'INFO,'+json.dumps(info).encode()+b'\n'+
        b'LOADSTART,42,2,2000,250,-1,16,0,0\n'+
        subprocess.check_output([str(DIAGNOSTIC),'--synthetic'])+
        b'LOADSTATS,2000,0,0,0,0,2000000,0,0,0,0,0,0,0,0,0,0,0,240000000\nLOADEND,42,0\n')


def mutate(data, second, kind, field, value, previous=False):
    lines=data.decode().splitlines(True)
    index=next(i for i,s in enumerate(lines) if s.startswith(f'D,{second},{kind},'))
    words=lines[index].strip().split(',')
    words[3+(0 if previous else 11)+load.diagnostics.NAMES.index(field)] = str(value)
    lines[index]=','.join(words)+'\n'
    return rehash(''.join(lines).encode())


class DiagnosticsTests(unittest.TestCase):
    def test_cpp_roundtrip_and_scope(self):
        with tempfile.TemporaryDirectory() as td:
            data=synthetic(); s=load.save_analysis(data,Path(td),'synthetic',REPLAY,True)
            self.assertEqual(s['checks']['status'],'pass')
            self.assertEqual(s['timing_diagnostics']['retained_witnesses'],20)
            self.assertEqual(len(json.loads((Path(td)/'timing.json').read_text())),2)
            _,_,b=load.parse(data)
            # Known clock drift and offset; each synthetic GPIO write lasts 40 ticks.
            edges=[(i*.001+.0000005+j*.000040)*1.00004+1 for i in range(2000) for j in (0,1)]
            report=inspect_timing_service(b,edges,240000000)
            self.assertEqual(report['original_acceptance'],'pass')
            self.assertLess(report['max_witness_interval_outside_cpu_bracket_us'],.001)
            self.assertLess(report['max_witness_width_outside_cpu_bracket_us'],.001)
            # Glitch the SAME retained width event: diagnostics must not convert
            # a physical disagreement into a qualified pass.
            edges[1]+=.000020
            report=inspect_timing_service(b,edges,240000000)
            self.assertEqual(report['original_acceptance'],'fail')
            self.assertGreater(report['max_witness_width_outside_cpu_bracket_us'],19)
            self.assertTrue(report['buckets'][0]['scope_width_peak_retained'])
            with self.assertRaises(ValueError): inspect_timing_service(b,edges[:-2],240000000)

    def test_missing_reordered_or_unsupported_diagnostics(self):
        data=synthetic(); lines=data.splitlines(keepends=True)
        for bad in (b''.join(x for x in lines if not x.startswith(b'D,1,5,')),
                    data.replace(b'D,1,5,',b'D,1,6,'),
                    data.replace(b'"timing_diagnostics": 1',b'"timing_diagnostics": 0'),
                    data.replace(b'T,1,1000',b'T,1,999'),
                    data[:-1]):
            with self.assertRaises(ValueError): load.parse(rehash(bad) if bad.endswith(b'\n') else bad)

    def test_unsupported_embedded_printf_output_is_rejected(self):
        data=synthetic()
        # The first hardware diagnostic download exposed unsupported long-long
        # formatting as literal "lu" tokens. Never accept or repair those rows.
        bad=data.replace(b'D,0,0,0,9600,',b'D,0,0,lu,lu,')
        self.assertNotEqual(bad,data)
        with self.assertRaises(ValueError): load.parse(rehash(bad))
        # Keep the embedded formatter on C89 conversions; a host libc passing
        # long-long tests cannot establish newlib-nano compatibility.
        source=(ROOT/'examples/daisy/diagnostics.h').read_text()
        self.assertNotIn('%ll',source)

    def test_rehashed_clock_or_peak_corruption_rejected(self):
        data=synthetic()
        for kind,field,value in ((3,'work_us',41),(3,'end_elapsed',999999),
                                (2,'seq',999),(6,'rise_after',15),
                                (0,'time_us',1),(4,'begin_tick',100)):
            with self.subTest(field=field),self.assertRaises(ValueError):
                load.parse(mutate(data,0,kind,field,value))

    def test_long_elapsed_math_and_raw_wrap(self):
        # Exercise the old problematic elapsed range and the full one-hour
        # supported range without pretending this is hardware soak evidence.
        hz=240000000
        for us in (1611000000,1668000000,3599999000):
            ticks=us*240+239; start=(ticks+0xfffffff0)&0xffffffff
            values=[ticks,ticks+9601,us//1000,us,41,start,
                    (start+120)&0xffffffff,(start+160)&0xffffffff,
                    (start+9601)&0xffffffff,(start+9721)&0xffffffff,(start+9761)&0xffffffff]
            self.assertEqual(load.diagnostics.observation(values,hz,3600000000)['time_us'],us)
        values[0]=1<<64
        with self.assertRaises(ValueError): load.diagnostics.observation(values,hz,3600000000)


if __name__=='__main__': unittest.main()
