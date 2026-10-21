/* SPDX-License-Identifier: MIT
 * Copyright 2026 Lyle Mills
 * Both DMA pairs coexist: switching region cannot move code or other storage.
 * These NOLOAD buffers are initialized by the workload before reading them.
 */
SECTIONS
{
    .ep_dma_sdram 0xc0000000 (NOLOAD) : { KEEP(*(.ep_dma_sdram)) } > SDRAM
    .ep_dsp_delay 0xc0008000 (NOLOAD) : { KEEP(*(.ep_dsp_delay)) } > SDRAM
    .ep_dma_low_arena 0xc0210000 (NOLOAD) : { KEEP(*(.ep_dma_low_arena)) } > SDRAM
    .ep_dma_high_arena 0xc1d70000 (NOLOAD) : { KEEP(*(.ep_dma_high_arena)) } > SDRAM
    .ep_jack_records 0xc2000000 (NOLOAD) : { KEEP(*(.ep_jack_records)) } > SDRAM
}
INSERT BEFORE .sdram_bss;
ASSERT(SIZEOF(.ep_dma_sdram) == 32768, "Unexpected low SDRAM DMA size")
ASSERT(SIZEOF(.ep_dsp_delay) == 2097152, "Unexpected DSP delay size")
ASSERT(SIZEOF(.ep_dma_low_arena) == 65536, "Unexpected low SDRAM arena size")
ASSERT(SIZEOF(.ep_dma_high_arena) == 65536, "Unexpected high SDRAM arena size")
ASSERT(SIZEOF(.ep_jack_records) == 28800000, "Unexpected jack trace size")
ASSERT(ADDR(.ep_dma_sdram) + SIZEOF(.ep_dma_sdram) <= ADDR(.ep_dsp_delay) &&
       ADDR(.ep_dsp_delay) + SIZEOF(.ep_dsp_delay) <= ADDR(.ep_dma_low_arena) &&
       ADDR(.ep_dma_low_arena) + SIZEOF(.ep_dma_low_arena) <= ADDR(.ep_dma_high_arena) &&
       ADDR(.ep_dma_high_arena) + SIZEOF(.ep_dma_high_arena) <= ADDR(.ep_jack_records) &&
       ADDR(.ep_jack_records) + SIZEOF(.ep_jack_records) <= 0xc4000000,
       "SDRAM experiment buffers overlap or exceed memory")
ASSERT(SIZEOF(.sdram_bss) == 0, "Unaccounted SDRAM allocation in placement experiment")
