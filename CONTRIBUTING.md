# Contributing

## Public scope

Describe reusable behavior in product-neutral terms. Do not name or describe private or unreleased projects, internal repositories, roadmaps, or implementation plans in code, tests, documentation, commit messages, release notes, or public build output. Use synthetic, generic examples. Attribution to publicly documented third-party work and required copyright/license notices must remain intact.

## Contributions

Start with an [open contribution task](https://github.com/lylepmills/eurorack-patterns/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22help%20wanted%22), or use the [issue forms](https://github.com/lylepmills/eurorack-patterns/issues/new/choose) for a reproducible bug, source correction or measured trace. Small counterexamples and source corrections are as useful as new components. Discuss a new public API before implementing it. A maintainer reviews evidence and contracts; no response-time commitment is implied.

Contributions should keep each pattern small, specific, and traceable. For a catalog entry, give one observed behavior, its maker/product/version, a stable primary source link, a proposed reusable idea, a tradeoff, and a concrete check. Distinguish what the source demonstrates from what you infer. If a source is a manual or maker account, label it as such; do not describe it as inspected code. Add an ID only after checking that the idea is not already covered. After adding or renaming an entry, run `python3 tools/catalog_index.py` to refresh the catalog's index table; CI checks that it is current.

For library code, state the contract: units and time base, startup state, invalid-input behavior, bounds and overflow, and who owns calls across threads or interrupts. Add focused host tests for the intended mechanism and failure boundary. Mark fixtures as **synthetic** when generated or simulated; mark **measured** traces with the device, firmware, acquisition setup, units, date, and relevant calibration. A host test does not establish electrical behavior, real-time timing, or hardware qualification. Keep personal data, serial numbers, customer patches, and private repository content out of test traces.

Contributed original code and writing are submitted under this repository's MIT license, with no blanket contributor license agreement. Do not paste third-party implementation text into a new file merely because a source is linked. If code is adapted or copied, document the exact source file and revision, review its per-file license, and preserve all required notices before submitting. If provenance or reuse permission is unclear, contribute a linked design note and test idea instead of copied code.

Changes reach `main` only through a pull request: a repository ruleset refuses direct pushes, force pushes and deletion of `main`, and requires the Host tests jobs to pass before a merge. Before submitting, run the repository's documented tests, inspect the diff for generated files or unintended private paths, and update [coverage](docs/coverage.md) when a pattern gains an implementation or stronger validation. Claims of hardware validation need actual measurements or a reproducible bench procedure with results.

For bug-history research, inspect the patch and surrounding callers, pin the revision, and distinguish merged/released behavior from branch proposals and unresolved reports. A closed issue does not by itself establish a fix; an upstream test read during research is not a test executed here. Include a counterexample or failure boundary and an independent oracle where practical. The [second-pass methodology](docs/research-pass-2.md) and [validation guide](docs/validation.md) provide examples and measured-trace metadata requirements.

## Keep investigations bounded

Before a hardware campaign, name the reusable contract or product decision it
can change, list a finite set of cases, and set acceptance and stopping criteria.
Record actual coverage and retain failures. Separate a reusable lesson from a
fixture's unresolved physical diagnosis; resolving every anomaly is not a
prerequisite for a useful library. Put long apparatus histories in bench or
investigation records and link a concise conclusion from the validation guide.

## Readable changes and history

Use a small number of coherent commits that explain the problem, final behavior,
tests and limitations. Include the relevant tests and documentation with a
change. Consolidate exploratory fixups before merging, while preserving any
original source revision needed to reproduce a measurement. Do not rewrite
published release tags or relabel old evidence with a new source identity.

Keep large recordings outside ordinary Git history. Retain reviewable reports,
an immutable download and hashes for every payload; the [evidence guide](docs/evidence.md)
shows the current arrangement. A shorter history must not erase counterexamples
or turn a failed measurement into a passing one.
