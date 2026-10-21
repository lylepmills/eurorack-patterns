#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Export reviewed jack preflight evidence with an explicit public-data allowlist.

Reads saved wire/digital/derived-analog data only; opens no device. The complete
native scope waveforms remain with the operator and are identified by hashes.
"""
import argparse
import gzip
import hashlib
import json
import lzma
import struct
from pathlib import Path
import re
from review_daisy_jacks import review, review_motion, review_fault_motion, CASES
from jack_capture import parse, CONFIG
from daisy_scope import match_service

MOTION_CASES = {
    'manual-ordinary-silent': (3, 'ordinary insertion/withdrawal; passive terminated far end'),
    'manual-slow-partial-silent': (2, 'attempted slow/partial insertion/withdrawal; passive terminated far end'),
    'manual-slow-insertion-silent': (2, 'attempted slow insertion with ordinary withdrawal; passive terminated far end'),
    'manual-ordinary-open': (2, 'ordinary insertion/withdrawal; open unconnected far end'),
    'manual-ordinary-open-second-cable': (2, 'ordinary insertion/withdrawal; open unconnected far end; second cable'),
    'manual-transition-fault': (1, 'insertion/withdrawal with a triggered fault; unpowered far end'),
    'automated-electrical-clamp': (1, 'empty jack with independent open-drain clamp on tip/sense; no cable movement'),
    'automated-clean-finish': (0, 'stationary empty jack; automatic operator-finish request; no cable movement'),
}


def sha(data): return hashlib.sha256(data).hexdigest()


def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result: raise ValueError('duplicate JSON key')
        result[k] = v
    return result


def export(source, prefix, expected, case='empty', *, derived=None, dsp_reference=None, clock_reference=False):
    motion = case in MOTION_CASES
    assert case in CASES or motion
    raw = (source / 'fixture/raw.txt').read_bytes()
    assert not clock_reference or case == 'automated-electrical-clamp', 'clock-reference export requires automated clamp case'
    info, run, rows, _ = parse(raw, clock_reference=clock_reference)
    loaded = info['protocol'] >= 4
    derived = source if derived is None else derived
    recorded = json.loads(raw.split(b'\n', 1)[0][6:], object_pairs_hook=unique)
    assert set(recorded) == set(CONFIG) | {'kind', 'board', 'build_id', 'ready', 'timer_hz', 'adc_hz', 'protocol'}
    assert recorded == info and re.fullmatch('[0-9a-f]{24}', info['build_id'])
    for k, v in info.items():
        if k not in ('kind', 'board', 'build_id'): assert type(v) in (int, bool)
    meta = json.loads((source / 'fixture/metadata.json').read_text())
    build = meta['build']; assert meta['status'] == 'complete' and build['build_id'] == info['build_id']
    declared = json.loads(meta['declared_fixture'])
    assert declared.get('case', 'empty') == case, 'fixture declaration differs from requested case'
    assert re.fullmatch('[0-9a-f]{40}', build['source_commit'])
    assert re.fullmatch('[0-9a-f]{40}', build['sdk_revision'])
    binary = build['artifacts_sha256']['patterns_jack.bin']; assert re.fullmatch('[0-9a-f]{64}', binary)
    channels = json.loads((derived / 'channels.json').read_text(), object_pairs_hook=unique)
    assert set(channels) == {'sense', 'service', 'presence', 'probe'} | ({'audio'} if loaded else set())
    for d in channels.values():
        assert set(d) == {'initial_high', 'edges_s', 'begin_s', 'end_s'}
        assert type(d['initial_high']) is bool
        assert all(type(t) in (int, float) for t in d['edges_s'])
        assert all(type(d[k]) in (int, float) for k in ('begin_s', 'end_s'))
    analog = json.loads((derived / ('analog-apertures.json' if motion else 'analog-plateaus.json')).read_text(), object_pairs_hook=unique)
    if motion:
        assert set(analog) == {'sample_rate_hz','begin_s','end_s','samples','first_indices','last_indices',
                              'minimum_volts','maximum_volts','representation'} | ({'source_plateaus'} if loaded else set())
        assert analog['representation'] == 'Native extrema over each service aperture, including boundary samples'
        for key in ('first_indices','last_indices','minimum_volts','maximum_volts'):
            assert all(type(v) in (int,float) for v in analog[key])
        for key in ('sample_rate_hz','begin_s','end_s','samples'): assert type(analog[key]) in (int,float)
        if loaded:
            p = analog['source_plateaus']
            assert set(p) == {'center_indices','minimum_volts','maximum_volts','representation'}
            assert p['representation'] == 'Three native samples centered at or before each service midpoint; source timing only'
            assert all(type(v) in (int,float) for k in ('center_indices','minimum_volts','maximum_volts') for v in p[k])
    else:
      assert set(analog) == {'sample_rate_hz', 'begin_s', 'end_s', 'samples', 'min_volts', 'max_volts',
                           'plateau_indices', 'plateau_volts', 'representation'}
      assert analog['representation'] == 'One native analog sample at or just before each service fall; complete native waveform archived separately'
      assert all(type(v) in (int, float) for k in ('plateau_indices', 'plateau_volts') for v in analog[k])
      assert all(type(analog[k]) in (int, float) for k in ('sample_rate_hz','begin_s','end_s','samples','min_volts','max_volts'))
    generator_raw = None
    generator_build = None
    if case == 'automated-electrical-clamp':
        assert expected == 'pass'
        generator_raw = (source.parent / (source.name + '-generator.txt')).read_bytes()
        campaign = json.loads((source.parent / 'matrix.json').read_text())
        generator_build = campaign['generator_build']
        assert re.fullmatch('[0-9a-f]{24}', generator_build['build_id'])
        assert all(re.fullmatch('[0-9a-f]{40}', generator_build[k]) for k in ('source_commit','sdk_revision'))
        assert re.fullmatch('[0-9a-f]{64}', generator_build['artifacts_sha256']['patterns_pulse_generator.bin'])
        gen_info = json.loads(generator_raw.split(b'\n',1)[0][8:], object_pairs_hook=unique)
        assert set(gen_info) == {'kind','protocol','board','build_id','released','armed','max_edges','max_us','max_late_us','timer_hz'}
        assert all(type(v) in (int,bool) for k,v in gen_info.items() if k not in ('kind','board','build_id'))
    clock_bytes = None
    if clock_reference:
        from inspect_daisy_timing import read_digital
        clock_bytes = (source / 'scope/digital_2_0.bin').read_bytes()
        initial, edges = read_digital(clock_bytes)
        _, _, begin, end, _ = struct.unpack_from('<IdddQ', clock_bytes, 24)
        channels['clock'] = dict(initial_high=initial, edges_s=edges, begin_s=begin, end_s=end)
    outcome = None
    rejection_detail = None
    try:
        if case == 'automated-electrical-clamp':
            if loaded:
                from review_daisy_jack_load import review as electrical_review
                assert campaign['times_us'] in ([3000000,6500000],[3000000,10500000])
            else:
                from review_daisy_jack_matrix import review as electrical_review
                assert campaign['times_us'] == [3000000,6500000]
            kwargs = {'dsp_reference': dsp_reference} if info['protocol'] >= 6 else {}
            if clock_reference: kwargs['clock_reference'] = True
            outcome = electrical_review(raw, channels, analog, generator_raw,
                                        generator_build['build_id'], campaign['times_us'], **kwargs)
            if loaded and (campaign['times_us'][1] == 10500000 or not run['audio']['block']):
                assert outcome['qualification'] == 'responsive'
        elif case == 'automated-clean-finish':
            from review_daisy_jack_load import review_finish
            outcome = review_finish(raw, channels, analog, dsp_reference=dsp_reference)
        elif case == 'manual-transition-fault': outcome = review_fault_motion(raw, channels, analog)
        elif motion: outcome = review_motion(raw, channels, analog, cycles=MOTION_CASES[case][0])
        else: outcome = review(raw, channels, analog, info['build_id'], case=case)
    except ValueError as e:
        if expected == 'missing-motion-tail':
            assert motion and str(e) == 'Service count mismatch or unsupported startup prefix'
            service = channels['service']; count = len(service['edges_s']) // 2
            assert not service['initial_high'] and len(service['edges_s']) % 2 == 0 and 0 < count < len(rows)
            service_rows = [dict(time_us=r['sample_us'], work_us=r['end_us']-r['sample_us']) for r in rows[:count]]
            rises, _, alignment = match_service(service_rows, service['edges_s'])
            expected_end = rises[0] + (run['elapsed_us']-rows[0]['sample_us']) * (1+alignment['clock_scale_ppm']/1e6) / 1e6
            assert service['end_s'] < expected_end and analog['end_s'] < expected_end
            assert len(analog['minimum_volts']) == len(analog['maximum_volts']) == count
            rejection_detail = dict(firmware_samples=len(rows), scope_service_samples=count,
                missing_tail_samples=len(rows)-count, prefix_timing_diagnostic=alignment,
                limitation='Prefix alignment locates the missing tail; it does not qualify the complete recording.')
        elif expected == 'motion-analog-disagreement':
            assert motion and str(e) in ('stable low analog/ADC disagreement', 'stable high analog/ADC disagreement')
        elif expected == 'missing-probe':
            assert case == 'empty'
            assert str(e) == 'unexpected probe edge count'
            assert not channels['probe']['edges_s'] and not channels['probe']['initial_high']
        else:
            assert case == 'empty' and expected == 'analog-disagreement' and str(e) == 'analog/digital plateau disagreement'
    else: assert expected == 'pass'
    if clock_reference: del channels['clock']  # Separate lossless native payload, never JSON-expanded.
    payloads = dict(raw=raw, channels=json.dumps(channels, separators=(',', ':')).encode(),
                    analog=json.dumps(analog, separators=(',', ':')).encode())
    if generator_raw is not None: payloads['generator'] = generator_raw
    scope_names = {'record_options.json','capture_config_full.json','capture_stdout.txt',
                   'record_result.json','digital_0.bin','digital_1.bin','digital_2.bin','digital_3.bin','analog_0.bin'}
    manual_scope_names = {'settings.json','capture.sal','analog_0.bin',
                          'digital_1_0.bin','digital_1_1.bin','digital_1_2.bin','digital_1_3.bin'}
    if loaded: manual_scope_names.add('digital_2_0.bin')
    if clock_reference: manual_scope_names.add('digital_2_1.bin')
    files = {p.name:sha(p.read_bytes()) for p in (source / 'scope').iterdir() if p.is_file()}
    assert set(files) in (scope_names, manual_scope_names)
    published = dict(schema=1, evidence='measured on hardware', status=expected,
        build=dict(build_id=info['build_id'], source_commit=build['source_commit'], sdk_revision=build['sdk_revision'], binary_sha256=binary),
        fixture=dict(board='Seed3', case=case, jack='switched mono; ' + (MOTION_CASES[case][1] if motion else CASES[case]), probe_series_ohms=1000,
                     sense_pulldown_ohms=100000, scope_probe='10x; sense node', analog_rate_hz=analog['sample_rate_hz']),
        run=run, review=outcome, native_scope_sha256=files,
        limitation=((outcome['limitation'] if outcome else 'Physical motion review rejected; independent evidence is incomplete or disagrees with the ADC. No complete physical pass or mechanical-position qualification.') + ' All acquired digital transitions and complete wire evidence; analog payload contains extrema over captured service apertures, not the full waveform.' if motion else
                    'Complete digital timelines and wire records; analog export is one plateau sample per observation plus extrema, not the full waveform. No insertion or external-module voltage qualification.'))
    if clock_reference:
        published['status'] = outcome['status']
        published['clock_reference'] = True
        published['limitation'] += ' Scheduling and behavior are checked in counted HSE cycles; the original external-clock stability result is retained separately. No calibrated absolute-clock or audio-fidelity claim.'
    if expected == 'missing-probe': published['rejection'] = 'Physical probe channel stayed low; incomplete independent evidence, not a hardware pass.'
    if generator_build is not None:
        published['generator_times_us'] = campaign['times_us']
        published['generator_build'] = dict(build_id=generator_build['build_id'],
            source_commit=generator_build['source_commit'], sdk_revision=generator_build['sdk_revision'],
            binary_sha256=generator_build['artifacts_sha256']['patterns_pulse_generator.bin'])
    if expected == 'analog-disagreement':
        published['rejection'] = 'Analog plateaus disagree with the independently recorded digital sense and ADC; cause unresolved, not a hardware pass.'
    if expected == 'motion-analog-disagreement':
        published['rejection'] = 'Stable analog apertures contradict ADC readings during a motion capture; cause unresolved, not a hardware pass.'
    if expected == 'missing-motion-tail':
        published['rejection'] = 'Scope digital/analog coverage ends before the firmware acquisition boundary; missing tail evidence, not a hardware pass.'
        published['rejection_detail'] = rejection_detail
    assert not prefix.with_suffix('.json').exists()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        dest = prefix.parent / (prefix.name + '-' + name + '.txt.gz')
        assert not dest.exists()
        packed = gzip.compress(data, compresslevel=9, mtime=0)
        published[name + '_sha256'] = sha(data); published[name + '_compressed_sha256'] = sha(packed)
        dest.write_bytes(packed)
    if clock_bytes is not None:
        dest = prefix.parent / (prefix.name + '-clock.bin.xz')
        assert not dest.exists()
        packed = lzma.compress(clock_bytes, filters=[
            {'id': lzma.FILTER_DELTA, 'dist': 8}, {'id': lzma.FILTER_LZMA2, 'preset': 3}])
        assert lzma.decompress(packed) == clock_bytes, 'lossless clock roundtrip'
        published['clock_file'] = dest.name
        published['clock_sha256'] = sha(clock_bytes)
        published['clock_compressed_sha256'] = sha(packed)
        dest.write_bytes(packed)
    prefix.with_suffix('.json').write_text(json.dumps(published, indent=2) + '\n')
    return published

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path); p.add_argument('prefix', type=Path)
    p.add_argument('--expected', choices=('pass','missing-probe','analog-disagreement','motion-analog-disagreement','missing-motion-tail'), default='pass')
    p.add_argument('--case', choices=tuple(CASES)+tuple(MOTION_CASES), default='empty')
    p.add_argument('--dsp-reference', type=Path)
    p.add_argument('--clock-reference', action='store_true')
    a = p.parse_args(); result = export(a.source, a.prefix, a.expected, a.case, dsp_reference=a.dsp_reference, clock_reference=a.clock_reference)
    print(result['status'], result['run']['count'], 'observations exported')
