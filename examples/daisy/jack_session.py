#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Pair token-finished Daisy acquisition with a manually stopped Saleae MSO.

Requires the official logic2-automation MSO preview (headless server). Start
with explicit device identities; this tool never flashes or moves controls.
Call `jack_capture.py finish <session>/fixture` from another process when done.
"""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import jack_capture


class RetainedCapture:
    """Stop at most once, including exception cleanup; retain native evidence."""
    def __init__(self, capture, folder):
        self.capture, self.folder = capture, folder
        self.stopped = self.saved = self.exported = False

    def stop(self):
        if not self.stopped:
            self.stopped = True
            self.capture.stop()

    def save_capture(self, path):
        self.capture.save_capture(path); self.saved = True

    def export_raw_data_binary(self, path):
        self.capture.export_raw_data_binary(path); self.exported = True

    def retain(self):
        self.stop()
        if not self.saved: self.save_capture(str(self.folder/'capture.sal'))
        if not self.exported: self.export_raw_data_binary(str(self.folder))


def wait_device(manager, scope_id, device_type, timeout=20):
    """Discovery can lag server startup; never substitute another instrument."""
    deadline = time.monotonic() + timeout
    while True:
        matches = [d for d in manager.get_devices() if d.device_id == scope_id]
        if matches:
            if len(matches) != 1 or matches[0].device_type != device_type or matches[0].is_simulation:
                raise ValueError('Requested physical MSO identity differs')
            return matches[0]
        if time.monotonic() >= deadline: raise TimeoutError('Requested physical MSO not found')
        time.sleep(.1)


def collect(capture, child, out, maximum, finish_after=None, on_started=None):
    """Keep scope coverage through acquisition, then save while USB downloads."""
    started = out / 'fixture/started.json'
    complete = out / 'fixture/acquisition-complete.json'
    deadline = time.monotonic() + 15
    while not started.exists():
        if child.poll() is not None: raise RuntimeError('Fixture exited before acknowledgement')
        if time.monotonic() >= deadline: raise TimeoutError('No fixture acknowledgement')
        time.sleep(.05)
    ack = json.loads(started.read_text())
    began = time.monotonic()
    session_ready = dict(
        status='recording', token=ack['token'], maximum_seconds=maximum,
        acknowledged_utc=datetime.now(timezone.utc).isoformat(),
        finish_command='jack_capture.py finish <session>/fixture')
    jack_capture.publish_json(out / 'recording-ready.json', session_ready)
    print('Recording ready. Finish the fixture session when the actions are complete.', flush=True)
    if on_started is not None:
        on_started()
    sent = False
    while not complete.exists():
        if child.poll() is not None: raise RuntimeError('Fixture exited without acquisition completion')
        elapsed = time.monotonic() - began
        if elapsed > maximum + 15: raise TimeoutError('Acquisition exceeded maximum')
        if finish_after is not None and elapsed >= finish_after and not sent:
            jack_capture.request_finish(out / 'fixture'); sent = True
        time.sleep(.05)
    ack_end = json.loads(complete.read_text())
    if ack_end.get('token') != ack['token']: raise ValueError('Acquisition completion token differs')
    # This marker is provisional. Overall success still requires complete USB
    # checksums/replay AND successful independent native scope export.
    # The scope streams independently of the fixture's USB acknowledgement.
    # Retain a short post-roll so an immediate stop cannot cut into that tail.
    # This margin is not a substitute for checking complete physical coverage.
    postroll_started = time.monotonic()
    time.sleep(.5)
    postroll_seconds = time.monotonic() - postroll_started
    stopping = time.monotonic()
    capture.stop()
    stop_seconds = time.monotonic() - stopping
    capture.save_capture(str(out / 'scope/capture.sal'))
    capture.export_raw_data_binary(str(out / 'scope'))
    result = child.wait(timeout=330)
    if result != 0: raise RuntimeError('Fixture download/replay failed; evidence retained')
    summary = json.loads((out / 'fixture/summary.json').read_text())
    if summary['run']['token'] != ack['token']: raise ValueError('Summary token differs')
    report = dict(status='collected', physical_review='pending',
                  scope_postroll_seconds=postroll_seconds,
                  scope_stop_seconds=stop_seconds,
                  firmware_finish=summary['run']['finish_reason'],
                  acquisition_us=summary['run']['acquisition_limit_us'])
    jack_capture.publish_json(out / 'collection-complete.json', report)
    return report


def run(args, manager=None, on_started=None):
    manifest = json.loads(args.manifest.read_text())
    if manifest.get('kind') != 'eurorack-patterns-daisy-jack-bench' or manifest.get('protocol') not in (2, 3, 4, 5):
        raise ValueError('Manual session requires jack firmware protocol 2–5')
    jack_capture.validate_plan(args.max_seconds * 1000, args.fault, args.policy,
                              args.trigger, args.fault_delay_slots, args.fault_us)
    if manifest['protocol'] < 3 and (args.trigger, args.fault_delay_slots, args.fault_us) != (0, 0, 25000):
        raise ValueError('Configurable fault timing requires protocol 3')
    jack_capture.validate_audio(args.max_seconds * 1000, *jack_capture.audio_arguments(args))
    if args.out.exists(): raise ValueError('Output must be new')
    from saleae import automation as a
    args.out.mkdir(parents=True); (args.out/'scope').mkdir()
    child = None
    with (a.Manager.launch(headless=True, port=args.server_port)
          if manager is None else nullcontext(manager)) as manager:
        manager.set_reporting(analytics=False, crashes=False)
        wait_device(manager, args.scope_id, a.DeviceType.LOGIC_MSO)
        layout = jack_capture.digital_layout(manifest['protocol'])
        config = a.MsoDeviceConfiguration(
            scope_channels=[a.MsoScopeChannelConfiguration(index=0,
                analog=a.MsoScopeAnalogChannelConfiguration(center_voltage=1.65,
                    voltage_range=5.0, probe_attenuation=10.0, coupling=a.Coupling.DC))],
            analog_sample_rate=250000,
            digital_probes=[a.MsoDigitalProbeConfiguration(port_index=port, threshold_voltage=1.65,
                channels=[a.MsoDigitalProbeChannelConfiguration(index=i,
                    minimum_pulse_width_seconds=0) for _,p,i in layout if p == port])
                for port in sorted({p for _,p,_ in layout})])
        (args.out/'scope/settings.json').write_text(json.dumps(dict(
            analog_channel=0, analog_rate_hz=250000, probe_attenuation=10, coupling='DC',
            digital_layout=[dict(name=n,port_index=p,channel_index=i) for n,p,i in layout],
            threshold_volts=1.65, minimum_pulse_width_seconds=0,
            mode='manual; no trim', physical_review='pending'), indent=2)+'\n')
        with manager.start_capture(device_id=args.scope_id, device_configuration=config,
                capture_configuration=a.CaptureConfiguration(capture_mode=a.ManualCaptureMode())) as capture:
            retained = RetainedCapture(capture, args.out/'scope')
            # Independent pre-command coverage, not a cue to the operator.
            time.sleep(.5)
            command = [sys.executable, str(Path(__file__).with_name('jack_capture.py')),
                'capture', '--port', args.port, '--manifest', str(args.manifest),
                '--out', str(args.out/'fixture'), '--seconds', str(args.max_seconds),
                '--notes', args.notes, '--fault', str(args.fault), '--policy', str(args.policy),
                '--trigger', str(args.trigger), '--fault-delay-slots', str(args.fault_delay_slots),
                '--fault-us', str(args.fault_us)]
            command += [item for k,v in zip(('audio-block','audio-permille','audio-off-ms'),
                jack_capture.audio_arguments(args)) for item in ('--'+k,str(v))]
            with (args.out/'console.txt').open('w') as log:
                child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                try:
                    return collect(retained, child, args.out, args.max_seconds,
                                   args.finish_after, on_started)
                finally:
                    try:
                        retained.retain()
                    except Exception as error:
                        (args.out/'scope/retention-error.txt').write_text(str(error)+'\n')
                    if child.poll() is None:
                        # Leave no serial owner behind after a scope failure.
                        # Preserve raw evidence, but never call this a pass.
                        try:
                            jack_capture.request_finish(args.out/'fixture')
                        except (OSError, ValueError, KeyError):
                            pass
                        try:
                            child.wait(timeout=args.max_seconds+330)
                        except subprocess.TimeoutExpired:
                            child.terminate(); child.wait(timeout=5)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', required=True); p.add_argument('--scope-id', required=True)
    p.add_argument('--manifest', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--max-seconds', type=int, default=300); p.add_argument('--notes', required=True)
    jack_capture.add_fault_arguments(p)
    jack_capture.add_audio_arguments(p)
    p.add_argument('--server-port', type=int, default=10439)
    p.add_argument('--finish-after', type=float, help='Unattended workflow check: request finish after this many seconds')
    args=p.parse_args()
    if not 1<=args.max_seconds<=300: p.error('maximum must be 1–300 seconds')
    if args.finish_after is not None and not 0<args.finish_after<args.max_seconds:
        p.error('finish-after must be positive and below maximum')
    print(json.dumps(run(args), indent=2))

if __name__=='__main__': main()
