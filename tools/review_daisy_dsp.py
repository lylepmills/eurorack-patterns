#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Verify deterministic DSP work and completed background DMA, not audio quality."""
import functools
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'examples/daisy'))
from capture import require


@functools.lru_cache(maxsize=64)
def signature(reference, voices, frames):
    result = subprocess.run([str(reference),'--signature',str(voices),str(frames)],
                            capture_output=True, check=True, text=True, timeout=120)
    value = json.loads(result.stdout)
    require(set(value) == {'frames','hash','peak','nonzero','macs'} and
            all(type(v) is int and 0 <= v <= 0xffffffff for v in value.values()),
            'invalid DSP reference result')
    return value


def verify(run, reference=None):
    if 'dsp' not in run: return None
    dsp, dma = run['dsp'], run['dma']
    if dsp['voices']:
        require(reference is not None, 'DSP reference executable required')
        expected = signature(str(Path(reference).resolve()), dsp['voices'], dsp['frames'])
        require({k:dsp[k] for k in expected} == expected, 'DSP signature differs from deterministic replay')
    if dma['kib']:
        end = min(run['audio']['end_us'], run['acquisition_limit_us'])
        # This is an achieved minimum, not a claim of exact 1kHz throughput.
        # Record the actual count, skipped launch opportunities and gaps.
        require(dma['verified'] >= end//(2*dma['period_us']) and dma['first_us'] <= 10000 and
                end-10000 <= dma['last_us'] <= end+5000 and dma['max_gap_us'] <= 10000,
                'background DMA did not cover the loaded interval')
    limitation='The DSP reference reuses the tested integer kernel. DMA timing/counters are device-reported; D4 independently checks audio callbacks, not the DMA2 bus. Silent outputs do not qualify codec audio quality.'
    if 'dma_memory' in run:
        # Protocol 7 also runs in M mode, where D4 carries the clock and D5
        # carries audio. Preserve legacy replay text while avoiding a false
        # channel attribution in the memory comparison.
        limitation=limitation.replace('D4 independently', 'the separate audio marker independently')
    return dict(dsp='full deterministic sample signature matched' if dsp['voices'] else 'disabled',
                dma='every completed destination word verified' if dma['kib'] else 'disabled',
                dma_payload_bytes=dma['bytes'], dma_verified_transfers=dma['verified'],
                dma_skipped_launches=dma['skipped'], dma_max_gap_us=dma['max_gap_us'],
                limitation=limitation)
