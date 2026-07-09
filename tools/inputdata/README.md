# Inputdata Generator

`tools/inputdata` contains the generator that builds the list of inputdata files required for Github
Continuous Integration tests.  The purpose is to produce the files that should be included in the CI
Docker container, avoiding the need for them to be downloaded during CI.

## What it does

The main entry point is `python3 -m tools.inputdata.generate_inputdata_manifest`. It scans an E3SM checkout, extracts test names from workflow files, runs CIME `create_test` for full-model cases, and writes manifest and provenance files that describe the input files referenced by those tests.

It also performs a best-effort standalone EAMxx scan so the generated manifests can include input paths referenced outside of the full-model CIME flow.

## How it works

The generator uses a small pipeline:

1. `tools.inputdata.lib.workflow_parser` reads `.github/workflows/*.yml` and `.yaml` files from the E3SM tree.
2. It collects full-model test names from `create_test` lines and matrix definitions, and records standalone EAMxx references when present.
3. `tools.inputdata.lib.cime_manifest.run_create_test` invokes `cime/scripts/create_test` for each full-model test in a setup-only mode (`--no-build`, `--no-run`, `--namelists-only`). That creates the case metadata and Buildconf files needed to discover input lists, but it does not compile or execute the test case, and it avoids actually pulling model input data during the run.
4. `tools.inputdata.lib.url_normalize` converts discovered local paths into public inputdata URLs when they point at supported data.
5. `tools.inputdata.lib.inputdata_validation.validate_inputdata_reference` checks the candidate URL with a lightweight remote existence probe without downloading the file. It tries the E3SM public inputdata server first, then the CESM mirror. When both endpoints definitively return not-found responses, the entry is recorded as missing; when the servers cannot be verified cleanly, the entry is kept but marked unverified in provenance.
6. The generator writes the final outputs in a stable order so repeated runs produce the same files.

Some `create_test` invocations can still print `FAIL` during setup. In this workflow, that usually means CIME could not finish case setup for that particular test, so the generator records the failure as a warning and moves on to the next test instead of treating it as a fatal error for the whole manifest run.  Usually, the needed information is discovered despite this.

## Inputs

The command requires:

- `--e3sm-root`: path to the E3SM checkout
- `--test-root`: directory where CIME test cases are created
- `--output-root`: directory where generated artifacts and temporary outputs are written
- `--state-out`, `--files-out`, `--standalone-files-out`, `--missing-files-out`, `--provenance-out`: output files to write

## Outputs

The generator writes five files to the paths passed on the command line:

- `state-out`: workflow and extraction metadata, including the extracted test inventory. This is the snapshot you can inspect to see which workflows and tests were discovered from the E3SM checkout.
- `files-out`: full-model inputdata URLs confirmed present on the E3SM or CESM server. This is the primary manifest consumed by the inputdata automation and other tooling that needs the full-model file list.
- `standalone-files-out`: standalone EAMxx inputdata URLs. This is used for the separate standalone manifest so those paths can be tracked independently from the full-model list.
- `missing-files-out`: relative paths of input files that could not be confirmed on either the E3SM or CESM server. A `WARNING: missing inputdata` line is also printed to stderr for each entry. Pass `--strict` to fail the run when any missing entries are found.
- `provenance-out`: per-URL provenance showing where each input was discovered. This file is useful for tracing a URL back to the workflow, test, and case directory or source scan that produced it. It is supplemental traceability data, not a required input to the generator. For standalone discoveries, `case_dir` is intentionally empty because there is no CIME case directory.

## Environment notes

The generator needs an environment with an E3SM checkout and a working CIME `create_test` script available at `cime/scripts/create_test`. It also expects writable paths for `--test-root` and `--output-root`.

## Related modules

- [generate_inputdata_manifest.py](generate_inputdata_manifest.py)
- [build_pr_metadata.py](build_pr_metadata.py)
- [lib/workflow_parser.py](lib/workflow_parser.py)
- [lib/cime_manifest.py](lib/cime_manifest.py)
- [lib/url_normalize.py](lib/url_normalize.py)
- [lib/inputdata_validation.py](lib/inputdata_validation.py)