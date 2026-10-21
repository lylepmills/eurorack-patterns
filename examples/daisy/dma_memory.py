# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""DMA-visible buffer placement and protocol-7/8/9 plan checks; no hardware access."""
from capture import require

CAPACITY = 16384
KEYS = ('region', 'source', 'destination', 'capacity_bytes', 'cache_line_bytes')
REGIONS = {0: (0xc0000000, 0xc4000000), 1: (0x24000000, 0x24078000), 2: (0xc0000000, 0xc4000000)}
REGIONS.update({r: REGIONS[0] for r in range(3, 10)})
SYMBOLS = {0: 'ep_dma_sdram_buffers', 1: 'ep_dma_internal_buffers',
           2: 'ep_dma_sdram_high_buffers'}
FIXED_STORAGE = {
    'ep_dma_sdram_buffers': (0xc0000000, 32768),
    'ep_dsp_delay': (0xc0008000, 2097152),
    'ep_dma_sdram_high_buffers': (0xc1d77400, 32768),
    'ep_jack_records': (0xc2000000, 28800000),
}
ALIGNMENT_STORAGE = {k:v for k,v in FIXED_STORAGE.items() if k != 'ep_dma_sdram_high_buffers'}
ALIGNMENT_STORAGE.update(ep_dma_low_arena=(0xc0210000, 65536),
                         ep_dma_high_arena=(0xc1d70000, 65536))
# Each selector is a view into one reserved arena. Views overlap across runs;
# only one is active, with disjoint 16 KiB source and destination buffers.
ALIGNMENTS = {2: ('high', 0x7400), 3: ('low', 0), 4: ('high', 0),
              5: ('low', 32), 6: ('high', 32), 7: ('low', 1024),
              8: ('high', 1024), 9: ('low', 0x7400)}


def arguments(args):
    return getattr(args, 'dma_region', 0), getattr(args, 'dma_period_us', 1000)


def validate_plan(kib, region, period, protocol=7):
    require(kib in (0, 4, 16) and region in REGIONS and period in (1000, 2000) and
            (kib or (region, period) == (0, 1000)), 'invalid DMA memory/cadence plan')
    require(protocol >= 7 or (region, period) == (0, 1000),
            'selectable DMA memory/cadence requires protocol 7')
    require(region != 2 or protocol >= 8, 'high SDRAM pair requires protocol 8')
    require(region < 3 or protocol >= 9, 'alignment selection requires protocol 9')


def report(values, kib, region):
    require(len(values) == 5 and all(type(v) is int and 0 <= v <= 0xffffffff for v in values),
            'invalid DMA memory report')
    result = dict(zip(KEYS, values))
    if not kib:
        require(not any(values), 'DMA memory reported while disabled')
        return result
    selected, source, destination, capacity, line = values
    require(selected == region and selected in REGIONS, 'DMA memory region differs')
    begin, end = REGIONS[selected]
    require(capacity == CAPACITY and line == 32 and
            all(begin <= address <= end - capacity and address % line == 0
                for address in (source, destination)) and
            (source + capacity <= destination or destination + capacity <= source),
            'DMA buffers outside region, overlapping, misaligned or wrong size')
    return result


def linked_buffers(nm_output, protocol=7):
    result = {}
    for region, symbol in SYMBOLS.items():
        if region == 2 and protocol < 8: continue
        if region == 2 and protocol >= 9: continue
        matches = [line.split() for line in nm_output.splitlines()
                   if line.split() and line.split()[-1] == symbol]
        require(len(matches) == 1 and len(matches[0]) == 4, 'missing/ambiguous DMA ELF symbol')
        address, size, kind, _ = matches[0]
        address, size = int(address, 16), int(size, 16)
        require(size == 2 * CAPACITY and kind.lower() == 'b', 'unexpected DMA ELF storage')
        result[str(region)] = report([region, address, address + CAPACITY, CAPACITY, 32], 16, region)
    if protocol >= 9:
        storage = fixed_storage(nm_output, protocol)
        for region, (area, offset) in ALIGNMENTS.items():
            arena = storage['ep_dma_' + area + '_arena']
            require(offset % 32 == 0 and offset + 2 * CAPACITY <= arena['size_bytes'],
                    'DMA alignment view exceeds arena')
            address = arena['address'] + offset
            result[str(region)] = report([region,address,address+CAPACITY,CAPACITY,32],16,region)
    elif protocol >= 8: fixed_storage(nm_output)
    return result


def fixed_storage(nm_output, protocol=8):
    result = {}
    for symbol, expected in (ALIGNMENT_STORAGE if protocol >= 9 else FIXED_STORAGE).items():
        matches = [line.split() for line in nm_output.splitlines()
                   if line.split() and line.split()[-1] == symbol]
        require(len(matches) == 1 and len(matches[0]) == 4, "missing/ambiguous fixed ELF storage")
        address, size, kind, _ = matches[0]
        address, size = int(address, 16), int(size, 16)
        require((address, size) == expected and kind.lower() == "b", "fixed SDRAM layout differs")
        result[symbol] = dict(address=address, size_bytes=size)
    return result


def verify_manifest(run, manifest):
    if manifest['protocol'] < 7: return
    require('dma_memory' in run, 'missing DMA memory report')
    if run['dma']['kib']:
        memory = run['dma_memory']
        expected = manifest.get('dma_linked_buffers', {}).get(str(memory['region']))
        require(expected == memory, 'DMA addresses differ from linked firmware manifest')
