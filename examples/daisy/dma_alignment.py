# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""One-image SDRAM alignment experiment, with fixed code/DSP/trace storage."""
from dma_comparison import compare as compare_regions

# Matching byte offsets in 64 KiB low/high arenas. Selector 2 preserves the
# previous high address; selector 0 separately preserves the original low pair.
PAIRS = ((3, 4), (5, 6), (7, 8), (9, 2))
ORDER = (3, 4, 6, 5, 7, 8, 2, 9)


def cases():
    base = dict(audio_block=16, audio_permille=0, audio_off_ms=8000,
                dsp_voices=16, dma_kib=16, dma_region=0, dma_period_us=2000)
    idle = dict(base, audio_block=0, audio_off_ms=0, dsp_voices=0,
                dma_kib=0, dma_period_us=1000)
    dsp = dict(base, dma_kib=0, dma_period_us=1000)
    result = [dict(idle, name='idle-before'), dict(dsp, name='dsp-before'),
              dict(base, name='legacy-low-before')]
    result += [dict(base, name=f'dma-only-r{r}', dsp_voices=0, dma_region=r) for r in ORDER]
    for sweep, order in enumerate((ORDER, ORDER[::-1]), 1):
        result += [dict(base, name=f'combined-s{sweep}-r{r}', dma_region=r) for r in order]
    return result + [dict(base, name='legacy-low-after'),
                     dict(dsp, name='dsp-after'), dict(idle, name='idle-after')]


def comparison_pairs():
    pairs = []
    for prefix in ('dma-only', 'combined-s1', 'combined-s2'):
        for low, high in PAIRS:
            pairs.append(dict(left=f'{prefix}-r{low}', right=f'{prefix}-r{high}',
                              variable='address range; same offset'))
    for sweep in (1, 2):
        for baseline, variants in ((3, (5, 7, 9)), (4, (6, 8, 2))):
            for variant in variants:
                pairs.append(dict(left=f'combined-s{sweep}-r{baseline}',
                                  right=f'combined-s{sweep}-r{variant}',
                                  variable='byte offset; same arena'))
    return pairs


def compare(left, right):
    return compare_regions(left, right,
        regions=(left['dma_memory']['region'], right['dma_memory']['region']))
