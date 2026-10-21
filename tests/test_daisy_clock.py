# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Clock diagnostics must remain separate from normal acquisition acceptance."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'examples/daisy'),str(ROOT/'tools')]
import jack_capture as j
from inspect_daisy_clock import inspect_clock, service_cycles, clock_coordinates, audio_cycles
from test_daisy_dsp_capture import fixture


class ClockDiagnostic(unittest.TestCase):
    def test_role_and_command_cannot_be_silently_accepted_as_normal(self):
        raw,_,_=fixture(); diag=raw.replace(b'daisy-jack-bench',b'daisy-jack-clock-diagnostic').replace(b'JSTART,',b'KSTART,')
        self.assertEqual(j.parse(diag,clock_diagnostic=True)[1],j.parse(raw)[1])
        self.assertIn('no behavior qualification',j.analyze(diag,clock_diagnostic=True)['hardware_validation'])
        with self.assertRaisesRegex(ValueError,'wrong firmware role'):j.parse(diag)
        with self.assertRaisesRegex(ValueError,'wrong firmware role'):j.parse(raw,clock_diagnostic=True)
        with self.assertRaisesRegex(ValueError,'KSTART'):j.parse(diag.replace(b'KSTART',b'JSTART'),clock_diagnostic=True)
        self.assertEqual(j.digital_layout(6,True)[-1],('clock',1,0))
        self.assertEqual(j.digital_layout(6)[-1],('audio',1,0))
        self.assertEqual(j.digital_layout(6,True,True)[-2:],[('clock',1,0),('audio',1,1)])
        for protocol,diagnostic in ((5,True),(6,False)):
            with self.assertRaises(ValueError):j.digital_layout(protocol,diagnostic,True)
        manifest=dict(clock_diagnostic_audio='PC8 / D4 / physical pin 5; K mode only')
        j.validate_diagnostic_audio(manifest,True,True)
        j.validate_diagnostic_audio({},True,False) # Existing captures keep their layout.
        for m,diagnostic in (({},True),(manifest,False)):
            with self.assertRaises(ValueError):j.validate_diagnostic_audio(m,diagnostic,True)

    def test_old_image_and_unbounded_or_faulted_plans_rejected(self):
        m=dict(protocol=6,clock_diagnostic='HSE/15 on PC9; K command; max 10 seconds')
        j.validate_clock_diagnostic(m,3000,0,0)
        for duration,fault,permille in [(11000,0,0),(999,0,0),(3000,1,0),(3000,0,1)]:
            with self.assertRaises(ValueError):j.validate_clock_diagnostic(m,duration,fault,permille)
        with self.assertRaises(ValueError):j.validate_clock_diagnostic(dict(protocol=6),3000,0,0)
        # Valid old normal protocol remains supported, but cannot claim a K-mode identity.
        raw,_,_=fixture();line=raw.splitlines()[0].replace(b'daisy-jack-bench',b'daisy-jack-clock-diagnostic').replace(b'"protocol":6',b'"protocol":5')
        with self.assertRaisesRegex(ValueError,'requires protocol 6'):j.identity(line,clock_diagnostic=True)

    def test_frequency_and_complete_waveform_checks(self):
        hz=1000;period=1.00004/hz
        e=[v for i in range(3000) for v in (1+i*period,1+i*period+.47*period)]
        r=inspect_clock(e,False,[(1.1,1.9),(2.1,2.9)],hz)
        self.assertAlmostEqual(r['blocks'][0]['clock_scale_ppm'],40,places=6)
        self.assertEqual(r['cycles'],3000)
        for broken in (e[:100]+e[102:],e[:101]+[e[101]+.01*period]+e[101:],e[:-1],list(reversed(e))):
            with self.assertRaises(ValueError):inspect_clock(broken,False,[(1.1,1.9)],hz)
        with self.assertRaises(ValueError):inspect_clock(e,True,[(1.1,1.9)],hz)
        with self.assertRaises(ValueError):inspect_clock(e,False,[(.9,1.9)],hz)
        with self.assertRaises(ValueError):inspect_clock(e,False,[(1.1,1.9)],float('nan'))
        # Mux opening may expose an already-high clock. Only the first
        # partial period/half-pulse and final half-pulse have this exception.
        clipped=e[:];clipped[-1]=clipped[-2]+period*.02
        clipped[0]+=period*.3
        self.assertEqual(inspect_clock(clipped,False,[(1.1,1.9)],hz)['cycles'],3000)
        with self.assertRaisesRegex(ValueError, 'cover'):
            inspect_clock(clipped,False,[(clipped[0],1.9)],hz)

    def test_cycle_comparison_distinguishes_clock_drift_from_service_errors(self):
        # The same nonlinear physical clock affects both observed waveforms.
        # Known cycles provide the reference; no local fit can hide a bad stamp.
        hz=1000
        physical=lambda t: 2+t+30e-6*t*t
        rises=[physical(i/hz) for i in range(4000)]
        ids=list(range(100,3900,10))
        edges=[rises[i] for i in ids]
        stamps=[i*1e6/hz-7 for i in ids]
        baseline=service_cycles(edges,stamps,rises,hz)
        self.assertAlmostEqual(baseline['offset_us'],7,places=7)
        self.assertLess(baseline['max_residual_us'],1e-8)
        bad=stamps[:];bad[len(bad)//2]+=4
        jitter=service_cycles(edges,bad,rises,hz)
        self.assertGreater(jitter['max_residual_us'],3.9)
        self.assertAlmostEqual(jitter['max_interval_error_us'],4,places=7)
        drifting=[s+8e-6*(s-stamps[0]) for s in stamps]
        self.assertGreater(service_cycles(edges,drifting,rises,hz)['max_residual_us'],15)
        delayed=edges[:];delayed[len(delayed)//2]+=6e-6
        self.assertGreater(service_cycles(delayed,stamps,rises,hz)['max_residual_us'],5.9)

    def test_cycle_comparison_requires_complete_ordered_pairs_and_coverage(self):
        rises=[i*.001 for i in range(20)]
        for edges,stamps in [([.002,.004],[2000]),([.002,.002],[2000,4000]),
                             ([.002,.004],[2000,float('nan')]),
                             ([.002,.004],[4000,2000])]:
            with self.assertRaises(ValueError):service_cycles(edges,stamps,rises,1000)
        for edges in ([.0005,.004],[.002,.02]):
            with self.assertRaisesRegex(ValueError,'coverage'):
                service_cycles(edges,[2000,4000],rises,1000)
        self.assertEqual(clock_coordinates([.00225,.00475],rises,1000),[2250.,4750.])

    def test_simultaneous_audio_keeps_count_width_and_cadence_checks(self):
        raw,channels,_=fixture(voices=0,kib=0,finish=True)
        _,run,rows,_=j.parse(raw)
        physical=lambda t: 2+t+30e-6*t*t
        clock=[physical(i/1000) for i in range(4000)]
        service=[physical(t) for t in channels['service']['edges_s'][::2]]
        audio=[physical(t) for t in channels['audio']['edges_s']]
        def check(edges, initial=False):
            return audio_cycles(run,rows,service,initial,edges,clock,1000)
        self.assertEqual(check(audio)['callbacks'],1377)
        with self.assertRaisesRegex(ValueError,'count'):check(audio[:-2])
        with self.assertRaisesRegex(ValueError,'incomplete'):check(audio,True)
        wrong_width=audio[:];wrong_width[101]+=10e-6
        with self.assertRaisesRegex(ValueError,'work'):check(wrong_width)
        delayed=audio[:];delayed[100:102]=[t+10e-6 for t in delayed[100:102]]
        with self.assertRaisesRegex(ValueError,'cadence'):check(delayed)

if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
