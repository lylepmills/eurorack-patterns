# Source and bug-history pass, October 2026

This pass expands the catalog from **66 to 88 patterns**, adds three original portable components, and strengthens six existing entries. Its question was: *what small assumptions actually failed in maintained instruments, and what narrowly specified behavior would prevent that class of failure?*

The [catalog](catalog.md) contains the findings and proposed checks. [Validation](validation.md) separates executed host tests from further evidence needed on hardware. New source observations credit Ornament & Crime, monome Ansible and Teletype, and 4ms MetaModule. These projects do not endorse this library.

## What was investigated

Three parallel investigations read commit diffs, surrounding code, selected issue/PR discussions and upstream tests. Findings were checked against the existing catalog, then reviewed independently during integration. Head snapshots were recorded on 13 October 2026:

| Project | Inspected default-branch revision | History available; investigation scope |
| --- | --- | --- |
| [Ornament & Crime](https://github.com/mxmxmx/O_C/tree/cfbffab4e2a1b162480264d4ef57c2bcb41580c6) | `cfbffab4e2a1b162480264d4ef57c2bcb41580c6` | 1,234 commits across fetched refs; 276 keyword-matching subjects; about 20 targeted patches and adjacent code. First 100 issue/PR records examined as an index; selected bodies/comments read. |
| [Ansible](https://github.com/monome/ansible/tree/9796656cbbe9eb0227d380d555e31192f0cf32bf) | `9796656cbbe9eb0227d380d555e31192f0cf32bf` | 312 reachable commits. Combined with Teletype: more than 20 selected patches/PRs and roughly a dozen related reports. |
| [Teletype](https://github.com/monome/teletype/tree/e390bacdf024f2234e2ade6a4821773b9a80a322) | `e390bacdf024f2234e2ade6a4821773b9a80a322` | 1,119 reachable commits; concentrated on pulse timing, panic, scene ownership, delayed commands and scheduler reentrancy. |
| [MetaModule](https://github.com/4ms/metamodule/tree/1a94fe61b33ce0b6ba5d69103230c713e1536697) | `1a94fe61b33ce0b6ba5d69103230c713e1536697` | 12,673 commits on main; 14,242 across fetched refs. Eighteen selected fix diffs, ten candidate mechanisms inspected with adjacent code and/or tests. Release ancestry and two unmerged fixes checked separately. |

**Available history is not reviewed history.** This was a targeted investigation, not a complete firmware audit, issue census, or test of the upstream binaries. No upstream test suite or physical module was run. A few source-shaped failure traces were reconstructed as independent synthetic models. The library's own tests execute the new contracts, not those original firmwares.

The search was biased toward micro-robustness: pulse, trigger, clock, reset, queue, scene, command, timer, delay, encoder, key, hold, mapping, catch-up, storage, flash, preset and save. Typical reproducible steps were:

```sh
git log --all --extended-regexp --regexp-ignore-case \
  --grep='pulse|trigger|clock|reset|queue|scene|timer|mapping|catchup|preset|save'
git show <fix-commit> -- <changed-file>
git show <fix-commit>^:<changed-file>
git show <snapshot>:<changed-file>
git merge-base --is-ancestor <fix-commit> <release-tag>
```

Issue status, PR merge status and relevant comments were checked through GitHub's public API. A closed issue alone was not treated as proof of a code fix. Source inclusion in a release establishes ancestry, not successful hardware qualification. The per-entry links pin commits where possible; issue discussions and release pages can evolve after this snapshot.

## Findings and implementation decisions

| Area | New entries | Decision |
| --- | --- | --- |
| Input identity and fan-in | A07–A08 | Board mapping and aggregate route ownership are integration recipes. Aggregate presence has explicit branch-only evidence. |
| Control correctness | C12–C14 | Quantizer membership remains a recipe. Add `PickupLatch` for continuous mapped bounds, explicit rearming and invalid-gap handling. |
| Editing and feedback | D11–D13 | Clock-independent refresh, separate play/edit targets and stable focus identity remain host responsibilities. |
| Event timing | E13–E14 | Add `PulseTimer` and `TriggerDelay`; explicitly document level coalescence and same-deadline mask coalescence. |
| Runtime ownership | F11–F19 | Save side effects, deferred context, callback slot ownership, mute scope, teardown, queue acknowledgement, disconnect and graph invalidation are mostly application recipes. Existing `LatestRequest` supports a tested retry composition. |
| Persistence | G09–G11 | Packed-layout, page-generation and semantic enum checks remain recipes pending a storage format/backend contract. |

Existing E06, E08, E12, F09, F10 and G05 gained sharper source evidence or counterexamples. Broad advice about “safe saves” or “cancel pending work” now identifies the specific actor, lifetime or deadline that caused a failure.

The three new headers are **original MIT implementations**, not ports of upstream algorithms. In particular, the trigger delay uses deadline-mask buckets rather than O_C's per-input shift registers; pickup immediately reports targets outside supplied bounds instead of implementing MetaModule's endpoint jump; the pulse timer exposes two chosen logical policies without Teletype's hardware timers or active-width editing. See [attribution and license boundaries](../ATTRIBUTION.md).

## Counterexamples that constrain reuse

- **Pickup can be impossible.** Restricted continuous bounds can exclude the saved value. Conversely, a snapped destination can accept an effective value outside its raw pre-snap endpoints. Bounds alone do not solve quantized pickup. C13 records the distinction; its upstream reset path also clears inaccessible flags after checking them, so we do not claim reliable load-time notice from that fix alone.
- **A timer is not an output service guarantee.** A late `Trigger` can expire and re-arm internally while the physical output never went low. Neither pulse policy guarantees a new edge for every request. E12/E13 and the tests explicitly preserve this limit.
- **Delayed bitmasks preserve identity, not multiplicity.** Two requests for the same input and due tick become one bit. Tick calls must follow a deliberate cadence; catching up missed calls can create a burst. E14 is unsuitable where every sub-tick event must survive.
- **A queue acknowledgement is not delivery.** F16 marks accepted enqueue; the actual transport can still fail. F17 deliberately discards stale performance messages while disconnected. Durable transfers require a different policy.
- **Clock disappearance is ambiguous.** A long rest, missing pulse, deliberate stop and tempo reduction can look alike without a Run signal. Keeping the last period improves some first notes while adding a cycle of tempo-response lag. There is no universal clock-loss helper in this release.
- **A newer-looking storage record is not necessarily recoverable.** Initial generation, gaps, sequence wrap, format compatibility, checksums and torn writes are separate concerns. G09–G11 do not imply an atomic flash journal.

## Reports kept unresolved

These are leads or counterexamples, not confirmed current defects or claims of resolution. Status is the public API state observed on the research date.

| Report | Status and evidence | What to investigate next |
| --- | --- | --- |
| [O_C #105: forced gate state](https://github.com/mxmxmx/O_C/issues/105) | Open. Source inspection suggests physical-gate history/display can diverge from a forced effective gate; the reported envelope behavior was not reproduced. | Derive effective-level edges and indicators from an explicit policy; replay forced high with physical low and high. |
| [O_C #75: multiplied clock after stop](https://github.com/mxmxmx/O_C/issues/75) | Open; maintainer discusses the internal timer. | Bound remaining subdivisions after loss of parent clock, then test intentional rests and restart phase. |
| [Ansible #37: external clock/reset ratchets](https://github.com/monome/ansible/issues/37) | Open. [PR #71](https://github.com/monome/ansible/pull/71) discusses a possible relation, not a verified resolution of this report. | Reproduce the precise reset/ratchet trace on the intended firmware. |
| [Teletype #244: short delayed pulses](https://github.com/monome/teletype/issues/244) | Open. The later [timer fix](https://github.com/monome/teletype/pull/310) does not establish this older report's resolution without a retest. | Repeat the report with current firmware and measured output service. |
| [MetaModule #533: removing feedback mapping](https://github.com/4ms/metamodule/issues/533) | Open. Concurrent collection mutation is a proposed cause in the report, not a root cause proven here. | Hold a reader at a test barrier while removing a mapping; verify object lifetime before hardware reproduction. |
| [MetaModule #388: empty active knob set](https://github.com/4ms/metamodule/issues/388) | Open; no inspected source-level diagnosis. | Choose whether an emptied bank remains navigable, then test last-entry removal and focus. |

MetaModule A08 and F18 cite commits on `moduleview-jack-improvements` that were **not** ancestors of main or [firmware v2.4.0](https://github.com/4ms/metamodule/releases/tag/firmware-v2.4.0) at inspection. Their source/tests are useful evidence for a candidate design, not a shipped-product claim.

Some apparent bugs were excluded: O_C [#106](https://github.com/mxmxmx/O_C/issues/106) was a calibration-gesture misunderstanding; [#77](https://github.com/mxmxmx/O_C/issues/77) was resolved using existing reset behavior; [#88](https://github.com/mxmxmx/O_C/issues/88) did not establish a systematic storage fault. An O_C change using instantaneous modifier state reduced latency but also bypassed button qualification; without stronger evidence it was not promoted to a general recommendation. MetaModule's I²C fail-safe thresholds, encoder acceleration, hold/repeat feel and clock prediction still need more specific contracts or measurements before becoming reusable code.

## Remaining research gaps

The first pass was broad across manuals and maker accounts but code-heavy toward Mutable Instruments. This pass adds depth in four repositories and their failures; it does not remove selection bias toward published source and searchable commit messages. Closed-source modules, obscure regressions, maker forum discussions, current community O_C forks, electrical tolerances and musician testing remain underrepresented. Continue by testing these contracts on a second hardware family, capturing real failure traces, and investigating a specific unanswered behavior rather than adding unqualified defaults.
