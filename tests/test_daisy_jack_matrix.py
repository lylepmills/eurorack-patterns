# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Synthetic matrix and independent apparatus evidence; no hardware access."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'examples/daisy'), str(ROOT/'tools')]
import jack_matrix
import review_daisy_jack_matrix as reviewer
from test_daisy_jack_fault_capture import trace, scope
import jack_capture
import export_daisy_jack

BUILD = 'a'*24
TIMES = [3000000, 6500000]


def generator(times=TIMES):
    info = dict(kind='daisy-pulse-generator', protocol=1, board='seed3', build_id=BUILD,
                released=True, armed=False, max_edges=64, max_us=30000000,
                max_late_us=25, timer_hz=240000000)
    lines = ['GENINFO,'+json.dumps(info), f'GENARMED,1,2,{times[-1]}', 'GENSTART,1,2']
    for i,t in enumerate(times): lines.append(f'GENEDGE,{i},{t},{t},{t+1},{1-i}')
    lines.append(f'GENEND,1,2,0,{times[-1]+2}')
    return ('\n'.join(lines)+'\n').encode()


class Matrix(unittest.TestCase):
    def test_first_failure_stops_campaign_and_retains_successes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); manifest=root/'manifest.json'
            manifest.write_text(json.dumps(dict(kind='eurorack-patterns-daisy-jack-bench',protocol=3)))
            args=SimpleNamespace(port='fixture',generator_port='generator',manifest=manifest,
                generator_manifest=root/'generator.json',out=root/'out',case='all',server_port=10439)
            automation=SimpleNamespace(Manager=SimpleNamespace(launch=MagicMock()))
            with patch.dict(sys.modules, {'saleae':SimpleNamespace(automation=automation)}), \
                 patch.object(jack_matrix.pulse_generator,'load_manifest',return_value={}), \
                 patch.object(jack_matrix,'record_case',side_effect=[{'name':'baseline-before','status':'pass'},ValueError('waveform failure')]) as record:
                with self.assertRaisesRegex(ValueError,'waveform failure'): jack_matrix.run(args)
            state=json.loads((args.out/'matrix.json').read_text())
            self.assertEqual(record.call_count,2)
            self.assertEqual(len(state['completed']),1)
            self.assertEqual(state['status'],'stopped on failure; evidence retained')

    def test_finite_matrix_and_bounds(self):
        cases = jack_matrix.cases()
        self.assertEqual(len(cases), 110)
        self.assertEqual(len({c['name'] for c in cases}), 110)
        self.assertEqual([cases[0]['fault'], cases[-1]['fault']], [0,0])
        for c in cases:
            jack_capture.validate_plan(10000,c['fault'],c['policy'],c['trigger'],c['fault_delay_slots'],c['fault_us'])
        self.assertEqual({(c['trigger'],c['fault'],c['fault_us'],c['fault_delay_slots']) for c in cases[1:-1]},
            {(t,f,u,d) for t in range(1,7) for f in (1,2) for u in (500,25000,100000) for d in (0,1,64)})

    def test_physical_review_all_phases_and_duration_extremes(self):
        for fault,trigger in [(0,0)]+[(f,t) for f in (1,2) for t in range(1,7)]:
            for duration in ((25000,) if not fault else (500,100000)):
                with self.subTest(fault=fault,trigger=trigger,duration=duration):
                    raw=trace(fault,trigger,duration=duration)
                    channels,analog=scope(jack_capture.parse(raw))
                    result=reviewer.review(raw,channels,analog,generator(),BUILD,TIMES)
                    self.assertEqual(result['status'],'pass')
                    self.assertLess(result['physical_clamp_duration_bounds_s'][0],3.5)
                    self.assertGreater(result['physical_clamp_duration_bounds_s'][1],3.5)

    def test_wrong_source_duration_or_identity_is_rejected(self):
        raw=trace(1,2); channels,analog=scope(jack_capture.parse(raw))
        wrong=[3000000,6600000]
        with self.assertRaisesRegex(ValueError,'duration disagreement'):
            reviewer.review(raw,channels,analog,generator(wrong),BUILD,wrong)
        with self.assertRaisesRegex(ValueError,'identity'):
            reviewer.review(raw,channels,analog,generator(),'b'*24,TIMES)

    def test_public_export_omits_local_notes_and_rejects_unknown_wire_fields(self):
        raw=trace(1,2); channels,analog=scope(jack_capture.parse(raw))
        info=jack_capture.parse(raw)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'case'; (source/'fixture').mkdir(parents=True); (source/'scope').mkdir()
            (source/'fixture/raw.txt').write_bytes(raw)
            build=dict(build_id=info['build_id'],source_commit='b'*40,sdk_revision='c'*40,
                artifacts_sha256={'patterns_jack.bin':'d'*64})
            meta=dict(status='complete',build=build,declared_fixture=json.dumps(dict(
                case='automated-electrical-clamp',private_note='internal-path-marker')))
            (source/'fixture/metadata.json').write_text(json.dumps(meta))
            (source/'channels.json').write_text(json.dumps(channels))
            (source/'analog-apertures.json').write_text(json.dumps(analog))
            gen_build=dict(build_id=BUILD,source_commit='e'*40,sdk_revision='c'*40,
                artifacts_sha256={'patterns_pulse_generator.bin':'f'*64},private_note='internal-path-marker')
            (root/'matrix.json').write_text(json.dumps(dict(generator_build=gen_build,times_us=TIMES)))
            (root/'case-generator.txt').write_bytes(generator())
            # This is a synthetic exporter test; opaque native-file hashes do
            # not turn generated derived waveforms into measured evidence.
            for name in ('settings.json','capture.sal','analog_0.bin',
                         'digital_1_0.bin','digital_1_1.bin','digital_1_2.bin','digital_1_3.bin'):
                (source/'scope'/name).write_bytes(b'synthetic placeholder')
            result=export_daisy_jack.export(source,root/'public/sample','pass','automated-electrical-clamp')
            self.assertNotIn('internal-path-marker',json.dumps(result))
            self.assertEqual(result['generator_build']['build_id'],BUILD)
            lines=generator().splitlines(keepends=True)
            identity=json.loads(lines[0][8:]); identity['private_note']='internal-path-marker'
            lines[0]=('GENINFO,'+json.dumps(identity)+'\n').encode()
            (root/'case-generator.txt').write_bytes(b''.join(lines))
            with self.assertRaises(AssertionError):
                export_daisy_jack.export(source,root/'public/rejected','pass','automated-electrical-clamp')
            self.assertFalse((root/'public/rejected.json').exists())

    def test_ambiguous_edges_do_not_become_exact_timestamps(self):
        raw=trace(1,2); channels,analog=scope(jack_capture.parse(raw))
        _,_,rows,_=jack_capture.parse(raw)
        # Hide the insertion edge for 20 ms: the waveform still cannot be
        # accepted as a tightly bounded stimulus, even if its middle is fine.
        for i,r in enumerate(rows):
            if 2990000 < r['sample_us'] < 3010000:
                analog['minimum_volts'][i]=0.; analog['maximum_volts'][i]=3.3
        with self.assertRaisesRegex(ValueError,'unbounded electrical transition'):
            reviewer.review(raw,channels,analog,generator(),BUILD,TIMES)


if __name__=='__main__': unittest.main(argv=[sys.argv[0]])
