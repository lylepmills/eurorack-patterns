# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Known short cycles, receiver glitches, interpolation and malformed records."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
import inspect_daisy_clock_waveform as w
import clock_waveform as plan

class Waveform(unittest.TestCase):
    def test_crossings_are_interpolated_without_filtering(self):
        v=np.array([0.,1.,3.,3.,1.,0.,3.,0.])
        np.testing.assert_allclose(w.crossings(v,1e9,0,2),np.array([1.5,5+2/3])*1e-9)
        np.testing.assert_allclose(w.crossings(v,1e9,0,2,False),np.array([3.5,6+1/3])*1e-9)

    def test_short_cycle_and_extra_receiver_edge_stay_visible(self):
        ordinary=937.5e-9
        a=np.array([0,ordinary,2*ordinary,3*ordinary-62.5e-9,4*ordinary-62.5e-9])
        p=w.periods(a)
        self.assertEqual((p['short_periods'],p['long_periods']),(1,0))
        self.assertEqual(sum(p['histogram_ns'].values()),len(a)-1)
        b=np.sort(np.r_[a+8e-9,a[2]+20e-9])
        match=w.match_edges(a,b)
        self.assertEqual((match['matched'],match['unmatched_left'],match['unmatched_right']),(5,0,1))
        self.assertAlmostEqual(match['median_right_minus_left_ns'],8)
        match=w.match_edges(a,b[2:])
        self.assertEqual(match['unmatched_left'],2)

    def test_native_format_rejects_downsampling_truncation_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'analog.bin'
            def write(samples=(0.,3.3,0.),downsample=1,count=3):
                p.write_bytes(struct.pack('<8siiQdddqQ',b'<SALEAE>',1,1,1,-1e-9,0,1e9,downsample,count)+struct.pack('<'+'f'*len(samples),*samples))
            write();v,meta=w.analog(p)
            self.assertEqual(meta['samples'],3)
            self.assertAlmostEqual(meta['end_s'],1e-9)
            del v  # Release the mapped file before rewriting it on Windows.
            for kwargs in (dict(downsample=2),dict(count=4),dict(samples=(0.,float('nan'),0.))):
                write(**kwargs)
                with self.assertRaises(ValueError): w.analog(p)

    def test_rise_and_fall_time_and_ringing_ambiguity(self):
        v=np.array([0.,0.,1.,2.,3.,3.,2.,1.,0.,0.])
        times=w.transition_times(v,1e9,0,.3,2.7)
        for direction in ('rise','fall'):
            self.assertEqual(times[direction]['paired'],1)
            self.assertAlmostEqual(times[direction]['median_ns'],2.4)
        times=w.transition_times(np.array([0.,1.,0.,1.,2.,3.]),1e9,0,.3,2.7)
        self.assertEqual(times['rise']['unpaired_starts'],1)

    def test_finite_balanced_plan_preserves_work(self):
        for stage, count in (('receivers',6),('waveforms',6),('swapped-path',4)):
            cases=plan.cases(stage)
            self.assertEqual(len(cases),count)
            self.assertEqual(sum(c['dma_region']==3 for c in cases),count//2)
            self.assertEqual({tuple(c[k] for k in ('audio_block','audio_off_ms','dsp_voices','dma_kib','dma_period_us','seconds')) for c in cases}, {(16,8000,16,16,2000,10)})
        self.assertEqual([c['dma_region'] for c in plan.cases('waveforms')[:4]],[3,4,4,3])
        with self.assertRaises(ValueError):plan.cases('unbounded')

    def test_receiver_threshold_isolated_to_clock_probe_port(self):
        from types import SimpleNamespace as S
        api=S(Coupling=S(DC='DC'),ScopeChannelType=S(ANALOG='analog'),MsoAnalogTriggerEdgeType=S(FALLING='falling'))
        for name in ('MsoDeviceConfiguration','MsoScopeChannelConfiguration','MsoScopeAnalogChannelConfiguration','MsoScopeDigitalChannelConfiguration','MsoDigitalProbeConfiguration','MsoDigitalProbeChannelConfiguration','CaptureConfiguration','MsoTriggerCaptureMode','MsoAnalogTriggerConfiguration','ScopeChannel'):
            setattr(api,name,S)
        cfg=plan.scope_configuration(api,sample_rate=1000000000,raw_threshold_mv=2300)
        self.assertEqual([p.threshold_voltage for p in cfg.digital_probes],[1.65,2.3])
        self.assertEqual([s.digital.threshold_high_voltage for s in cfg.scope_channels],[2.,2.])
        self.assertEqual([s.analog.voltage_range for s in cfg.scope_channels],[5.,10.])
        swapped=plan.scope_configuration(api,sample_rate=1000000000,clock_scope_index=0)
        self.assertEqual([s.analog.voltage_range for s in swapped.scope_channels],[10.,5.])
        original=plan.scope_configuration(api,clock_span_v=5.)
        self.assertEqual([s.analog.voltage_range for s in original.scope_channels],[5.,5.])
        self.assertTrue(all(c.minimum_pulse_width_seconds==0 for p in cfg.digital_probes for c in p.channels))
        trigger=plan.trigger_configuration(api,1).capture_mode
        self.assertEqual(trigger.trigger.channel.index,1)
        self.assertEqual(trigger.pre_trigger_seconds+trigger.post_trigger_seconds,.05)
        with self.assertRaises(ValueError):plan.scope_configuration(api,sample_rate=25000000)
        with self.assertRaises(ValueError):plan.scope_configuration(api,clock_scope_index=2)
        with self.assertRaises(ValueError):plan.scope_configuration(api,clock_span_v=float('nan'))

    def test_complete_inspection_and_receiver_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);rate=1e9
            x=np.arange(12000)/rate
            # 1 MHz synthetic clock with finite 5 ns transitions.
            knots=np.ravel(np.array([[i,i+5e-9,i+.5e-6,i+.505e-6] for i in np.arange(.1e-6,12e-6,1e-6)]))
            v=np.interp(x,knots,np.tile([0.,3.3,3.3,0.],12))
            ap=p/'analog.bin';ap.write_bytes(struct.pack('<8siiQdddqQ',b'<SALEAE>',1,1,1,0,0,rate,1,len(v))+v.astype('<f4').tobytes())
            rises=w.crossings(v,rate,0,1.65);falls=w.crossings(v,rate,0,1.65,False)
            edges=np.sort(np.r_[rises,falls])+3e-9
            dp=p/'digital.bin'
            def write(end):
                dp.write_bytes(struct.pack('<8siiQIdddQ',b'<SALEAE>',1,0,1,0,rate,0,end,len(edges))+edges.astype('<f8').tobytes())
            write(x[-1]);r=w.inspect(ap,dict(raw=dp),nominal_hz=1e6)
            self.assertEqual(r['thresholds']['1.65']['short_periods'],0)
            self.assertEqual(r['receivers']['raw']['matches']['1.65']['unmatched_left'],0)
            self.assertAlmostEqual(r['receivers']['raw']['matches']['1.65']['median_right_minus_left_ns'],3,places=4)
            write(x[-1]+1e-6)
            # Coverage rejection independent of edge count/clock interpretation.
            b=bytearray(dp.read_bytes());struct.pack_into('<d',b,36,10e-9);dp.write_bytes(b)
            with self.assertRaisesRegex(ValueError,'coverage'):w.inspect(ap,dict(raw=dp))

    def test_missing_clock_and_invalid_edges_rejected(self):
        for edges in ([0,1],[0,1,1],[0,float('nan'),2]):
            with self.assertRaises(ValueError): w.periods(edges)
        with self.assertRaises(ValueError): w.match_edges([0,0],[0,1])
        self.assertEqual(w.match_edges([], [1])['unmatched_right'],1)

if __name__=='__main__': unittest.main()
