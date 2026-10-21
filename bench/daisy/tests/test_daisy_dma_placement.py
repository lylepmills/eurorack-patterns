# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Protocol-8 fixed placement, compatibility, provenance and bounded plans."""
import argparse
import unittest
from test_daisy_dma_memory import fixture as prior, j, m, dsp, REFERENCE, rehash
import dma_placement


def fixture(region=0, period=1000, finish=False):
    raw, _, _ = prior(region, period, finish=finish)
    lines = raw.splitlines(keepends=True)
    lines[0] = lines[0].replace(b'"protocol":7', b'"protocol":8')
    if region == 2:
        address = m.FIXED_STORAGE['ep_dma_sdram_high_buffers'][0]
        lines[8] = f'JMEM,2,{address},{address+16384},16384,32\n'.encode()
    return rehash(lines)


def symbols():
    return '24000000 00008000 B ep_dma_internal_buffers\n' + ''.join(
        f'{address:08x} {size:08x} B {symbol}\n'
        for symbol, (address, size) in m.FIXED_STORAGE.items())


class Placement(unittest.TestCase):
    def test_replay_all_regions_periods_and_finish(self):
        for region in (0, 1, 2):
            for period in (1000, 2000):
                for finish in (False, True):
                    with self.subTest(region=region, period=period, finish=finish):
                        run = j.parse(fixture(region, period, finish))[1]
                        self.assertEqual(run['dma_memory']['region'], region)
                        m.verify_manifest(run, dict(protocol=8,
                            dma_linked_buffers=m.linked_buffers(symbols(), protocol=8)))
                        dsp.verify(run, REFERENCE)
        self.assertEqual(j.digital_layout(8, clock_reference=True),
                         j.digital_layout(7, clock_reference=True))
        parser = argparse.ArgumentParser(); j.add_dsp_arguments(parser)
        self.assertEqual(parser.parse_args(['--dma-region', '2']).dma_region, 2)
        with self.assertRaisesRegex(ValueError, 'protocol 8'):
            j.parse(fixture(2).replace(b'"protocol":8', b'"protocol":7'))
        with self.assertRaises(ValueError): m.validate_plan(16,3,1000,8)
        with self.assertRaises(ValueError): m.validate_plan(0,2,1000,8)

    def test_final_elf_requires_exact_disjoint_storage(self):
        text = symbols()
        self.assertEqual(m.linked_buffers(text,8)['2']['source'],0xc1d77400)
        self.assertEqual(m.fixed_storage(text)['ep_jack_records']['address'],0xc2000000)
        for old,new in [('c1d77400','c1d77420'),('c2000000','c0208000'),
                        ('c0008000','c0000000'),('00008000','00004000'),
                        ('ep_jack_records','unknown'),(' B ',' D ')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                m.linked_buffers(text.replace(old,new),8)
        with self.assertRaises(ValueError): m.linked_buffers(text+text,8)
        with self.assertRaises(ValueError): m.linked_buffers(text.splitlines()[0],8)

    def test_live_report_cannot_substitute_another_valid_sdram_address(self):
        run = j.parse(fixture(2))[1]
        manifest = dict(protocol=8, dma_linked_buffers=m.linked_buffers(symbols(),8))
        run['dma_memory'].update(source=0xc0000000,destination=0xc0004000)
        with self.assertRaisesRegex(ValueError,'linked firmware'): m.verify_manifest(run,manifest)

    def test_balanced_bounded_plan_and_achieved_work(self):
        cases = dma_placement.cases()
        self.assertEqual(len(cases),14)
        self.assertEqual(len({c['name'] for c in cases}),14)
        self.assertEqual([c['dma_region'] for c in cases[4:12]], [0,2,2,0,2,0,0,2])
        for c in cases:
            m.validate_plan(c['dma_kib'],c['dma_region'],c['dma_period_us'],8)
            j.validate_audio(10000,c['audio_block'],c['audio_permille'],c['audio_off_ms'])
            j.validate_dsp(10000,c['audio_block'],c['audio_permille'],c['dsp_voices'],c['dma_kib'])
        left,right = [j.parse(fixture(r,2000))[1] for r in (0,2)]
        self.assertTrue(dma_placement.compare(left,right)['completion_counts_matched'])
        right['dma']['skipped'] += 1
        self.assertFalse(dma_placement.compare(left,right)['completion_counts_matched'])
        right['dsp']['voices'] += 1
        with self.assertRaisesRegex(ValueError,'workload'): dma_placement.compare(left,right)


if __name__ == '__main__': unittest.main(argv=[__file__])
