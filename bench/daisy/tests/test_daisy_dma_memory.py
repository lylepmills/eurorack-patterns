# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Protocol-7 placement/cadence corruption and early-finish replay; no hardware."""
import unittest
from test_daisy_dsp_capture import fixture as prior, j, dsp, REFERENCE, rehash
import dma_memory as m
import dma_comparison


def fixture(region=0, period=1000, kib=16, finish=False):
    raw, c, a = prior(kib=kib, finish=finish)
    lines = raw.splitlines(keepends=True)
    lines[0] = lines[0].replace(b'"protocol":6', b'"protocol":7')
    lines[1] = lines[1][:-1] + f',{region},{period}\n'.encode()
    if kib and period == 2000:
        parts = lines[7][:-1].split(b',')
        n = 687 if finish else 3999
        for i, value in {2:period, 3:n, 4:n, 5:n, 6:n*kib*1024, 11:2100,
                         13:2100, 15:n}.items():
            parts[i] = str(value).encode()
        lines[7] = b','.join(parts) + b'\n'
    base = m.REGIONS[region][0]
    memory = [region, base, base+m.CAPACITY, m.CAPACITY, 32] if kib else [0]*5
    lines.insert(8, ('JMEM,' + ','.join(map(str, memory)) + '\n').encode())
    return rehash(lines), c, a


class DmaMemory(unittest.TestCase):
    def test_regions_cadences_and_finish(self):
        for region in (0, 1):
            for period in (1000, 2000):
                for finish in (False, True):
                    with self.subTest(region=region, period=period, finish=finish):
                        raw, _, _ = fixture(region, period, finish=finish)
                        run = j.parse(raw)[1]
                        self.assertEqual(run['dma']['period_us'], period)
                        self.assertEqual(run['dma_memory']['region'], region)
                        dsp.verify(run, REFERENCE)
        raw, _, _ = fixture(kib=0)
        self.assertFalse(any(j.parse(raw)[1]['dma_memory'].values()))
        self.assertNotIn('dma_memory', j.parse(prior()[0])[1])

    def test_missing_corrupt_and_wrong_region_report(self):
        raw, _, _ = fixture(1)
        for index, value in ((1,0),(2,0x20000000),(2,0x24000001),
                             (2,0x24074020),(3,0x24000000),(3,0xffffffff),
                             (4,4096),(5,64)):
            lines = raw.splitlines(keepends=True)
            parts = lines[8][:-1].split(b',')
            parts[index] = str(value).encode()
            lines[8] = b','.join(parts) + b'\n'
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                j.parse(rehash(lines))
        lines = raw.splitlines(keepends=True); del lines[8]
        with self.assertRaises(ValueError): j.parse(rehash(lines))
        lines = raw.splitlines(keepends=True)
        lines[7] = lines[7].replace(b'JDMA,16,1000,', b'JDMA,16,2000,')
        with self.assertRaisesRegex(ValueError, 'configuration'): j.parse(rehash(lines))
        run = j.parse(raw)[1]
        manifest = dict(protocol=7, dma_linked_buffers={'1':dict(run['dma_memory'])})
        m.verify_manifest(run, manifest)
        manifest['dma_linked_buffers']['1']['source'] += 32
        with self.assertRaisesRegex(ValueError, 'linked firmware'): m.verify_manifest(run, manifest)

    def test_elf_symbols_and_application_bounds(self):
        text = '24010000 00008000 B ep_dma_internal_buffers\nc0000000 00008000 b ep_dma_sdram_buffers\n'
        regions = m.linked_buffers(text)
        self.assertEqual(regions['1']['destination'], 0x24014000)
        for bad in (text+text, text.replace('24010000','20000000'),
                    text.replace('24010000','24074000'), text.replace('00008000','00004000'),
                    text.replace(' B ', ' D '), text.replace('internal_buffers','other')):
            with self.subTest(bad=bad), self.assertRaises(ValueError): m.linked_buffers(bad)
        m.report([1,0x24070000,0x24074000,16384,32],16,1)

    def test_plan_rejections_and_requested_rate_coverage(self):
        for args in ((0,1,1000),(0,0,2000),(16,2,1000),(16,1,500),(16,1,1000,6),
                     (16,0,2000,6)):
            with self.subTest(args=args), self.assertRaises(ValueError): m.validate_plan(*args)
        raw,_,_ = fixture(period=2000); run = j.parse(raw)[1]
        run['dma']['verified'] = 1999
        with self.assertRaisesRegex(ValueError, 'cover'): dsp.verify(run,REFERENCE)
        self.assertEqual(j.digital_layout(6,clock_reference=True),
                         j.digital_layout(7,clock_reference=True))

    def test_balanced_comparison_and_throughput_confounds(self):
        cases = dma_comparison.cases()
        self.assertEqual(len(cases),12)
        self.assertEqual(len({c['name'] for c in cases}),12)
        self.assertEqual([c['dma_region'] for c in cases[2:10]], [0,1,1,0,0,1,1,0])
        for c in cases:
            j.validate_audio(10000,c['audio_block'],c['audio_permille'],c['audio_off_ms'])
            j.validate_dsp(10000,c['audio_block'],c['audio_permille'],c['dsp_voices'],c['dma_kib'])
            m.validate_plan(c['dma_kib'],c['dma_region'],c['dma_period_us'])
        left,right = [j.parse(fixture(r,2000)[0])[1] for r in (0,1)]
        self.assertTrue(dma_comparison.compare(left,right)['completion_counts_matched'])
        right['dma']['skipped'] = 1
        self.assertFalse(dma_comparison.compare(left,right)['completion_counts_matched'])
        right['dma']['skipped'] = 0; right['dma']['verified'] -= 100
        self.assertFalse(dma_comparison.compare(left,right)['completion_counts_matched'])
        right['dma']['period_us'] = 1000
        with self.assertRaisesRegex(ValueError, 'workload'): dma_comparison.compare(left,right)


if __name__ == '__main__': unittest.main(argv=[__file__])
