# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Full motion evidence, plus independent physical-evidence mutations."""
import copy,gzip,hashlib,json,math,subprocess,sys,unittest
from bisect import bisect_right
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools'))
import review_daisy_jacks as physical

class Motion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=subprocess.check_output([sys.argv[1],'--motion-trace'])
        cls.parsed=physical.jack_capture.parse(cls.raw)
        _,run,rows,_=cls.parsed
        cls.channels={name:dict(initial_high=False,edges_s=[],begin_s=0.,end_s=32.) for name in ('sense','service','presence','probe')}
        cls.analog=dict(sample_rate_hz=250000,begin_s=0.,end_s=32.,samples=8000000,
            first_indices=[],last_indices=[],minimum_volts=[],maximum_volts=[],
            representation='Native extrema over each service aperture, including boundary samples')
        previous={k:False for k in cls.channels}
        for r in rows:
            for name,value,t in [('probe',bool(r['probe']),r['drive_us']),('sense',r['raw']>=49151,r['drive_us']),('presence',bool(r['ready'] and r['patched']),r['adc_end_us'])]:
                if value!=previous[name]:cls.channels[name]['edges_s'].append(1+t/1e6)
                previous[name]=value
            a,b=1+r['sample_us']/1e6,1+r['end_us']/1e6
            cls.channels['service']['edges_s'] += [a,b]
            cls.analog['first_indices'].append(math.floor(a*250000));cls.analog['last_indices'].append(math.ceil(b*250000))
            v=3.3 if r['raw']>=49151 else 0.
            cls.analog['minimum_volts'].append(v);cls.analog['maximum_volts'].append(v)
        for name in ('probe','sense'):
            if previous[name]:cls.channels[name]['edges_s'].append(1+run['elapsed_us']/1e6)

    def review(self,channels=None,analog=None):
        # Wire integrity/replay is already checked above; isolate mutations of
        # independent physical evidence rather than repeatedly reparse it.
        with patch.object(physical.jack_capture,'parse',return_value=self.parsed):
            return physical.review_motion(self.raw,channels or self.channels,analog or self.analog)

    def test_three_cycles(self):
        r=self.review();self.assertEqual(r['cycles'],3);self.assertEqual(r['presence_edges'],6)
        self.assertEqual(r['ambiguous_analog_apertures'],0)

    def test_missing_or_extra_output_edges(self):
        for name in ('service','probe','presence'):
            c=copy.deepcopy(self.channels);c[name]['edges_s'].pop()
            with self.subTest(name=name),self.assertRaises(ValueError):self.review(channels=c)

    def test_disconnected_or_mistimed_analog(self):
        a=copy.deepcopy(self.analog);a['minimum_volts']=[0.]*60000;a['maximum_volts']=[0.]*60000
        with self.assertRaisesRegex(ValueError,'analog/ADC'):self.review(analog=a)
        a=copy.deepcopy(self.analog);a['first_indices'][0]+=1
        with self.assertRaisesRegex(ValueError,'timing'):self.review(analog=a)

    def test_full_measured_recording(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-motion'
        meta=json.loads((folder/'ordinary-silent.json').read_text());payload={}
        for key in ('raw','channels','analog'):
            packed=(folder/f'ordinary-silent-{key}.txt.gz').read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
            data=gzip.decompress(packed);self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
            payload[key]=data if key=='raw' else json.loads(data)
        report=physical.review_motion(payload['raw'],payload['channels'],payload['analog'])
        self.assertEqual(report['samples'],600000);self.assertEqual(report['cycles'],3)
        self.assertEqual(report['state_changes'],meta['review']['state_changes'])
        self.assertEqual(report['invalid_observations'],1494)
        self.assertEqual(report['ambiguous_analog_apertures'],1495)

    def test_slow_insertion_with_complete_scope_tail(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-motion'
        meta=json.loads((folder/'slow-insertion-postroll.json').read_text());payload={}
        for key in ('raw','channels','analog'):
            packed=(folder/f'slow-insertion-postroll-{key}.txt.gz').read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
            data=gzip.decompress(packed);self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
            payload[key]=data if key=='raw' else json.loads(data)
        report=physical.review_motion(payload['raw'],payload['channels'],payload['analog'],cycles=2)
        # Physical timing is checked against tolerances by review_motion;
        # fitted floating-point diagnostics need not be bit-identical.
        self.assertEqual(report['status'],'pass')
        self.assertEqual(report['run'],meta['run'])
        self.assertEqual(report['state_changes'],meta['review']['state_changes'])
        self.assertEqual(report['samples'],146397);self.assertEqual(report['cycles'],2)
        self.assertEqual(report['run']['finish_reason'],'operator')
        self.assertEqual(report['run']['acquisition_limit_us'],73198500)
        self.assertEqual(report['run']['missed'],0);self.assertEqual(report['run']['adc_failures'],0)
        self.assertEqual(report['presence_edges'],4)
        self.assertEqual(len(payload['channels']['service']['edges_s']),292794)
        self.assertEqual(len(payload['analog']['minimum_volts']),146397)
        self.assertEqual(report['invalid_observations'],2052)
        self.assertEqual(report['ambiguous_analog_apertures'],2052)
        self.assertEqual([c['patched'] for c in report['state_changes']],[False,True,False,True,False])
        # The new complete trace does not qualify the earlier missing-tail run.
        prior=json.loads((folder/'slow-insertion-missing-tail.json').read_text())
        self.assertEqual(prior['status'],'missing-motion-tail');self.assertIsNone(prior['review'])

    def test_open_ended_cable_motion(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-motion'
        for name,count,end,ambiguous in [('ordinary-open',93942,46971000,0),
                                          ('ordinary-open-second-cable',78485,39242500,1)]:
            with self.subTest(cable=name):
                meta=json.loads((folder/f'{name}.json').read_text());payload={}
                for key in ('raw','channels','analog'):
                    packed=(folder/f'{name}-{key}.txt.gz').read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
                    data=gzip.decompress(packed);self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
                    payload[key]=data if key=='raw' else json.loads(data)
                self.assertEqual(meta['fixture']['case'],'manual-'+name)
                report=physical.review_motion(payload['raw'],payload['channels'],payload['analog'],cycles=2)
                self.assertEqual(report['status'],'pass');self.assertEqual(report['run'],meta['run'])
                self.assertEqual(report['state_changes'],meta['review']['state_changes'])
                self.assertEqual(report['samples'],count);self.assertEqual(report['cycles'],2)
                self.assertEqual(report['run']['finish_reason'],'operator')
                self.assertEqual(report['run']['acquisition_limit_us'],end)
                self.assertEqual(report['run']['missed'],0);self.assertEqual(report['run']['adc_failures'],0)
                self.assertEqual(report['presence_edges'],4)
                self.assertEqual(len(payload['channels']['service']['edges_s']),count*2)
                self.assertEqual(len(payload['analog']['minimum_volts']),count)
                self.assertEqual(report['invalid_observations'],0)
                self.assertEqual(report['ambiguous_analog_apertures'],ambiguous)
                self.assertEqual([c['patched'] for c in report['state_changes']],[False,True,False,True,False])

    def test_measured_faults_before_patched_qualification(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-transition'
        for name,fault,count in [('insert-adc-before',1,68627),('insert-service-before',2,72661)]:
            with self.subTest(capture=name):
                meta=json.loads((folder/f'{name}.json').read_text());payload={}
                for key in ('raw','channels','analog'):
                    packed=(folder/f'{name}-{key}.txt.gz').read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
                    data=gzip.decompress(packed);self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
                    payload[key]=data if key=='raw' else json.loads(data)
                parsed=physical.jack_capture.parse(payload['raw'])
                info,run,rows,changes=parsed
                with patch.object(physical.jack_capture,'parse',return_value=parsed):
                    report=physical.review_fault_motion(payload['raw'],payload['channels'],payload['analog'])
                self.assertEqual(info['protocol'],3);self.assertEqual(report['status'],'pass')
                self.assertEqual(report['run'],meta['run']);self.assertEqual(report['samples'],count)
                self.assertEqual(run['fault'],fault);self.assertEqual(run['trigger'],2)
                self.assertEqual(run['fault_delay_slots'],0)
                self.assertEqual(run['fault_end_us']-run['fault_begin_us'],25000)
                self.assertEqual(run['missed'],0 if fault==1 else 50)
                self.assertEqual(run['adc_failures'],0)
                self.assertEqual(rows[run['trigger_seq']]['bad_windows'],7)
                self.assertEqual(run['fault_due_us'],(rows[run['trigger_seq']]['slot']+1)*500)
                invalid=[r for r in rows if r['evidence']==2]
                self.assertEqual(len(invalid),50 if fault==1 else 1)
                self.assertTrue(all(r['ready'] and not r['patched'] and r['bad_windows']==0 for r in invalid))
                fresh=rows[invalid[-1]['seq']+1:changes[1]['seq']+1]
                self.assertEqual(len(fresh),512)
                self.assertTrue(all(r['evidence']!=2 for r in fresh))
                self.assertTrue(all(not r['patched'] for r in fresh[:-1]))
                self.assertTrue(fresh[-1]['patched'])
                self.assertEqual([c['patched'] for c in changes],[False,True,False])
                self.assertEqual(report['presence_edges'],2)
                self.assertEqual(len(payload['channels']['service']['edges_s']),count*2)
                self.assertEqual(report['ambiguous_analog_apertures'],0)
                self.assertEqual(report['digital_transition_apertures'],0)

    def test_measured_faults_before_unpatched_qualification(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-transition'
        for name,fault,count in [('remove-adc-before',1,101711),('remove-service-before',2,82871)]:
            with self.subTest(capture=name):
                meta=json.loads((folder/f'{name}.json').read_text());payload={}
                for key in ('raw','channels','analog'):
                    packed=(folder/f'{name}-{key}.txt.gz').read_bytes()
                    self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
                    data=gzip.decompress(packed);self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
                    payload[key]=data if key=='raw' else json.loads(data)
                parsed=physical.jack_capture.parse(payload['raw'])
                info,run,rows,changes=parsed
                with patch.object(physical.jack_capture,'parse',return_value=parsed):
                    report=physical.review_fault_motion(payload['raw'],payload['channels'],payload['analog'])
                self.assertEqual(info['protocol'],3);self.assertEqual(report['status'],'pass')
                self.assertEqual(report['run'],meta['run']);self.assertEqual(report['samples'],count)
                self.assertEqual(run['fault'],fault);self.assertEqual(run['trigger'],5)
                self.assertEqual(run['fault_delay_slots'],0)
                self.assertEqual(run['fault_end_us']-run['fault_begin_us'],25000)
                self.assertEqual(run['missed'],0 if fault==1 else 50)
                self.assertEqual(run['adc_failures'],0)
                self.assertTrue(rows[run['trigger_seq']]['patched'])
                self.assertEqual(run['fault_due_us'],(rows[run['trigger_seq']]['slot']+1)*500)
                invalid=[r for r in rows if r['evidence']==2]
                self.assertEqual(len(invalid),50 if fault==1 else 1)
                self.assertTrue(all(r['ready'] and r['patched'] and r['bad_windows']==0 for r in invalid))
                fresh=rows[invalid[-1]['seq']+1:changes[2]['seq']+1]
                self.assertEqual(len(fresh),64)
                self.assertTrue(all(r['evidence']==0 for r in fresh))
                self.assertTrue(all(r['patched'] for r in fresh[:-1]))
                self.assertFalse(fresh[-1]['patched'])
                self.assertEqual([c['patched'] for c in changes],[False,True,False])
                self.assertEqual(report['presence_edges'],2)
                self.assertEqual(len(payload['channels']['service']['edges_s']),count*2)
                self.assertEqual(report['ambiguous_analog_apertures'],0)
                self.assertEqual(report['digital_transition_apertures'],1 if fault==1 else 0)

    def test_operator_finished_motion_with_late_analog_disagreement(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-motion'
        meta=json.loads((folder/'slow-partial-silent.json').read_text());payload={}
        for key in ('raw','channels','analog'):
            packed=(folder/f'slow-partial-silent-{key}.txt.gz').read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
            data=gzip.decompress(packed);self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
            payload[key]=data if key=='raw' else json.loads(data)
        self.assertEqual(meta['status'],'motion-analog-disagreement')
        self.assertIsNone(meta['review'])
        parsed=physical.jack_capture.parse(payload['raw'])
        _,run,rows,changes=parsed
        self.assertEqual(run['count'],233089)
        self.assertEqual(run['missed'],0);self.assertEqual(run['adc_failures'],0)
        self.assertEqual(run['finish_reason'],'operator')
        self.assertEqual(run['acquisition_limit_us'],116544500)
        self.assertEqual([c['patched'] for c in changes],[False,True,False,True,False])
        self.assertEqual(sum(r['evidence']==2 for r in rows),10150)
        # Complete digital timing and replay survive the analog disagreement;
        # neither is sufficient to relabel the capture as a physical pass.
        with patch.object(physical.jack_capture,'parse',return_value=parsed):
            timing=physical.review_timing(payload['raw'],payload['channels'])
            with self.assertRaisesRegex(ValueError,'stable low analog/ADC disagreement'):
                physical.review_motion(payload['raw'],payload['channels'],payload['analog'],cycles=2)
        analog=payload['analog'];sense=payload['channels']['sense']
        bad=[i for i,r in enumerate(rows) if
             (analog['maximum_volts'][i]<=.85 and r['raw']>16384) or
             (analog['minimum_volts'][i]>=2.4 and r['raw']<49151)]
        self.assertEqual(len(bad),41328);self.assertEqual(bad[0],142187)
        self.assertEqual(rows[bad[0]]['sample_us'],71093650)
        for r,t,u in zip(rows,timing['rises'],timing['falls']):
            j,k=bisect_right(sense['edges_s'],t),bisect_right(sense['edges_s'],u)
            if j==k:
                high=sense['initial_high'] ^ bool(j%2)
                self.assertFalse((high and r['raw']<=16384) or (not high and r['raw']>=49151))

    def test_missing_scope_tail_cannot_pass_complete_firmware_replay(self):
        folder=ROOT/'bench/daisy/measured/daisy/2026-10-19-jack-motion'
        meta=json.loads((folder/'slow-insertion-missing-tail.json').read_text());payload={}
        for key in ('raw','channels','analog'):
            packed=(folder/f'slow-insertion-missing-tail-{key}.txt.gz').read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(),meta[key+'_compressed_sha256'])
            data=gzip.decompress(packed);self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key+'_sha256'])
            payload[key]=data if key=='raw' else json.loads(data)
        self.assertEqual(meta['status'],'missing-motion-tail');self.assertIsNone(meta['review'])
        _,run,rows,changes=physical.jack_capture.parse(payload['raw'])
        self.assertEqual(run['count'],119282);self.assertEqual(run['missed'],0)
        self.assertEqual(run['adc_failures'],0);self.assertEqual(run['finish_reason'],'operator')
        self.assertEqual(run['acquisition_limit_us'],59641000)
        self.assertEqual(rows[-1]['seq'],119281)
        self.assertEqual([c['patched'] for c in changes],[False,True,False,True,False])
        self.assertEqual(len(payload['channels']['service']['edges_s']),238506)
        self.assertEqual(len(payload['analog']['minimum_volts']),119253)
        self.assertEqual(meta['rejection_detail']['missing_tail_samples'],29)
        with self.assertRaisesRegex(ValueError,'Service count mismatch'):
            physical.review_motion(payload['raw'],payload['channels'],payload['analog'],cycles=2)

if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
