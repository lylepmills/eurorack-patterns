/* SPDX-License-Identifier: MIT
 * Copyright 2026 Lyle Mills
 * Augment the pinned SDK script; do not place DMA buffers in its default DTCM.
 * NOLOAD storage is fully written before DMA use; startup need not zero it.
 */
SECTIONS
{
    .ep_dma_internal (NOLOAD) : ALIGN(32)
    {
        KEEP(*(.ep_dma_internal))
    } > SRAM
}
INSERT AFTER .fini_array;
ASSERT(SIZEOF(.ep_dma_internal) == 32768, "Unexpected internal DMA buffer size")
ASSERT(ADDR(.ep_dma_internal) >= 0x24000000 &&
       ADDR(.ep_dma_internal) + SIZEOF(.ep_dma_internal) <= 0x24078000,
       "Internal DMA buffers outside application AXI SRAM")
