# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Protocol-9 alignment views, historical replay compatibility and ELF bounds."""
import argparse
import unittest
from test_daisy_dma_memory import fixture as prior, j, m, dsp, REFERENCE, rehash
import dma_alignment

EXPECTED = {0: 0xc0000000, 1: 0x24000000, 2: 0xc1d77400,
            3: 0xc0210000, 4: 0xc1d70000, 5: 0xc0210020, 6: 0xc1d70020,
            7: 0xc0210400, 8: 0xc1d70400, 9: 0xc0217400}


def fixture(region, period=2000, finish=False):
    raw, _, _ = prior(region, period, finish=finish)
    lines = raw.splitlines(keepends=True)
    lines[0] = lines[0].replace(b'"protocol":7', b'"protocol":9')
    a = EXPECTED[region]
    lines[8] = f'JMEM,{region},{a},{a+16384},16384,32\n'.encode()
    return rehash(lines)


def symbols():
    return '24000000 00008000 B ep_dma_internal_buffers\n' + ''.join(
        f'{a:08x} {n:08x} B {name}\n' for name, (a, n) in m.ALIGNMENT_STORAGE.items())


class Alignment(unittest.TestCase):
    def test_commands_complete_and_early_replay(self):
        manifest = dict(protocol=9, dma_linked_buffers=m.linked_buffers(symbols(),9))
        for region, address in EXPECTED.items():
            for period in (1000,2000):
                for finish in (False,True):
                    with self.subTest(region=region,period=period,finish=finish):
                        run = j.parse(fixture(region,period,finish))[1]
                        self.assertEqual(run['dma_memory']['source'],address)
                        m.verify_manifest(run,manifest)
                        dsp.verify(run,REFERENCE)
        self.assertEqual(j.digital_layout(9,clock_reference=True),j.digital_layout(8,clock_reference=True))
        parser=argparse.ArgumentParser();j.add_dsp_arguments(parser)
        self.assertEqual(parser.parse_args(['--dma-region','9']).dma_region,9)
        for region in range(3,10):
            for protocol in (7,8):
                with self.assertRaisesRegex(ValueError,'protocol 9'):
                    j.parse(fixture(region).replace(b'"protocol":9',f'"protocol":{protocol}'.encode()))
        for args in ((16,10,2000,9),(0,3,1000,9),(16,3,500,9)):
            with self.assertRaises(ValueError):m.validate_plan(*args)

    def test_exact_elf_arenas_and_runtime_selection(self):
        text=symbols(); linked=m.linked_buffers(text,9)
        self.assertEqual({int(k):v['source'] for k,v in linked.items()},EXPECTED)
        storage=m.fixed_storage(text,9)
        self.assertEqual(storage['ep_dsp_delay']['address'],0xc0008000)
        self.assertEqual(storage['ep_jack_records']['address'],0xc2000000)
        for old,new in (('c0210000','c0210020'),('c1d70000','c1d77400'),
                        ('00010000','00008000'),('c0008000','c0000000'),
                        ('c2000000','c0208000'),(' B ',' D ')):
            with self.subTest(old=old),self.assertRaises(ValueError):m.linked_buffers(text.replace(old,new),9)
        for bad in (text+text,text.splitlines()[0]):
            with self.assertRaises(ValueError):m.linked_buffers(bad,9)
        run=j.parse(fixture(5))[1]
        manifest=dict(protocol=9,dma_linked_buffers=linked)
        run['dma_memory']['source']-=32;run['dma_memory']['destination']-=32
        with self.assertRaisesRegex(ValueError,'linked firmware'):m.verify_manifest(run,manifest)

    def test_balanced_plan_and_work_comparisons(self):
        cases=dma_alignment.cases();self.assertEqual(len(cases),30)
        by_name={c['name']:c for c in cases};self.assertEqual(len(by_name),30)
        combined=[c for c in cases if c['name'].startswith('combined')]
        self.assertEqual([c['dma_region'] for c in combined[:8]],
                         [c['dma_region'] for c in combined[8:]][::-1])
        self.assertEqual(set(c['dma_region'] for c in combined),set(range(2,10)))
        for c in cases:
            m.validate_plan(c['dma_kib'],c['dma_region'],c['dma_period_us'],9)
            j.validate_audio(10000,c['audio_block'],c['audio_permille'],c['audio_off_ms'])
            j.validate_dsp(10000,c['audio_block'],c['audio_permille'],c['dsp_voices'],c['dma_kib'])
        pairs=dma_alignment.comparison_pairs();self.assertEqual(len(pairs),24)
        for pair in pairs:
            self.assertIn(pair['left'],by_name);self.assertIn(pair['right'],by_name)
        left,right=[j.parse(fixture(r))[1] for r in (5,6)]
        self.assertTrue(dma_alignment.compare(left,right)['completion_counts_matched'])
        right['dma']['skipped']=1
        self.assertFalse(dma_alignment.compare(left,right)['completion_counts_matched'])
        right['dma']['period_us']=1000
        with self.assertRaisesRegex(ValueError,'workload'):dma_alignment.compare(left,right)


if __name__=='__main__':unittest.main(argv=[__file__])
