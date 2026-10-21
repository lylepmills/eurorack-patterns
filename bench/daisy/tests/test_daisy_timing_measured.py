#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Retained measured timing evidence; selected pulses never imply full replay."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'examples/daisy'))
import load_capture
DATA = ROOT/'bench/daisy/measured/daisy/2026-10-17-timing'


def verify(name, seconds, quality='pass', scope='pass'):
    meta=json.loads((DATA/(name+'.json')).read_text())
    compressed=(DATA/(name+'.txt.gz')).read_bytes(); raw=gzip.decompress(compressed)
    assert hashlib.sha256(compressed).hexdigest()==meta['compressed_sha256']
    assert hashlib.sha256(raw).hexdigest()==meta['raw_sha256']
    s,controls,buckets=load_capture.parse(raw,meta['firmware_build_id'])
    assert controls is None and len(buckets)==seconds
    assert s['counters']==meta['counters'] and s['configuration']==meta['configuration']
    load_capture.assess(s,True,dict(meta['host_writer'],error=None))
    assert s['checks']['status']==meta['quality_status']==quality
    assert s['checks']['failures']==meta['quality_failures']
    assert meta['scope_status']==scope
    assert meta['validation_status']==('pass' if quality==scope=='pass' else 'fail')
    if scope == 'pass':
        assert not meta['scope']['mismatched_buckets']
        assert meta['scope']['max_interval_error_us'] < 5
        assert meta['scope']['max_work_width_error_us'] < 3
    assert s['counters']['samples']==meta['scope']['samples']==1000*seconds
    assert not s['actions'] and meta['scope']['button_released_throughout']
    assert meta['scope']['action_edges']==0
    if s['configuration']['mode'] != 2:
        assert 'timing' not in meta
        return
    timing=meta['timing']; selected=timing['service_pulses']
    seqs=[r[0] for r in selected]
    assert seqs==sorted(set(seqs)) and len(selected)<s['counters']['samples']
    expected={w[side]['seq'] for b in buckets for w in b['timing']['witnesses']
              for side in ('previous','current')}
    assert set(seqs)==expected
    pulses={seq:(rise,fall) for seq,rise,fall in selected}
    assert all(0<=seq<seconds*1000 and 0<=rise<fall for seq,rise,fall in selected)
    hz=s['counters']['timer_hz']; tick_us=1e6/hz
    width_error=interval_error=0.
    def edge(t,kind):
        return t['begin_elapsed']+((t[kind]-t['begin_tick'])&0xffffffff)
    def excess(measured,lo,hi):
        return max(lo-measured,measured-hi,0.)
    assert len(timing['buckets'])==len(buckets)
    for b,reported in zip(buckets,timing['buckets']):
        ws=b['timing']['witnesses']; first,last=ws[0]['current'],ws[1]['current']
        scale=(pulses[last['seq']][0]-pulses[first['seq']][0])*1e6/(
            (edge(last,'rise_before')-edge(first,'rise_before'))*tick_us)
        assert abs((scale-1)*1e6-reported['raw_clock_scale_ppm'])<.0001
        assert abs(b['timing']['max_bookkeeping_ticks']*tick_us-reported['max_bookkeeping_us'])<1e-9
        assert b['timing']['bookkeeping_seq']==reported['bookkeeping_seq']
        for w in ws:
            p,t=w['previous'],w['current']; rise,fall=pulses[t['seq']]
            width_error=max(width_error,excess((fall-rise)*1e6/scale,
                (edge(t,'fall_before')-edge(t,'rise_after'))*tick_us,
                (edge(t,'fall_after')-edge(t,'rise_before'))*tick_us))
            if t['seq'] and p['seq']+1==t['seq']:
                interval_error=max(interval_error,excess((rise-pulses[p['seq']][0])*1e6/scale,
                    (edge(t,'rise_before')-edge(p,'rise_after'))*tick_us,
                    (edge(t,'rise_after')-edge(p,'rise_before'))*tick_us))
    # Serialization/recalculation agreement, not a new physical acceptance gate.
    assert abs(width_error-timing['summary']['max_witness_width_outside_cpu_bracket_us'])<.0001
    assert abs(interval_error-timing['summary']['max_witness_interval_outside_cpu_bracket_us'])<.0001
    assert timing['summary']['original_acceptance']==scope
    if seconds == 1800:
        # This real elapsed-time run crosses 100 raw counter wraps and the older
        # failure window. Parsing validates extended ticks before conversion;
        # the selected physical evidence cannot qualify omitted pulse details.
        assert buckets[-1]['timing']['witnesses'][1]['current']['begin_elapsed'] > 100 * 2**32
        assert s['configuration']['audio_permille']==650
        assert s['configuration']['block_size']==16 and s['configuration']['usb_hz']==500
        assert width_error==interval_error==0
        assert [b['second'] for b in timing['buckets'][1611:1669]]==list(range(1611,1669))


for name in ('aggregate-baseline','diagnostic-baseline','aggregate-combined','diagnostic-combined'):
    verify(name,10)
    print('PASS:',name,'complete 10-second aggregate evidence; selected diagnostic pulses checked where present')

verify('soak-30m',1800)
print('PASS: soak-30m complete 1800-second diagnostic evidence; selected pulse brackets agree; older failure remains unresolved')
