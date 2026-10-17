# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Validate retained timing witnesses; CPU brackets are not pad-edge guarantees."""
from capture import require

MASK = 0xffffffff
NAMES = ('begin_elapsed,end_elapsed,seq,time_us,work_us,begin_tick,rise_before,'
         'rise_after,end_tick,fall_before,fall_after').split(',')
KINDS = ['first', 'last', 'interval_us', 'work_us', 'rise_interval_ticks',
         'width_ticks', 'begin_guard_ticks', 'end_guard_ticks', 'rise_call_ticks', 'fall_call_ticks']


def delta(a, b):
    return (a-b) & MASK


def metric(kind, p, t):
    if kind == 2: return t['time_us']-p['time_us'] if t['seq'] else 0
    if kind == 3: return t['work_us']
    if kind == 4: return delta(t['rise_before'], p['rise_before']) if t['seq'] else 0
    fields = {5: ('fall_before','rise_before'), 6: ('rise_after','begin_tick'),
              7: ('fall_after','end_tick'), 8: ('rise_after','rise_before'),
              9: ('fall_after','fall_before')}
    a, b = fields[kind]
    return delta(t[a], t[b])


def observation(values, hz, duration_us):
    t = dict(zip(NAMES, values))
    require(len(values) == len(NAMES) and all(0 <= v <= MASK for v in values[2:])
            and 0 <= t['begin_elapsed'] <= t['end_elapsed'] < (duration_us+1000000)*hz//1000000,
            'invalid diagnostic observation bounds')
    require(t['time_us'] == t['begin_elapsed']*1000000//hz
            and t['work_us'] == t['end_elapsed']*1000000//hz-t['time_us'],
            'diagnostic clock conversion mismatch')
    stages = ['begin_tick','rise_before','rise_after','end_tick','fall_before','fall_after']
    elapsed = [delta(t[name], t['begin_tick']) for name in stages]
    require(elapsed == sorted(elapsed) and elapsed[-1] < 0x80000000
            and delta(t['end_tick'],t['begin_tick']) == t['end_elapsed']-t['begin_elapsed'],
            'diagnostic raw tick ordering mismatch')
    return t


def parse_bucket(take, bucket, base_seq, hz, duration_us, origin):
    words = take().decode('ascii').rstrip('\n').split(',')
    require(len(words) == 5 and words[0] == 'T', 'missing timing bucket')
    second, count, cost, seq = map(int, words[1:])
    require(second == bucket['second'] and count == bucket['samples'] and 0 <= cost <= MASK,
            'timing bucket accounting mismatch')
    result = dict(second=second, samples=count, max_bookkeeping_ticks=cost,
                  bookkeeping_seq=seq, witnesses=[])
    if not count:
        require(cost == seq == 0, 'invalid empty timing bucket')
        return result, origin
    require(base_seq <= seq < base_seq+count, 'bookkeeping sequence outside bucket')
    known = {}
    for kind in range(len(KINDS)):
        words = take().decode('ascii').rstrip('\n').split(',')
        require(len(words) == 3+2*len(NAMES) and words[0] == 'D'
                and int(words[1]) == second and int(words[2]) == kind, 'missing/reordered timing witness')
        values = list(map(int, words[3:]))
        p, t = [observation(v, hz, duration_us) for v in (values[:len(NAMES)], values[len(NAMES):])]
        require(base_seq <= t['seq'] < base_seq+count
                and bucket['first_us'] <= t['time_us'] <= bucket['last_us'],
                'timing witness outside bucket')
        if kind < 2:
            require(p == t and t['seq'] == base_seq+(count-1 if kind else 0)
                    and t['time_us'] == bucket['last_us' if kind else 'first_us'],
                    'timing endpoint mismatch')
        elif not t['seq']:
            require(p == t, 'invalid first-sample predecessor')
        else:
            require(p['seq']+1 == t['seq'] and p['time_us'] < t['time_us']
                    and p['end_elapsed'] <= t['begin_elapsed']
                    and t['begin_elapsed']-p['begin_elapsed'] < 0x80000000,
                    'invalid timing predecessor')
        for v in (p, t):
            this_origin = delta(v['begin_tick'],v['begin_elapsed'])
            if origin is None: origin = this_origin
            require(this_origin == origin, 'inconsistent raw/extended clock origin')
            require(v['seq'] not in known or known[v['seq']] == v, 'conflicting timing witness')
            known[v['seq']] = v
        result['witnesses'].append(dict(kind=KINDS[kind], previous=p, current=t))
    witnesses = result['witnesses']
    require(metric(2, witnesses[2]['previous'], witnesses[2]['current']) == bucket['max_interval_us']
            and witnesses[3]['current']['work_us'] == bucket['max_work_us'],
            'timing witness disagrees with aggregate maximum')
    # Selection must dominate every retained candidate, even when another peak
    # first exposed it. All raw observations remain available for physical review.
    for kind in range(2, len(KINDS)):
        peak = metric(kind, witnesses[kind]['previous'], witnesses[kind]['current'])
        for w in witnesses[2:]:
            require(metric(kind, w['previous'], w['current']) <= peak,
                    'timing witness is not a retained maximum')
    return result, origin
