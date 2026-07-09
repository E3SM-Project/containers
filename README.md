# E3SM Containers Repository

This repository contains Docker build contexts and automation for container
images used by E3SM CI and related workflows.

## Repository Layout

- `ghci/`: Base GHCI CI container build context.
- `standalone-ghci/`: Standalone GHCI container build context.
- `inputdata/`: Inputdata container build context and manifest files.
- `e3sm-diags-test-data/`: E3SM diags test-data image build context.
- `tools/inputdata/`: Inputdata manifest generation and support utilities.
- `.github/workflows/`: GitHub Actions workflows for build/publish and
  manifest automation.

## Workflow Summary

All workflows live in `.github/workflows`.

### `ghci.yaml`

- Purpose: Build the `ghcr.io/<org>/<repo>-ghci` image.
- Triggers:
  - `pull_request` to `main` when `ghci/**` or workflow file changes.
  - `push` to `main` on same paths.
  - tags matching `ghci-*`.
- Behavior:
  - Always builds on PRs and pushes.
  - Pushes image only when event is not `pull_request`.

### `standalone-ghci.yaml`

- Purpose: Build the `ghcr.io/<org>/<repo>-standalone-ghci` image.
- Triggers:
  - `pull_request` to `main` when `standalone-ghci/**` or workflow file
    changes.
  - `push` to `main` on same paths.
  - tags matching `standalone-ghci-*`.
- Behavior:
  - Uses `ubuntu-22.04-arm` runner matrix.
  - Pushes image only when event is not `pull_request`.

### `e3sm-diags-test-data.yaml`

- Purpose: Build the `ghcr.io/<org>/<repo>-e3sm-diags-test-data` image.
- Triggers:
  - `merge_group` to `main`.
  - `pull_request` to `main` when `e3sm-diags-test-data/**` or workflow file
    changes.
  - `push` to `main` on same paths.
  - tags matching `e3sm-diags-test-data-*`.
- Behavior:
  - Pushes image only when event is not `pull_request`.

### `inputdata.yaml`

- Purpose: Build inputdata images from manifest files in `inputdata/`.
- Triggers:
  - `pull_request` to `main` when `inputdata/**` or workflow file changes.
  - `push` to `main` on same paths.
  - tags matching `inputdata-*`.
- Behavior:
  - Matrix builds two variants:
    - `files` from `inputdata/files.txt`.
    - `files-standalone` from `inputdata/files-standalone.txt`.
  - Pushes images only when event is not `pull_request`.

### `update-inputdata-manifest.yml`

- Purpose: Regenerate inputdata manifests from E3SM workflows and open a PR
  when generated outputs change.
- Triggers:
  - Weekly schedule (`cron: 0 12 * * 1`).
  - Manual `workflow_dispatch`.
- Behavior:
  - Checks out this repository and `E3SM-Project/E3SM` at `master`.
  - Runs `python3 -m tools.inputdata.generate_inputdata_manifest`.
  - Compares managed files:
    - `inputdata/files.txt`
    - `inputdata/files-standalone.txt`
    - `inputdata/files-missing.txt`
    - `inputdata/e3sm-workflow-state.json`
    - `inputdata/provenance.json`
  - If no changes: exits without opening a PR.
  - If changes exist: uses `peter-evans/create-pull-request` to open a real
    PR with generated metadata.

## How Workflows Fit Together

1. `update-inputdata-manifest.yml` is the source-of-truth updater for
   inputdata manifest content.
2. When it opens a PR that modifies files under `inputdata/`,
   `inputdata.yaml` runs automatically on that PR and validates container builds
   without pushing images.
3. After the PR is reviewed and merged to `main`, `inputdata.yaml` runs again
   on the `push` event and publishes updated inputdata images to GHCR.
4. `ghci.yaml`, `standalone-ghci.yaml`, and `e3sm-diags-test-data.yaml` are
   independent image pipelines and do not depend on inputdata-manifest updates.

In short: one workflow updates inputdata manifests, a different workflow builds
and publishes inputdata images from those manifests.

## Common Trigger Pattern

Most image workflows follow the same model:

- Build on PRs for validation.
- Publish on `push` to `main` or on release-style tags.
- Scope execution with `paths` filters to avoid unrelated builds.

## For New Contributors

If you are updating manifest generation logic:

1. Change code under `tools/inputdata/`.
2. Run the generator locally if needed.
3. Use `workflow_dispatch` on `update-inputdata-manifest.yml` to test the
   automation path.

If you are updating container images directly:

1. Modify the corresponding directory (`ghci/`, `standalone-ghci/`,
   `inputdata/`, or `e3sm-diags-test-data/`).
2. Open a PR and confirm the matching workflow build succeeds.
3. Merge to `main` to publish new images.