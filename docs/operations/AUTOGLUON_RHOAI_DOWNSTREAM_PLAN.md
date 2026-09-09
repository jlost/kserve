# AutoGluon RHOAI Downstream Packaging Plan

**Status:** implementation-ready for `rhoai-3.6-ea.2`
**Updated:** 2026-09-09
**Implementation:** `red-hat-data-services/kserve` `main` and active
`rhoai-[0-9].[0-9]**` release branches

## 1. Decision and contract

RHOAI packaging policy stays downstream-owned. The public AutoGluon project
and lock remain ODH-owned; RHOAI uses a standalone project file:

```text
python/autogluonserver/pyproject.rhoai.toml
```

The standalone project is the only human-maintained RHOAI dependency input.
The generator produces exactly two derived files:

```text
python/autogluonserver/uv.rhoai.lock
python/autogluonserver/autogluon-all-requirements.txt
```

Normal ownership flow remains:

```text
KServe main source + RHOAI project
        → generator bot commit
        → main-to-release sync
        → release build
```

Regeneration is eventually consistent and branch-aware. It regenerates after
relevant `main` pushes and converges `rhoai-[0-9].[0-9]**` branches after
merged release PRs that touch relevant files; direct release-branch pushes do
not trigger it. This follows the
event-handling pattern in
[WVA #236](https://github.com/red-hat-data-services/workload-variant-autoscaler/pull/236/changes).

Generated artifacts are build inputs. Therefore:

- a generated bot commit is the authoritative converged revision;
- a source-only direct release change must include matching generated files
  and pass `--check`; and
- an intermediate source-triggered build must never be promoted as the
  release result.

Supporting source-only release changes without that restriction requires a
separate Konflux trigger/gating change. It is not part of this KServe workflow
change.

## 2. Ownership and branch flow

ODH-to-KServe-main sync preserves all RHOAI-owned paths. KServe-main-to-release
sync copies AutoGluon files normally. Only `.tekton/**` and
`kserve-module/prefetched-manifests-rhoai/**` remain release-owned exceptions.

```text
opendatahub-io/kserve:release-v0.17
        │ ODH → RHOAI main sync
        ▼
red-hat-data-services/kserve:main
        │ push to main → regeneration bot commit
        ▼
red-hat-data-services/kserve:rhoai-3.6-ea.2
        │ main → release sync or release-aware repair
        ▼
AutoGluon Konflux release build
```

`main` remains source of truth. Release regeneration repairs convergence; it
does not create a second release-specific packaging policy.

## 3. File ownership

### ODH-owned public inputs

```text
python/autogluonserver/pyproject.toml
python/autogluonserver/uv.lock
python/autogluonserver/Makefile
python/autogluonserver/README.md
python/autogluonserver/autogluonserver/**
python/autogluonserver/tests/**
```

These must resolve from public package indexes without RHOAI package policy.

### RHOAI-owned files

```text
python/autogluonserver/pyproject.rhoai.toml
python/autogluonserver/uv.rhoai.lock
python/autogluonserver/autogluon-all-requirements.txt
python/autogluonserver/README.rhoai.md
hack/rhoai/generate_autogluon.py
hack/rhoai/test_generate_autogluon.py
.github/workflows/autogluon-rhoai-update.yml
Dockerfiles/autogluon.Dockerfile.konflux
```

The first three files are copied from `main` to release branches by normal
sync. The release-aware workflow may update only the two generated files.

## 4. Generator contract

Command:

```bash
uv run hack/rhoai/generate_autogluon.py
```

`--check` generates into a temporary workspace, compares both outputs, and
never modifies the working tree. `--project` and `--output-dir` remain
available for alternate projects and tests; omitted options use the repository
root and canonical AutoGluon paths.

Generator requirements:

1. Validate the standalone project structure, Python range, setuptools build
   backend, `rhoai-build` group, local package sources, and five patched
   AutoGluon AIPCC mappings.
2. Require exactly one credential-free default AIPCC index.
3. Copy `python/kserve`, `python/storage`, and `python/autogluonserver` into
   a temporary tree with standard `pyproject.toml`/`uv.lock` names.
4. Reuse `uv.rhoai.lock` when present; bootstrap without it when absent.
5. Run `uv lock`, `uv lock --check`, then one locked `uv export`.
6. Validate RHOAI artifact hosts, Konflux platform coverage, hashes, and
   absence of public PyPI artifact URLs.
7. Prefix the exported body with exactly one AIPCC `--index-url`.
8. Write both outputs atomically. Failed generation leaves existing outputs
   untouched.

The generator must remain deterministic for identical project and local
package inputs.

Generator contract tests run with:

```bash
uv run hack/rhoai/test_generate_autogluon.py
```

They cover accepted checked-in inputs, credential rejection, artifact-host
validation, hash enforcement, and stale-output detection without modifying the
working tree in check mode.

## 5. Release-aware regeneration workflow

Modify `.github/workflows/autogluon-rhoai-update.yml` to support four event
classes. Pull requests run read-only generator-contract tests; relevant
`main` pushes and only merged release PRs that touch relevant files can
regenerate or push artifacts. An optional manual dispatch uses the same
generic generation path.

```yaml
on:
  push:
    branches:
      - main
    paths:
      - python/autogluonserver/pyproject.rhoai.toml
      - python/autogluonserver/uv.rhoai.lock
      - python/autogluonserver/autogluon-all-requirements.txt
      - python/kserve/pyproject.toml
      - python/storage/pyproject.toml
      - hack/rhoai/*.py
      - .github/workflows/autogluon-rhoai-update.yml

  pull_request_target:
    types: [closed]
    branches: ['rhoai-[0-9].[0-9]**']
    paths:
      - python/autogluonserver/pyproject.rhoai.toml
      - python/autogluonserver/uv.rhoai.lock
      - python/autogluonserver/autogluon-all-requirements.txt
      - python/kserve/pyproject.toml
      - python/storage/pyproject.toml
      - hack/rhoai/*.py
      - .github/workflows/autogluon-rhoai-update.yml

  pull_request:
    paths:
      - python/autogluonserver/pyproject.rhoai.toml
      - python/autogluonserver/uv.rhoai.lock
      - python/autogluonserver/autogluon-all-requirements.txt
      - python/kserve/pyproject.toml
      - python/storage/pyproject.toml
      - hack/rhoai/*.py
      - .github/workflows/autogluon-rhoai-update.yml

  workflow_dispatch:
```

The `main` push and merged release-PR events use the same relevant-file path
set as the read-only pull-request test. A generated-only bot push therefore
reruns the workflow but exits successfully without a second commit because the
outputs are already current. Release generation is automatically available
from merged `pull_request_target` events targeting
`rhoai-[0-9].[0-9]**`; direct pushes to those branches do not start this
workflow. `workflow_dispatch` is retained as an operator recovery option, but
follows the same generation job and has no dispatch-specific branch, approval,
or token logic. The read-only `pull_request` test includes generated outputs
so stale artifacts fail review without receiving write credentials.

### Event behavior

| Event | Target branch | Checkout revision | Condition |
| --- | --- | --- | --- |
| `push` on `main` | `github.ref_name` | `github.sha` | relevant paths |
| merged `pull_request_target` | PR base branch | `merge_commit_sha` | merged + relevant paths |
| `pull_request` | no branch write | PR merge ref | read-only tests only |
| `workflow_dispatch` | selected branch | `github.sha` | generic generation path |

For `pull_request_target`:

- use the workflow from the trusted target branch;
- skip unless `github.event.pull_request.merged == true`;
- check out the merge commit, never the untrusted PR head; and
- push only to the PR base branch.

Use a branch-specific concurrency key:

```yaml
concurrency:
  group: autogluon-rhoai-${{ github.event_name == 'pull_request_target' && github.event.pull_request.base.ref || github.ref_name }}
  cancel-in-progress: false
```

For `pull_request`:

- run only the generator-contract tests;
- grant no write permission or repository secret;
- check out with `persist-credentials: false`; and
- exclude the generation job explicitly so PRs cannot create App tokens or
  push branches; and
- install only the workflow's trusted `uv` bootstrap version, then let the
  generator reject a mismatch with the checked-out `kserve-deps.env`.

The generation job must:

1. Create the existing repository-scoped RHDS CI GitHub App token.
2. Resolve target branch and checkout revision from the event type.
3. Check out the full target history and create a local target branch.
4. Install Python 3.12 and the `UV_VERSION` pinned in `kserve-deps.env`.
5. Run the generator.
6. Stage only `uv.rhoai.lock` and
   `autogluon-all-requirements.txt`.
7. Exit successfully without a commit when outputs are current.
8. Commit with:

   ```text
   chore(autogluon): regenerate RHOAI artifacts
   ```

9. Push using `HEAD:refs/heads/$TARGET_BRANCH`.
10. On push rejection, fetch the latest target branch, reset the disposable
    runner workspace to it, rerun generation, and retry up to five times.

Never rebase stale generated output without rerunning the generator.

The workflow uses the existing pinned actions and secrets:

- `actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1`;
- `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5`;
- `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065`;
- `RHDS_CI_APP_CLIENT_ID`; and
- `RHDS_CI_APP_PRIVATE_KEY`.

The App token must request only `contents: write`. Checkout must use
`persist-credentials: false`; the token is supplied only as an ephemeral Git
fetch/push authorization header and never stored in `.git/config`.

## 6. Build and promotion semantics

Existing Konflux PipelineRuns continue consuming the stable
`autogluon-all-requirements.txt` filename. No Konflux Central change is
required for the supported flow:

- implementation PR includes current generated artifacts;
- main regeneration updates outputs after every relevant-file push;
- main-to-release sync copies source and current outputs; and
- merged release-PR regeneration repairs any branch drift.

Separate source and generated commits may cause redundant builds under the
existing broad release trigger. The generated-artifact revision is the valid
revision for promotion. A source-only release change that lacks matching
generated files is not a valid release change and must not be promoted.

If product requirements later demand source-only release changes, add a
Konflux change that suppresses input-only builds and triggers the release build
from the generated bot commit. Do not solve that ordering problem by adding
more GitHub retry logic.

## 7. Dockerfile contract

`Dockerfiles/autogluon.Dockerfile.konflux` must:

- copy the standalone RHOAI project with the AutoGluon source;
- replace in-image `pyproject.toml` with `pyproject.rhoai.toml`;
- install the generated requirements with `--require-hashes`;
- install local `kserve`, `storage`, and `autogluonserver` packages with
  `--no-deps`; and
- retain the existing base image, license generation, labels, and four-platform
  build contract.

No second dependency resolver may run in the Dockerfile.

## 8. Synchronization configuration

ODH-to-KServe-main sync must ignore all RHOAI-owned files listed in §3,
including the workflow, generator, generator tests, Dockerfile, standalone
project, and two generated outputs.

KServe-main-to-release sync must ignore only:

```text
.tekton/*
kserve-module/prefetched-manifests-rhoai/**
```

AutoGluon files must flow from `main` to active `rhoai-[0-9].[0-9]**` branches.
WVA and model-controller remain owners of their prefetched-manifest subtrees.

## 9. Rollout

1. Update this plan and the KServe workflow together.
2. Verify generator output and `--check` locally with the `UV_VERSION` pinned
   in `kserve-deps.env`.
3. Validate workflow YAML and inspect event expressions.
4. Run the existing AutoGluon PR build.
5. Merge the KServe-main implementation with generated artifacts included.
6. Confirm one regeneration bot commit on `main` after a relevant change, or a
   no-op when outputs are current.
7. Test a controlled release-branch change in a non-production branch:
   verify merged-PR handling, branch-local output commit, direct-push
   non-triggering, and no regeneration loop.
8. Confirm main-to-release sync preserves generated files and release-owned
   manifests.
9. Confirm the release build uses the generated-artifact revision before
   promotion.

### Post-merge validation (required)

After implementation merge, validate both the workflow and resulting
artifacts before treating the change as released:

1. Inspect the `autogluon-rhoai-update.yml` run for the merge commit. Confirm
   generator-contract tests pass, generation job has the expected event/branch,
   and no PR test job received repository secrets.
2. Confirm exactly one bot commit was created when artifacts changed, or a
   successful no-op when they were already current. Confirm bot commit changes
   only `uv.rhoai.lock` and `autogluon-all-requirements.txt`.
3. At the bot commit, run:

   ```bash
   uv run hack/rhoai/generate_autogluon.py --check
   ```

   Require success and a clean diff for both generated files.
4. Confirm the generated requirements contain hashes, exactly one AIPCC index,
   no public PyPI artifact URLs, and the four required platform markers.
5. Confirm the subsequent Konflux build uses the bot commit, then promote only
   that generated-artifact revision.
6. Repeat steps 1–5 for a controlled `rhoai-[0-9].[0-9]**` branch change,
   covering a merged relevant release PR and confirming that a direct
   release-branch push does not trigger this workflow.

## 10. Acceptance criteria

### Workflow

- Relevant pull requests run read-only generator-contract tests.
- Pull-request test jobs cannot create App tokens or push branches.
- Relevant-file pushes on `main` start the workflow and regenerate the two
  outputs when they are stale.
- `workflow_dispatch` uses the same generation job as automatic events, without
  a dispatch-specific code path or approval gate.
- Merged release PR runs against its merge SHA, not PR head.
- Closed, unmerged release PR does nothing.
- Merged relevant-file release PRs targeting `rhoai-[0-9].[0-9]**` start the
  workflow.
- Direct push to `rhoai-[0-9].[0-9]**` does not start this workflow.
- Generated-only bot push produces a successful no-op, not a second commit.
- Concurrent updates rerun generation from latest branch state.
- Bot commit stages no file outside the two generated outputs.

### Generator and build

- `--check` detects missing or stale outputs.
- Repeated generation is byte-for-byte stable.
- `uv lock --check` and locked export succeed.
- Requirements contain hashes and exactly one AIPCC index directive.
- Dockerfile installs the same generated graph without re-resolution.
- Four-platform PR and release builds consume the generated requirements.
- No source-only release change is promoted with stale generated artifacts.

### Ownership

- ODH sync cannot overwrite RHOAI-owned paths.
- Main-to-release sync copies AutoGluon files.
- Main-to-release sync preserves `.tekton/**` and prefetched manifests.
- No RHOAI packaging policy enters ODH.

## 11. Out of scope

- Changing Konflux trigger semantics or adding a new release pipeline.
- Supporting source-only release changes without generated artifacts.
- Moving RHOAI package policy into ODH.
- Private package credentials in generated files.
- Changing AutoGluon runtime code or public dependency policy.
- Changing WVA or model-controller manifest ownership.
