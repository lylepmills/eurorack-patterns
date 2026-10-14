# Attribution and source boundaries

The text in [the catalog](docs/catalog.md) consists of original, concise research summaries and proposed reuse checks written by Rubato Audio. Each entry links to the maker documentation, technical account, release note, or source code that supports the observed behavior. The cited behavior belongs to that maker and the identified product/version. A proposed reuse or test is an interpretation, not an endorsement by the maker.

The public headers are original MIT-licensed library code unless a file states another license. Source links document design inspiration; any adapted or copied implementation must retain its source and required notices.

Source links are references and inspiration. The repository's MIT license applies to this repository's own code and writing; it does **not** relicense linked manuals, maker articles, firmware, artwork, names, or trademarks. The library does not copy those projects' source files. Any future contribution that adapts or copies third-party code must identify the exact file/revision, check that file's applicable license, preserve required copyright and license notices, and mark the derivative file clearly. A maker repository may contain files under different licenses; do not assume one repository-wide license covers every file.

## Inspected code revisions

| Maker/project | Revision | Catalog examples |
| --- | --- | --- |
| [Mutable Instruments Eurorack](https://github.com/pichenettes/eurorack/tree/f4cfa7697095a28d292bff758beb51deb49b5a86) | `f4cfa7697095a28d292bff758beb51deb49b5a86` | Beads, Braids, Plaits, Rings, Marbles, Clouds |
| [4ms DLD](https://github.com/4ms/DLD/tree/dfc4295fc9ca71be6243217ab544c2ef71705e3b) | `dfc4295fc9ca71be6243217ab544c2ef71705e3b` | Controls, clock handling, transitions, interrupt scheduling |
| [monome crow](https://github.com/monome/crow/tree/b340579d94e57e2b43336611b2c4037cff74bb80) | `b340579d94e57e2b43336611b2c4037cff74bb80` | Event queue |
| [Winterbloom Castor & Pollux](https://github.com/wntrblm/Castor_and_Pollux/tree/652b28c950ed04ca41f0d8aa98d9b1be2f310f76) | `652b28c950ed04ca41f0d8aa98d9b1be2f310f76` | Settings migration and validation |
| [Ornament & Crime](https://github.com/mxmxmx/O_C/tree/cfbffab4e2a1b162480264d4ef57c2bcb41580c6) | `cfbffab4e2a1b162480264d4ef57c2bcb41580c6` | Per-input trigger delay, pin identity, quantizer membership, persistence fixes |
| [monome Ansible](https://github.com/monome/ansible/tree/9796656cbbe9eb0227d380d555e31192f0cf32bf) | `9796656cbbe9eb0227d380d555e31192f0cf32bf` | Stopped-clock UI, edit/play targets, first-clock timing, flash exclusion, serialized modes |
| [monome Teletype](https://github.com/monome/teletype/tree/e390bacdf024f2234e2ade6a4821773b9a80a322) | `e390bacdf024f2234e2ade6a4821773b9a80a322` | Pulse retrigger/service, panic, running/deferred command lifetime, nested enqueue |
| [4ms MetaModule](https://github.com/4ms/metamodule/tree/1a94fe61b33ce0b6ba5d69103230c713e1536697) | `1a94fe61b33ce0b6ba5d69103230c713e1536697` | Mapped pickup, control-page identity, teardown, feedback queues and disconnect handling |

The catalog also credits Doepfer, Befaco, Intellijel, Xaoc Devices, Instruō, ALM, Make Noise, Noise Engineering, Expert Sleepers, Ornament & Crime, monome, and Winterbloom for the specific manuals, release notes, and maker accounts linked at each entry. Those sources are cited for factual observations; their wording and diagrams are not reproduced here. Versioned manuals and page references are retained where the research identified them. A source link is evidence for that entry, not a general claim that the maker uses or recommends this library.

## Second-pass implementation provenance

The source and bug-history pass credits the O_C collaborators (including Patrick Dowling, Max Stadler/mxmxmx and Tim Churches), monome and its contributors, and 4ms and its contributors beside their observations. Historical fix commits are pinned in the catalog in addition to the default-branch snapshots above. MetaModule's aggregate-presence and mapping-removal observations use `c4da22c9fe1df78c22b9f295bef10dc03cfd6af4` and `c3f74800f8bf43b4ddc77967881cad12611b02b6`; these were **unmerged branch evidence**, not main/v2.4.0 behavior at inspection.

| Library addition | Inspiration and independent scope |
| --- | --- |
| `trigger_delay.h` | O_C's [identity-preserving delay fix](https://github.com/mxmxmx/O_C/commit/cc2b6985c71a5aab5de8eba7a992b191b261a511). Our implementation uses a ring of due masks, a checked horizon, explicit schedule-before-tick order and documented coalescence. No O_C source was copied or adapted. |
| `pulses.h` | Teletype's [pulse timer fix](https://github.com/monome/teletype/pull/310) and inspected retrigger semantics. Our independent logical timer supports restart/ignore, cancel and caller-owned ticks; no hardware timer, command parser or GPL implementation is included. |
| `pickup.h` | MetaModule's [restricted-range](https://github.com/4ms/metamodule/commit/1f053d1fd16b654940ef865ee5305a6a8cc79d1f) and [destination-rearm](https://github.com/4ms/metamodule/commit/0d1d5d92834d9af87a2bda77f116b24ea33278da) changes. Our independent latch accepts effective mapped bounds and reports unreachable immediately; it does not port the mapping/snap algorithm or endpoint-jump policy. |

The inspected O_C trigger-delay, quantizer, settings and page-storage files contain MIT-style per-file notices; some GPIO/support files do not contain a license header, and the inspected repository has no top-level license file. This is not a blanket license conclusion about O_C. Ansible and Teletype contain top-level GPLv2 license text; MetaModule's root license specifies GPLv3 or later and distinguishes third-party dependencies. Those licenses remain attached to their respective projects. This pass incorporated factual summaries and independently specified code/tests, not upstream source or test text. Any later direct adaptation needs a fresh exact-file license review and preserved notices.

Research bounds, unresolved reports and distinctions between inspected upstream tests and executed library tests are recorded in [research-pass-2.md](docs/research-pass-2.md) and [validation.md](docs/validation.md).

## Optional reference-board example

The Raspberry Pi Pico example is original MIT application glue using the public
[Pico SDK](https://github.com/raspberrypi/pico-sdk/tree/079c6f39023649b154152db30f1d781e884879bc)
API. CI fetches SDK 2.3.1 separately; SDK sources and their per-file/third-party
licenses remain with that project and are not redistributed in this library.
No maker endorsement or physical validation is implied.
