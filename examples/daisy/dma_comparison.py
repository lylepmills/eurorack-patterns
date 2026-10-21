# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Bounded, order-balanced plans for the protocol-7 clock investigation."""
from capture import require


def cases():
    base = dict(audio_block=16, audio_permille=0, audio_off_ms=8000,
                dsp_voices=16, dma_kib=16, dma_region=0, dma_period_us=1000)
    idle = dict(base, audio_block=0, audio_off_ms=0, dsp_voices=0, dma_kib=0)
    dsp = dict(base, dma_kib=0)
    order = [(0,1000),(1,1000),(1,2000),(0,2000),
             (0,2000),(1,2000),(1,1000),(0,1000)]
    result = [dict(idle,name='idle-before'), dict(dsp,name='dsp-before')]
    for i,(region,period) in enumerate(order):
        result.append(dict(base, name=f'pair-{i//2+1}-r{region}-p{period}',
                           dma_region=region, dma_period_us=period))
    return result + [dict(dsp,name='dsp-after'), dict(idle,name='idle-after')]


def compare(left, right, regions=(0, 1)):
    """Compare validated runs; matched count is not proof of identical bus traffic."""
    require({left['dma_memory']['region'],right['dma_memory']['region']} == set(regions),
            'comparison must contain both memory regions')
    for key in ('duration_ms','acquisition_limit_us','finish_reason'):
        require(left[key] == right[key], 'comparison duration differs')
    for key in ('block','permille','off_ms'):
        require(left['audio'][key] == right['audio'][key], 'comparison audio plan differs')
    require(left['dsp']['voices'] == right['dsp']['voices'] and
            left['dma']['kib'] == right['dma']['kib'] and
            left['dma']['period_us'] == right['dma']['period_us'], 'comparison workload differs')
    rows = []
    for run in (left,right):
        dma = run['dma']
        interval = min(run['audio']['end_us'],run['acquisition_limit_us'])
        require(dma['kib'] and interval > 0, 'comparison needs active DMA')
        rows.append(dict(region=run['dma_memory']['region'], verified=dma['verified'],
            skipped=dma['skipped'], payload_bytes=dma['bytes'], loaded_us=interval,
            transfers_per_second=dma['verified']*1e6/interval,
            payload_bytes_per_second=dma['bytes']*1e6/interval,
            dsp_frames=run['dsp']['frames'], audio_callbacks=run['audio']['callbacks']))
    matched = (not any(r['skipped'] for r in rows) and
               abs(rows[0]['verified']-rows[1]['verified']) <= 1 and
               abs(rows[0]['audio_callbacks']-rows[1]['audio_callbacks']) <= 1 and
               abs(rows[0]['loaded_us']-rows[1]['loaded_us']) <= 1000)
    return dict(runs=rows, completion_counts_matched=matched,
        interpretation='Counts agree within one transfer/callback, no skipped launches; compare clock results with cache/verification costs included.'
        if matched else 'Achieved work differs; memory-region effects are confounded with throughput or callback coverage.')
