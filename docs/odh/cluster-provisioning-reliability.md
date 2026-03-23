# Cluster Provisioning Reliability for Model Serving CI

This document investigates the cluster provisioning failure rate in model serving CI (kserve, odh-model-controller) and evaluates alternative provisioning methods. It supports [Section 1 of the CI stability spike](ci-stability-spike.md#1-cluster-provisioning-reliability).

## Problem Statement

Of 138 FAILURE builds across 5 established E2E job types (3 kserve, 2 omc), **74 (54%) failed because the Hypershift cluster was never created**. These are binary failures -- HTTP 400 from the Hypershift API, or timeout waiting for `hostedclusters` / `clusterversions` to become ready. Tests never start. No test-level mitigation (JUnit XML, `--maxfail`, health checks, managed resources) helps when there is no cluster.

This single failure category accounts for more failures than all other categories combined and is the primary driver of the 37% overall success rate.

Source: [collect_ci_timing.py](collect_ci_timing.py) with log-based classification against [490 recent Prow builds](ci_timing_data.csv).

## Current Provisioning Method

Model serving E2E jobs use `hypershift-hostedcluster-workflow` with `cluster_profile: aws-opendatahub`:

```yaml
# From opendatahub-io-kserve-master.yaml in openshift/release
steps:
  cluster_profile: aws-opendatahub
  workflow: hypershift-hostedcluster-workflow
  env:
    HYPERSHIFT_NODE_COUNT: "3"
    BASE_DOMAIN: openshift-ci-aws.rhaiseng.com
```

Each job:
1. Acquires a Boskos lease from the `aws-opendatahub` pool (shared AWS credentials)
2. Creates a new Hypershift hosted cluster on-demand (~11-13 min median when successful)
3. Runs tests
4. Destroys the hosted cluster

The Hypershift hosted cluster has a **different control plane topology** from standard IPI clusters: the control plane runs on the management cluster, not within the provisioned cluster itself. This has caused test compatibility issues in other ODH repos (see [HyperShift History in ODH](#hypershift-history-in-odh)).

**Critical question: is the 54% failure rate inherent to HyperShift, or caused by Boskos pool contention?** The Konflux EaaS path (see [Konflux EaaS Path](#konflux-eaas-path-existing-alternative)) also uses HyperShift on AWS but provisions through completely different infrastructure -- no Boskos, no shared `aws-opendatahub` pool. If EaaS provisioning is reliable, the problem is pool contention, not HyperShift itself.

## Boskos Pool Contention

The `aws-opendatahub` Boskos pool is shared across **47 AWS E2E jobs from 26 repositories** (per the [ODH strategic plan](https://docs.google.com/document/d/1IM4YWMXsV3gxF0xZ8CxbxVJTmmezpXCLt5ISpApqh2M/edit), Appendix E). The strategic plan found that success rates for the ODH operator E2E suite vary by **21 percentage points** based on time of day:

- Best: 5-7 AM UTC at 70.8% success
- Worst: 9 PM UTC at 49.7% success

This variance represents a natural experiment: same tests, same code, same configuration -- only the infrastructure load changes. Our model serving jobs compete in the same pool, and likely experience similar contention-driven failure patterns.

**Open question:** Does our provisioning failure rate correlate with time of day? The raw data in [ci_timing_data.csv](ci_timing_data.csv) contains timestamps that could answer this.

## Ecosystem Awareness (from Slack)

This problem is well-known across the ODH ecosystem and OpenShift CI more broadly. Key findings from Slack channels:

**`#wg-odh-e2e-stability` (March 2026):** The ODH operator team (mstratto) has comprehensive CI observability tooling ([openshift-ci-observability](https://gitlab.cee.redhat.com/mstratto/openshift-ci-observability)) that shows:
- **ODH operator 7-day success rate: 67.5%** (1509/2234 builds) -- even after migrating to Hive cluster pools
- **`clusterClaimStep` is their #1 failure**: 289 failures in 7 days from pool exhaustion. Image build (227) and source checkout (180) failures are #2 and #3.
- **Tests themselves pass at 99.8%** when the cluster is available and builds succeed -- confirming that the bottleneck is infrastructure, not test quality
- **Lease exhaustion (HyperShift)**: 263 failures from a remaining HyperShift job (since removed)
- Active levers being investigated: pool right-sizing, reducing claim timeout from 2h to 30-45min (2h timeout ties up a Prow build pod for the duration), and a build cluster migration ([openshift/release#76260](https://github.com/openshift/release/pull/76260), [openshift/release#76403](https://github.com/openshift/release/pull/76403))

**`#forum-ocp-testplatform` (ongoing):** Boskos pool management is described as "blindly feeling around in the dark" by TRT members. AWS account quotas are not rationally calculated -- they are empirically discovered by raising limits until failures appear, then backing down. Nobody is actively managing capacity. Multiple teams (model-registry, cluster-control-plane-machine-set-operator) have reported the same `aws-opendatahub` cluster profile issues.

**`#trt-alert` (March 2026):** AWS lease pool exhaustion is blocking even OCP nightly payload releases. The `aggregated-hypershift-ovn-conformance-4.22` blocking job was rejected due to "CI infrastructure -- AWS lease pool exhaustion, no code fix needed." This confirms the problem is systemic across OpenShift CI, not ODH-specific.

**Implication for model serving:** The ODH operator team's 67.5% success rate with Hive pools is substantially better than our 37% with HyperShift/Boskos, but pool exhaustion remains a problem. Any provisioning method that draws from a shared Prow-managed pool is subject to the same capacity constraints. This strengthens the case for Konflux EaaS (Option 3), which uses entirely separate infrastructure.

## Konflux EaaS Path (existing alternative)

Model serving E2E tests are **already configured** in Konflux via [odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central). The Konflux pipelines use a completely different provisioning path that also creates HyperShift clusters but through separate infrastructure:

| Aspect | Prow (current) | Konflux EaaS |
|---|---|---|
| Provisioning mechanism | `hypershift-hostedcluster-workflow` | `eaas-create-ephemeral-cluster-hypershift-aws` |
| Credential management | Boskos leases from `aws-opendatahub` pool | Konflux manages credentials via `SpaceRequest` (no Boskos) |
| AWS account | Shared across 47 jobs from 26 repos | Konflux-managed (separate from Prow) |
| HyperShift management cluster | Prow `build01` | Konflux infrastructure |
| Cluster topology | HyperShift hosted control plane | HyperShift hosted control plane (same) |
| Test runner | `test/scripts/openshift-ci/run-e2e-tests.sh` | Same script, invoked from Tekton |
| Provisioning failure rate | **54%** (measured) | **~0%** (30/30 cluster provisions: omc + kserve) |

The key pipelines:
- kserve: `integration-tests/kserve/pr-group-testing-pipeline.yaml` -- provisions parallel EaaS clusters for graph, raw, predictor, and LLM tests
- omc: `integration-tests/odh-model-controller/pr-test-pipelinerun.yaml` -- provisions EaaS clusters for kserve and llmisvc tests

Both paths use the same test runner scripts and test code. The only difference is how the cluster is provisioned and who manages the AWS credentials.

**EaaS provisioning success rate (measured):** 30/30 cluster provisions succeeded across both repos:
- **omc:** 9/9 ITS runs (18 provisions at 2-parallel, Feb 9 - Mar 18 2026), consistent 45-53 min durations
- **kserve:** 3/3 group test runs on `release-v0.15` (12 provisions at 4-parallel, Feb 23 - Mar 10 2026), 1h00m-1h55m durations
- 2 additional kserve group test runs failed due to pipeline/config errors (not provisioning): 4 min on `release-v0.15`, instant on `release-v0.17`

Zero provisioning failures at both 2-parallel and 4-parallel cluster scale. This conclusively confirms Boskos contention as the root cause. Full analysis: [konflux-eaas-feasibility.md](konflux-eaas-feasibility.md).

## HyperShift History in ODH

The ODH operator team's experience with HyperShift is documented in the strategic plan (Appendix H):

| Date | PR | Action | Result |
|---|---|---|---|
| Aug 2025 | [#68045](https://github.com/openshift/release/pull/68045) | Switched main and stable-2.x from GCP IPI to AWS HyperShift | Merged Oct 8 |
| Oct 2025 | [#70167](https://github.com/openshift/release/pull/70167) | Reverted HyperShift for main and stable-2.x back to GCP IPI | Merged Oct 10 (2 days later) |
| Oct 2025 | [#70817](https://github.com/openshift/release/pull/70817) | Re-added HyperShift as optional-only job on main | Merged Oct 30 |

The revert was caused by `Validate_deployment_deletion_recovery` consistently failing on HyperShift. Root cause was unclear but likely related to behavioral differences between HyperShift hosted control planes and standard IPI clusters.

Related JIRA:
- RHOAIENG-31926 -- Original HyperShift migration
- RHOAIENG-37491 -- Optional HyperShift job
- RHOAIENG-42526 -- Spike to decide HyperShift vs IPI (still in backlog)

**Key takeaway:** The ODH operator team tried HyperShift, found it unreliable, reverted, and then migrated to Hive cluster pools as their P0 recommendation. Model serving adopted HyperShift and has stayed on it, experiencing a 54% provisioning failure rate.

## Provisioning Method Comparison

| Aspect | Cluster Profile (IPI) | Cluster Pool (Hive) | HyperShift via Prow (current) | HyperShift via Konflux EaaS |
|---|---|---|---|---|
| Mechanism | Fresh IPI install per job | Pre-provisioned cluster from Hive pool | Hosted control plane via Prow workflow | Hosted control plane via EaaS stepaction |
| Provisioning time | 25-40 min | 0-6 min (running: instant, hibernating: 3-6 min) | ~11-13 min median (when successful) | ~45-53 min total (incl. tests) |
| Cluster topology | Standard IPI | Standard IPI (identical) | Hosted control plane | Hosted control plane (same as Prow) |
| Resource management | Boskos leasing | Hive ClusterPool (direct cloud creds) | Boskos leasing (`aws-opendatahub`) | Konflux SpaceRequest (no Boskos) |
| Contention pool | `gcp-opendatahub` (8 jobs, 7 repos) | No shared pool | `aws-opendatahub` (47 jobs, 26 repos) | Konflux-managed (separate) |
| OCP versions | Any (including pre-release) | Released versions only | Released versions only | Released versions only |
| Test compatibility | Baseline | Identical to baseline | Some tests may fail (topology) | Same as Prow HyperShift |
| CI platform alignment | Prow (current) | Prow (current) | Prow (current) | Konflux (strategic direction) |
| Provisioning failure rate | Unknown | Unknown (ODH operator uses this) | **54%** (our data) | **~0%** (30/30 cluster provisions: omc + kserve) |

**Why cluster pools eliminate topology as a variable:** Pool clusters are standard IPI-provisioned clusters -- architecturally identical to what runs on GCP IPI. They are pre-built and hibernated, but otherwise unchanged. Since HyperShift test failures in the ODH operator correlated with the different cluster topology, using pool clusters removes that variable entirely.

**Why Konflux EaaS isolates the contention variable:** EaaS uses HyperShift (same topology as Prow) but with separate AWS credentials, a separate management cluster, and no Boskos involvement. With 30 successful cluster provisions -- 9/9 omc runs (18 provisions at 2-parallel) + 3/3 kserve group runs (12 provisions at 4-parallel) -- and zero provisioning failures, vs Prow's 54% provisioning failure rate, the data conclusively confirms Boskos pool contention as the root cause. Full analysis: [konflux-eaas-feasibility.md](konflux-eaas-feasibility.md).

## TRT Recommendation

From TRT Office Hours (2026-02-06):

> "Cluster profiles should be used for one purpose only: periodic jobs that validate against non-GA OCP versions. Everything else should move to cluster pools."

Our presubmit E2E jobs target GA OCP releases, so we are not constrained by the "released versions only" limitation of cluster pools.

## Key Differences with `cluster_claim`

Switching from `hypershift-hostedcluster-workflow` to `cluster_claim` with `workflow: generic-claim` introduces several behavioral changes (from strategic plan Appendix H):

| Current (HyperShift) | Cluster pool (`cluster_claim`) |
|---|---|
| Boskos leases AWS credentials | Hive manages credentials directly (no Boskos) |
| `${CLUSTER_PROFILE_DIR}/pull-secret` for pull secret | Use `ci-pull-credentials` secret from `test-credentials` namespace |
| `HYPERSHIFT_NODE_COUNT` controls node count | Node count fixed at pool creation in install-config |
| `COMPUTE_NODE_TYPE` controls instance type | Instance type fixed at pool creation |
| `hypershift-hostedcluster-workflow` | `generic-claim` (does NOT include operator-sdk installation) |
| Cluster has hosted control plane topology | Standard IPI topology |

The workflow change is the most significant: `generic-claim` is a minimal workflow that claims a cluster and provides kubeconfig. It does not include operator-sdk installation or any ODH-specific setup. Our existing pre-steps (ODH/KServe installation via `setup-e2e-tests.sh`) would need to handle all component setup, which they already do.

## Feasibility Questions

### Konflux EaaS (Option 3)

A proof of concept already exists: model serving E2E pipelines in [odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central) (`integration-tests/kserve/pr-group-testing-pipeline.yaml`, `integration-tests/odh-model-controller/pr-test-pipelinerun.yaml`) provision EaaS HyperShift clusters and run the same test scripts. This demonstrates that:

- The test runner (`test/scripts/openshift-ci/run-e2e-tests.sh`) works from Tekton
- EaaS cluster provisioning can be wired into the model serving test flow
- Multiple parallel EaaS clusters (graph, raw, predictor, LLM) can be provisioned in a single pipeline

Remaining questions:

1. ~~**EaaS provisioning success rate**~~: **Answered.** 30/30 cluster provisions succeeded: 9/9 omc ITS runs (18 provisions at 2-parallel) + 3/3 kserve group runs on `release-v0.15` (12 provisions at 4-parallel). Zero provisioning failures. See [konflux-eaas-feasibility.md](konflux-eaas-feasibility.md).
2. **Konflux ITS as pre-merge gate**: Can Konflux ITS serve as the primary pre-merge E2E gate? Current gaps include no native ChatOps (`/test`, `/retest`), no skip patterns, and different artifact visibility compared to Prow/Spyglass. See [objections analysis](konflux-eaas-feasibility.md#objections-and-counterpoints).
3. **Dual-CI transition**: During migration, would both Prow and Konflux E2E run on each PR, or would one be disabled? Running both doubles cluster consumption.

### Hive Cluster Pools (Option 2)

These questions apply only if migrating Prow jobs from HyperShift to Hive `cluster_claim`:

1. **Test behavior on IPI**: Pool clusters are standard IPI -- would any test behavior differ from HyperShift? The ODH operator found the opposite problem (tests failing on HyperShift that worked on IPI), so this is likely a non-issue for us.
2. **Pool capacity**: Does the `opendatahub` Hive pool owner have capacity for model serving's 5+ E2E job types (each running per PR)? Or would we need a dedicated pool?
3. **Pool sizing**: What `size`, `maxSize`, and `runningCount` would be needed? Sizing must align with available cloud quota in the AWS account.
4. **Pool management**: Pool manifests live in `openshift/release` under `clusters/hosted-mgmt/hive/pools/<team>/`. Who creates and maintains these? Coordinate with TRT via `#forum-ocp-testplatform`.
5. **Install-config requirements**: The pool's install-config determines node specs. What instance type and count do model serving tests need? Current config uses `HYPERSHIFT_NODE_COUNT=3` but does not specify instance type (defaults to HyperShift's default).

## Options

Ordered by effort, from lowest to highest:

### Option 1: Escalate with data and collaborate with `#wg-odh-e2e-stability`

The provisioning problem is well-known across the ODH ecosystem. The `#wg-odh-e2e-stability` working group (led by mstratto, the strategic plan author) is actively investigating provisioning failures. Their CI health data (March 2026) shows:

- **`clusterClaimStep` is their #1 failure** -- 289 failures in 7 days, even after migrating to Hive pools. Pool exhaustion replaced Boskos contention.
- **ODH operator 7-day success rate: 67.5%** with Hive pools (vs our 37% with HyperShift). Tests pass at 99.8% when they actually run.
- **Active investigation**: pool sizing, claim timeout reduction (current 2h timeout identified as unnecessarily long), and configuration fixes ([openshift/release#76260](https://github.com/openshift/release/pull/76260)).

The `#forum-ocp-testplatform` channel also has ongoing threads about AWS Boskos/Route53 issues affecting the `aws-opendatahub` pool (model-registry team reported the same `cluster_profile: aws-opendatahub` failures in April 2024).

**Effort:** Low (join `#wg-odh-e2e-stability`, share our data, coordinate)
**Expected impact:** Moderate -- provisioning improvements by the ODH operator team may benefit us indirectly if we share pool infrastructure. Our data (54% failure rate, 490 builds, log-based classification) would be a valuable contribution to their analysis.

### Option 2: Evaluate Hive cluster pools

The ODH operator already uses `cluster_claim` with `owner: opendatahub` and `workflow: generic-claim`. Their success rate improved from ~21% (IPI) to ~67.5% (Hive pools) -- a significant improvement but not a complete solution, as `clusterClaimStep` pool exhaustion is still their #1 failure.

Steps:
1. Check existing pool configuration in `openshift/release` under `clusters/hosted-mgmt/hive/pools/opendatahub/`
2. Assess capacity -- adding model serving's 5+ job types to the same pool would increase demand on an already-exhausted pool
3. Prototype a single job (e.g., `e2e-raw`, the simplest) with `cluster_claim` to validate test compatibility
4. If successful, migrate remaining jobs -- but coordinate pool sizing with the ODH operator team

**Effort:** Medium (pool investigation + prototype PR + validation + pool sizing coordination)
**Expected impact:** Moderate-High -- would improve from 37% to approximately the ODH operator's 67.5%, but not higher without pool sizing work. Eliminates Boskos contention and removes Hypershift topology variable, but introduces pool exhaustion as the new bottleneck.

### Option 3: Migrate E2E to Konflux EaaS

The model serving Konflux E2E pipelines already exist in [odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central) (`integration-tests/kserve/` and `integration-tests/odh-model-controller/`). They use the same test runner scripts (`test/scripts/openshift-ci/run-e2e-tests.sh`) and test code -- only the cluster provisioning path differs (EaaS instead of Prow/Boskos).

**EaaS provisioning data (measured):** 9/9 omc Konflux ITS E2E runs succeeded (18 cluster provisions at 2-parallel scale, 100%) between Feb 9 and Mar 18, 2026, with consistent 45-53 minute durations. This strongly supports the Boskos contention hypothesis. The kserve group pipeline (4 parallel clusters) has never been triggered. See [konflux-eaas-feasibility.md](konflux-eaas-feasibility.md) for full analysis including objections, counterpoints, and Slack ecosystem research.

Steps:
1. ~~Measure omc Konflux EaaS provisioning success rate~~ -- **Done.** 9/9 runs succeeded (18 cluster provisions).
1b. ~~**Wire up kserve group pipeline**~~ -- **Done.** PAC pipelines added to `release-v0.17` (PR #1240, Mar 19). Component builds work; group E2E configuration issue being debugged. Monitor subsequent PRs for 4-parallel-cluster data.
2. Evaluate Konflux ITS as the primary E2E path for pre-merge testing
3. Assess Konflux gaps: ChatOps (`/test`, `/retest`), skip patterns, artifact visibility -- see [objections table](konflux-eaas-feasibility.md#objections-and-counterpoints)
4. If gaps are acceptable, migrate pre-merge E2E from Prow to Konflux

**Effort:** Medium (gap assessment + transition planning; pipelines and data already exist)
**Expected impact:** High -- eliminates the 54% provisioning failure rate while aligning with the strategic CI platform direction (RHAISTRAT-903). Would improve overall success rate from 37% to potentially >90%. Remaining gaps (no native ChatOps, different artifact visibility) are workflow changes, not blockers.

### ~~Option 4: Provisioning retry wrapper~~ (not viable)

The dominant failure mode is Boskos lease timeout from pool contention -- the job waits for an `aws-opendatahub` lease, the pool is saturated, and the request times out. Retrying would place the job back in the same overloaded queue with no reason to expect a different result. This is not a transient error; it is a capacity problem. Options 1-3 address the root cause.

## Root Cause: Confirmed

The 54% provisioning failure rate is caused by **Boskos pool contention**, not HyperShift inherent reliability.

**Evidence:** Konflux EaaS uses the same HyperShift technology on AWS but with separate infrastructure (no Boskos, no `aws-opendatahub` pool). EaaS provisioning succeeded in 9/9 omc runs (18 cluster provisions at 2-parallel scale, 100%) vs Prow's 46% provisioning success rate. The only variable is credential management and AWS account isolation. The kserve 4-parallel-cluster case is untested.

This means:
- **Option 3 (Konflux EaaS)** directly eliminates the root cause by using separate infrastructure
- **Option 2 (Hive pools)** partially addresses it by bypassing Boskos, but introduces pool exhaustion as the new bottleneck (ODH operator's experience: 67.5% success, `clusterClaimStep` still #1 failure)
- **Option 1 (Collaborate)** remains valuable for improving the broader ecosystem but cannot solve the fundamental capacity problem

