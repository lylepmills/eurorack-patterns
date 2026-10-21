# Publishing a release

Release tags and assets are permanent dependency inputs. Never move or reuse a
published version to fix code or documentation; publish a new version. The API is
pre-1.0: describe behavioral/interface changes explicitly and retain the existing
CMake `SameMinorVersion` package policy. Patch releases preserve public contracts.

1. Work on a branch. Update the CMake version and changelog. Preserve attribution
   and inspect any added dependency's exact revision/license.
2. Audit the complete diff, new files, commit messages, release notes and build
   output for private project names, local paths, internal plans and unsupported
   claims. Use generic examples. Do not put a private-name denylist in this repo.
   Run `python3 tools/check_public.py`; an optional local `EP_PRIVATE_TERMS`
   newline-separated list can catch names without publishing them. The checker
   is an aid, not a confidentiality or provenance guarantee.
3. Run portable and synthetic bench checks, then the complete measured suite
   with the [verified evidence download](evidence.md). Require the **Measured
   evidence** workflow for changes to evidence interpretation or validation
   releases. Also run Release host tests with sanitizers, installed consumers, ARM header smoke,
   the Pico link build, and `python3 tools/render_traces.py
   build/example_behavior_traces --check`. See CI for the exact commands. No
   hardware qualification follows from a successful cross-build.
4. Push the audited branch and require every Host tests workflow job to pass on
   the exact candidate SHA. Land it on main without unrelated changes; verify
   main's checks as well. Review generated illustrations and local doc links.
5. Verify repository release immutability is enabled before publication. Create
   a draft release at the tested commit, stage all intended assets, and review
   its notes. Include the full commit ID, a copyable dependency pin, test results,
   compatibility changes and remaining evidence limits. Do not claim a physical
   measurement unless the trace and acquisition method are available.
6. Publish the draft and verify the release is marked immutable, its tag resolves
   to the tested SHA, and the source archive matches that tree. Any later fix gets
   a new version. Update main's README pin to the published commit; that follow-up
   documentation commit does not change the release.

GitHub documents [immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
Contributor issues should ask for a bounded public result and acceptance checks.
A maintainer reviews source claims, API contracts and evidence before merging;
there is no promised response time or implied endorsement by cited makers.

Before merging a long exploratory branch, consolidate it into coherent, tested
changes. Archive exact historical source revisions alongside evidence before
retiring development branches; old measured build identities must remain
recoverable. Verify download URLs and asset hashes before relying on the archive.
Keep evidence-only releases separate from the latest library version. Never
rewrite an existing library release to make history shorter.
