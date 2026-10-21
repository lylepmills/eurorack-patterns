# Repository tools

Most users need only the library and application examples. These tools support
documentation, optional recorded-evidence replay, or the historical Daisy bench.

| Tool or family | Purpose |
| --- | --- |
| `check_public.py` | Review local links, private paths and commit-message content; optional private terms stay local |
| `render_traces.py` | Recreate the README's explicitly synthetic illustrations |
| `fetch_evidence.py` | Download and verify optional measured traces; `--list` and `--check` are offline |
| `export_daisy_*` | Produce public, allowlisted reports and lossless traces from saved captures |
| `review_daisy_buttons.py`, `review_daisy_jacks.py`, `review_daisy_jack_*` | Check observed behavior and independent electrical evidence against declared acceptance limits |
| `daisy_scope.py`, `inspect_daisy_timing.py` | Shared timing and capture-coverage checks |
| `inspect_daisy_clock*`, `inspect_daisy_reference.py`, `review_daisy_clock_reference.py`, `review_daisy_dsp.py` | Replay diagnostics for the closed clock/workload investigation |

Start with the [validation guide](../docs/validation.md), then use the
[Daisy code map](../examples/daisy/README.md) or
[evidence instructions](../docs/evidence.md) for the relevant task. Capture
orchestration lives under `examples/daisy/`; offline review modules are also
exercised by host tests. Some exporters need the optional instrument SDK to read
native files. A successful replay confirms the recorded verdict, including an
expected failure; it is not a new physical measurement.
