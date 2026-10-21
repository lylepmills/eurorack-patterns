#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Stationary load matrix followed by a continuous soak; no flashing or port discovery."""
import argparse
import contextlib
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import load_capture


def plan(soak_seconds=1800):
    return [dict(name=name, audio_permille=padding, block_size=block, usb_hz=usb,
                 seconds=seconds, mode=mode) for name, padding, block, usb, seconds, mode in [
        ('baseline', -1, 16, 0, 10, 'trace'),
        ('audio-dma', 0, 16, 0, 10, 'trace'),
        ('audio-25', 250, 16, 0, 10, 'trace'),
        ('audio-65', 650, 16, 0, 10, 'trace'),
        ('usb-only', -1, 16, 500, 10, 'trace'),
        ('combined-16', 650, 16, 500, 30, 'trace'),
        ('combined-48', 650, 48, 500, 30, 'trace'),
        ('continuous-soak', 650, 16, 500, soak_seconds, 'soak')]]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port')
    p.add_argument('--manifest', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--replay', type=Path)
    p.add_argument('--soak-seconds', type=int, default=1800)
    p.add_argument('--dry-run', action='store_true')
    a=p.parse_args()
    if not 1 <= a.soak_seconds <= 3600:p.error('soak seconds must be 1..3600')
    cases=plan(a.soak_seconds)
    if a.dry_run:
        print(json.dumps(cases,indent=2)); return 0
    if not all((a.port,a.manifest,a.out,a.replay)):p.error('port, manifest, out and replay are required')
    load_capture.require(not a.out.exists(),'campaign output must be new')
    a.out.mkdir(parents=True)
    journal=dict(status='incomplete',started_utc=datetime.now(timezone.utc).isoformat(),cases=cases,completed=[])
    (a.out/'campaign.json').write_text(json.dumps(journal,indent=2)+'\n')
    try:
        for case in cases:
            name=case['name']
            print(f"Starting {name}: {case['seconds']} seconds. Keep the button released and pot stationary.",flush=True)
            options=argparse.Namespace(**{k:v for k,v in case.items() if k!='name'},
                port=a.port,manifest=a.manifest,out=a.out/name,replay=a.replay,
                stationary=True,target=.25,download_timeout=180)
            with (a.out/(name+'.log')).open('w') as log,contextlib.redirect_stdout(log):
                result=load_capture.record(options)
            journal['completed'].append(dict(name=name,result=result))
            (a.out/'campaign.json').write_text(json.dumps(journal,indent=2)+'\n')
            if result:
                print(f'Stopped: {name} did not pass. Evidence retained in the output directory.',flush=True)
                return result
            print('PASS:',name,flush=True)
        journal['status']='complete'
        return 0
    finally:
        (a.out/'campaign.json').write_text(json.dumps(journal,indent=2)+'\n')


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,KeyError,TimeoutError) as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
