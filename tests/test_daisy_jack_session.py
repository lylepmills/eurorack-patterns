# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Workflow boundaries using simulated device ownership; no hardware access."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'examples/daisy'))
import jack_session as session

class Workflow(unittest.TestCase):
    def test_mso_probe_local_indices_and_export_mapping(self):
        legacy=session.jack_capture.digital_layout(3)
        self.assertEqual(legacy, [('sense',0,0),('service',0,1),('presence',0,2),('probe',0,3)])
        current=session.jack_capture.digital_layout(4)
        self.assertEqual(current,legacy+[('audio',1,0)])
        self.assertTrue(all(0 <= channel < 4 for _,port,channel in current))
        self.assertEqual([f'digital_{p+1}_{i}.bin' for _,p,i in current],
                         ['digital_1_0.bin','digital_1_1.bin','digital_1_2.bin','digital_1_3.bin','digital_2_0.bin'])

    def test_delayed_discovery_matches_only_requested_device(self):
        other=SimpleNamespace(device_id='other',device_type='MSO',is_simulation=False)
        wanted=SimpleNamespace(device_id='wanted',device_type='MSO',is_simulation=False)
        manager=Mock();manager.get_devices.side_effect=[[],[other],[other,wanted]]
        with patch.object(session.time,'sleep'):
            self.assertIs(session.wait_device(manager,'wanted','MSO'),wanted)
        manager.get_devices.side_effect=None;manager.get_devices.return_value=[other]
        with self.assertRaises(TimeoutError):session.wait_device(manager,'wanted','MSO',timeout=0)
        wanted.is_simulation=True;manager.get_devices.return_value=[wanted]
        with self.assertRaises(ValueError):session.wait_device(manager,'wanted','MSO')

    def fixture(self, out):
        (out/'fixture').mkdir(); (out/'scope').mkdir()
        (out/'fixture/started.json').write_text('{"token":42}')
        (out/'fixture/acquisition-complete.json').write_text('{"token":42}')
        (out/'fixture/summary.json').write_text(json.dumps(dict(run=dict(
            token=42, finish_reason='operator', acquisition_limit_us=1234500))))

    def test_finish_before_download_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out)
            events=[];capture=Mock();child=Mock()
            child.wait.side_effect=lambda **kwargs: events.append('download') or 0
            capture.stop.side_effect=lambda:events.append('stop')
            capture.save_capture.side_effect=lambda p:events.append('save')
            capture.export_raw_data_binary.side_effect=lambda p:events.append('export')
            with patch.object(session.time,'sleep',side_effect=lambda seconds:events.append(('postroll',seconds))):
                report=session.collect(capture,child,out,300)
            self.assertEqual(events,[('postroll',.5),'stop','save','export','download'])
            self.assertEqual(report['physical_review'],'pending')
            self.assertEqual(report['acquisition_us'],1234500)

    def test_partial_download_never_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out)
            child=Mock();child.wait.return_value=2;capture=Mock()
            with self.assertRaisesRegex(RuntimeError,'download/replay'):
                session.collect(capture,child,out,300)
            capture.save_capture.assert_called_once()
            self.assertFalse((out/'collection-complete.json').exists())

    def test_generator_starts_only_after_ack_and_failure_stays_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); self.fixture(out)
            def start():
                self.assertEqual(json.loads((out/'recording-ready.json').read_text())['token'], 42)
                raise RuntimeError('generator failed')
            with self.assertRaisesRegex(RuntimeError, 'generator failed'):
                session.collect(Mock(), Mock(), out, 10, on_started=start)
            self.assertFalse((out/'collection-complete.json').exists())

    def test_wrong_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fixture(out)
            (out/'fixture/acquisition-complete.json').write_text('{"token":43}')
            with self.assertRaisesRegex(ValueError,'token differs'):
                session.collect(Mock(),Mock(),out,300)
            self.assertFalse((out/'collection-complete.json').exists())

    def test_cleanup_does_not_stop_twice(self):
        capture=Mock();retained=session.RetainedCapture(capture,Path('scope'))
        retained.retain();retained.retain()
        capture.stop.assert_called_once();capture.save_capture.assert_called_once()
        capture.export_raw_data_binary.assert_called_once()

    def test_stop_error_is_retained_not_retried(self):
        capture=Mock();capture.stop.side_effect=RuntimeError('USB loss')
        retained=session.RetainedCapture(capture,Path('scope'))
        with self.assertRaisesRegex(RuntimeError,'USB loss'):retained.stop()
        retained.retain()
        capture.stop.assert_called_once();capture.save_capture.assert_called_once()

if __name__=='__main__':unittest.main()
