# Optional measured evidence

The normal build tests portable contracts with synthetic traces and reference
models. It does not download recordings or operate hardware. Reports from the
Daisy campaign remain in `bench/daisy/measured/daisy/`; the larger, lossless trace
files are separate release assets. Failed recordings remain failures.

## Download and replay

```sh
python3 tools/fetch_evidence.py --list
python3 tools/fetch_evidence.py
python3 tools/fetch_evidence.py --check
cmake -S . -B build-measured -DCMAKE_BUILD_TYPE=Release \
  -DEURORACK_PATTERNS_BUILD_BENCH_TESTS=ON \
  -DEURORACK_PATTERNS_BUILD_MEASURED_TESTS=ON
cmake --build build-measured --config Release --parallel
ctest --test-dir build-measured -C Release --output-on-failure
```

The full corpus is about 2 GB. `--campaign NAME` selects one listed campaign;
repeat it to select several. Full measured tests require the complete manifest.
For an offline machine, download the same release archives elsewhere, then use
`--from-dir ARCHIVE_DIRECTORY`. Downloaded files are ignored by Git. They can be
removed and restored without changing the reports or library.

The [manifest](../bench/daisy/measured/manifest.json) pins archive sizes and SHA-256
digests, plus the exact size and hash of every extracted trace. The downloader
verifies both layers, rejects unsafe paths and links, and installs only verified
files. The published archives and manifest still name members under the
historical `tests/measured/` prefix; the downloader installs them under
`bench/daisy/measured/` without altering the immutable release assets. Configuration fails if measured tests are requested with missing or
changed evidence; missing data never silently turns a measured test into a pass.

## Provenance and development history

The [evidence release](https://github.com/lylepmills/eurorack-patterns/releases/tag/evidence-daisy-2026-10-20)
preserves the original development history as a split Git bundle alongside the
trace archives. Its source head is
`077d816dd94322a421468d98086fb14601c2ecbd`. Reports keep the firmware commits,
build identifiers, acceptance limits and raw hashes recorded during acquisition.
Consolidating the integration history does not relabel those measurements as
results of the new commits.

To recover the original source revisions, download the `source-history.bundle.part*`
files and `source-history.json` from that release. Concatenate the parts in the
listed order, verify their hashes and the complete bundle hash, then run:

```sh
git clone --branch codex/daisy-clock-validation source-history.bundle evidence-history
git -C evidence-history checkout FIRMWARE_COMMIT_FROM_REPORT
```

This archive is a research record, not another supported library release. It
includes intermediate firmware and rejected experiments. The concise validation
guide is the entry point for reusable lessons; chronological records explain the
individual experiments. Native instrument files remain separately retained by
hash where the reports say so; an exported trace is not a native voltage capture.

## Test boundaries

| Build | Purpose | Evidence download |
| --- | --- | --- |
| Default | Portable components, application examples and downloader integrity | None |
| `EURORACK_PATTERNS_BUILD_BENCH_TESTS=ON` | Host simulations of the optional Daisy adapter and capture tools | None |
| Both bench and measured options | Replay retained measurements and assert their recorded pass/fail verdicts | Required |

All three configurations are host tests. Neither a replay nor a firmware link
build is a fresh hardware measurement. Run the complete measured suite when
changing interpretation of captured data, and before publishing a validation
release. The separate **Measured evidence** workflow runs this suite on demand
and on pull requests that change components, bench tools, tests or build rules;
the normal CI matrix runs portable and synthetic adapter checks on every change.
