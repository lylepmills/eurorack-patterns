# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""One-image low/high SDRAM comparison, including achieved-throughput controls."""
from dma_comparison import compare as compare_regions


def cases():
    base = dict(audio_block=16, audio_permille=0, audio_off_ms=8000,
                dsp_voices=16, dma_kib=16, dma_region=0, dma_period_us=1000)
    idle = dict(base, audio_block=0, audio_off_ms=0, dsp_voices=0, dma_kib=0)
    dsp = dict(base, dma_kib=0)
    result = [dict(idle, name='idle-before'), dict(dsp, name='dsp-before')]
    result += [dict(base, name=f'dma-only-r{region}', dsp_voices=0, dma_region=region)
               for region in (0, 2)]
    # ABBA and BAAB: each address appears early and late; the slower requested
    # rate tests whether any difference remains at comparable achieved work.
    for period, regions in ((1000, (0, 2, 2, 0)), (2000, (2, 0, 0, 2))):
        for i, region in enumerate(regions):
            result.append(dict(base, name=f'combined-p{period}-{i+1}-r{region}',
                               dma_region=region, dma_period_us=period))
    return result + [dict(dsp, name='dsp-after'), dict(idle, name='idle-after')]


def compare(left, right):
    return compare_regions(left, right, regions=(0, 2))
