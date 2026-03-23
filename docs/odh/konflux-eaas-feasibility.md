# Konflux EaaS Feasibility for Model Serving E2E

This document evaluates whether Konflux EaaS (Environment as a Service) is a viable replacement for Prow-based cluster provisioning in model serving CI. The primary motivation is the 54% Hypershift provisioning failure rate on Prow (see [cluster-provisioning-reliability.md](cluster-provisioning-reliability.md)).

The analysis is structured as:
1. **Objections** -- reasons Konflux E2E won't work or is ill-suited
2. **Counterpoints** -- mitigations, solutions, or corrections to each objection
3. **EaaS provisioning success rate** -- the single most important data point

## Infrastructure: Where Our Konflux Instances Live

| Attribute | Value |
|---|---|
| Konflux UI | `https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com` |
| Tenant namespace | `open-data-hub-tenant` |
| Applications | `opendatahub-builds` (CI), `group-testing` (kserve group), `opendatahub-release` (release) |
| Artifact browser | `https://app-artifact-browser.apps.rosa.konflux-qe.zmr9.p3.openshiftapps.com` |
| EaaS stepactions | Resolved from `konflux-ci/build-definitions` on `main` |
| EaaS provisioning | `eaas-provision-space` -> `eaas-create-ephemeral-cluster-hypershift-aws` (HyperShift on Konflux-managed AWS, no Boskos) |

### Key E2E Pipelines

**kserve** -- PAC pipelines added to `opendatahub-io/kserve` on `release-v0.17` branch (PR #1240, merged Mar 19 2026):
- 5 component build pipelines (agent, controller, router, storage-initializer, llmisvc-controller) -- all working, triggered via PAC on every PR
- `kserve-group-test` -- the E2E pipeline that provisions parallel EaaS clusters for graph, raw, predictor, and LLM test suites
- Group pipeline definition is in `integration-tests/kserve/pr-group-testing-pipeline.yaml` in [odh-konflux-central](https://github.com/opendatahub-io/odh-konflux-central)
- **Status (Mar 20):** component builds work (5/5 on every PR); group E2E test works on `release-v0.17`. **Gap:** llmisvc-controller tests are not yet included in the group pipeline.

**odh-model-controller** -- `integration-tests/odh-model-controller/pr-test-pipelinerun.yaml`:
- `kind: PipelineRun`, name `odh-model-controller-e2e-test`
- Provisions EaaS cluster, deploys ODH operator from Konflux snapshot, runs `run-e2e-tests.sh raw 2 raw`
- Has `IntegrationTestScenario` `odh-model-controller-ci-its-manual` wired to `application: opendatahub-builds`, context `component_odh-model-controller-ci`
- Pipeline timeout: 4h, task timeout: 3h

Both pipelines invoke the same test runner scripts as Prow (`test/scripts/openshift-ci/run-e2e-tests.sh`).

## Objections and Counterpoints

| # | Objection | Severity | Counterpoint | Status |
|---|---|---|---|---|
| 1 | ~~**EaaS provisioning reliability is unknown**~~ | ~~BLOCKING~~ | **Resolved.** 30 EaaS cluster provisions with zero provisioning failures: 9/9 omc ITS runs (18 provisions at 2-parallel) + 3/3 kserve group runs (12 provisions at 4-parallel) between Feb-Mar 2026. See [findings below](#findings). | Resolved |
| 2 | **Limited ChatOps** -- no `/test` command on GitHub PRs | Low | Konflux supports `/retest` (retrigger failed pipelines), `/cherry-pick` (backport), and `/konflux-help` (list commands). Only `/test <job-name>` (run a specific named job) has no equivalent. PR builds are triggered automatically by PAC on push. Retesting a specific pipeline is done via `/retest` or the Konflux UI. Smaller gap than originally assessed. | Acceptable |
| 3 | **Different artifact visibility** -- no Spyglass; artifacts go to OCI registry + custom artifact browser | Low | The artifact browser at `https://app-artifact-browser.apps.rosa.konflux-qe.zmr9.p3.openshiftapps.com` serves the same purpose. Must-gather and test logs are pushed via `secure-git-push` to `opendatahub-io/odh-build-metadata`. Workflow change, not a capability gap. | Acceptable |
| 4 | ~~**kserve group pipeline has no trigger**~~ | ~~Medium~~ | **Resolved.** PAC pipelines active on `release-v0.15` since Feb 24 (PR #1094) and ported to `release-v0.17` on Mar 19 (PR #1240). 3 successful group E2E runs on `release-v0.15`. | Resolved |
| 5 | **HyperShift topology issues** -- the ODH operator reverted HyperShift due to test failures; EaaS uses the same topology | Low | Model serving tests have been running on HyperShift (via Prow) for months. The 28% `test:assertion` failure rate includes all test bugs, not topology-specific ones. The ODH operator's topology issue was specific to `Validate_deployment_deletion_recovery`, which is not a model serving test. Our tests are already HyperShift-compatible. | Non-issue for us |
| 6 | **Strategic plan deferred E2E migration** -- explicitly stated Konflux not mature enough | Medium | The strategic plan (late 2025) assessed Konflux maturity at that time. Since then: (a) the PoC pipelines in odh-konflux-central have been developed and refined, (b) the ODH operator also has Konflux ITS, and (c) RHAISTRAT-903 identifies Konflux as the strategic CI direction. The maturity assessment should be re-evaluated against current state. | Needs re-evaluation |
| 7 | **Dual-CI transition doubles cluster consumption** -- running both Prow and Konflux E2E during migration | Low | Transition can be phased: (a) validate EaaS reliability data, (b) run Konflux E2E as informational (no PR gate) alongside Prow, (c) once confident, make Konflux the gate and disable Prow E2E. The dual period can be short. Alternatively, the Prow E2E jobs currently fail 63% of the time anyway -- replacing them does not meaningfully increase total cluster hours. | Manageable |
| 8 | ~~**omc ITS is "manual"**~~ -- named `odh-model-controller-ci-its-manual`, unclear if auto-triggered | ~~Low~~ | **Verified.** 9/9 main-branch PRs with component builds had the ITS auto-trigger. The "manual" in the name refers to the ITS being manually created (not auto-generated by PAC), not to its trigger behavior. | Resolved |
| 9 | **No file-based skip patterns** -- can't skip E2E based on which files changed in PR | Low | Prow E2E jobs also do not use file-based skip patterns today. All E2E jobs run on every PR regardless of changed files. This is not a regression from current behavior. If skip patterns are needed in the future, Tekton `when` expressions or PAC CEL filters can be used. | Non-issue |
| 10 | **Released OCP versions only** -- EaaS can only provision GA OCP versions | Low | Our current HyperShift Prow jobs also target GA OCP releases. We do not test against pre-release OCP. This is a constraint we already live with. | Non-issue |
| 11 | **Loss of Tide merge queue** -- Prow's Tide provides auto-rebase, batch merge, stale-branch testing | High | Raised by pierDipi in `#team-openshift-ai-devel` (Feb 2026). Tide ensures no PRs merge on stale branches and batch-merges approved PRs. Konflux can work with Tide for status checks but cannot coordinate batch retesting. **Proposed mitigation:** use **Mergify** as Tide replacement (Deepak/dchourasia recommendation). spolti open to testing. Hybrid also viable: keep Prow for merge automation, delegate E2E to Konflux. | Open -- needs evaluation |
| 12 | **Loss of must-gather artifacts** -- Prow collects must-gather data post-test, kept for weeks in Spyglass | Medium | Raised by spolti in `#team-openshift-ai-devel` (Feb 2026). Users cannot SSH into ephemeral EaaS clusters. Must-gather collection needs to be implemented as a Tekton task in the pipeline. dchourasia committed to investigating. | Open -- needs implementation |
| 13 | **Loss of Prow retester** -- auto-retries flaky approved+lgtm PRs via `openshift/release` retester config | Medium | Raised by pierDipi in `#team-openshift-ai-devel`. dchourasia says "possible using Konflux chatops, but not automatically." No native Konflux equivalent exists today. | Open -- no solution yet |
| 14 | **Hardware constraints** -- EaaS clusters limited to 3x m5.2xlarge (8 vCPU, 32GB each) | Low | Raised by spolti and jlost. Initially caused random test failures on Konflux. Increasing the global default timeout resolved it. The same cluster spec matches Prow's `HYPERSHIFT_NODE_COUNT=3`. If LLM tests need more, this is a constraint. | Resolved by timeout tuning |
| 15 | **Dynamic branch onboarding** -- each `release-vX.YY` branch requires manual Konflux re-onboarding | Low | kserve uses rolling release branches (`release-v0.15`, `release-v0.17`) rather than BoW-style fixed `stable` branch. Each branch change requires PAC pipeline updates. dchourasia committed to preparing steps for self-service onboarding. | Manageable |
| 16 | **Moving away from k8s ecosystem standard** -- Prow is the de-facto CI standard in the k8s ecosystem | Low | Raised by vadim in `#team-openshift-ai-devel`. Valid concern for upstream contributions. However, upstream/kserve tests already use GH Actions (not Prow), so Konflux doesn't introduce a new divergence from upstream. Only the ODH/RHOAI fork uses Prow. | Non-issue for model serving |
| 17 | **Long-term cost ownership** -- "unclear if Konflux team will eat RHOAI testing cost forever" | Low | Raised by pierDipi. EaaS clusters are not billed to the RHOAI cost center today, but this could change. However, Prow's Boskos AWS costs are also real. Even if costs shift, the reliability improvement (0% vs 54% provisioning failure) justifies the move. | Acceptable risk |
| 18 | ~~**Image tagging strategy** -- Konflux defaults to commit SHA only; needs custom Tekton task~~ | ~~Medium~~ | **Resolved.** Verified Mar 2026: model serving pipelines already use custom tags. Push builds produce `odh-v3.4` (versioned) + `odh-stable` (floating) + `rhoai-init.mandatory-tag` (computed). PR builds produce `odh-pr` + `odh-pr-{{revision}}` (commit SHA). Applied via catalog `apply-tags` task in `multi-arch-container-build` pipeline. Only difference from Prow: PR images use commit SHA instead of PR number -- minor workflow difference, not a gap. | Resolved |
| 19 | **PR test image publishing** -- Prow's `/test pr-image-mirror-kserve-controller` pushes PR images for external testing before merge | Low | No direct Konflux equivalent for on-demand PR image mirroring. However, Konflux PR builds already push `odh-pr` + `odh-pr-<sha>` tags to `quay.io/opendatahub/` on every PR, so PR images are already available without a manual trigger. The Prow workflow is rarely used. Manual `kubectl create pipelinerun` is a fallback if needed. | Acceptable |
| 20 | **No TestGrid / historical test visualization** -- Prow feeds TestGrid for trend analysis and flake detection | Low | Konflux UI shows current pipeline runs but has no historical aggregation like TestGrid. However, model serving does not currently use TestGrid for flake detection or trend analysis -- our observability gap exists on both platforms equally. If needed, JUnit XML export to Grafana or ci-test-mapping (see [ci-stability-spike.md](ci-stability-spike.md)) would solve this for both Prow and Konflux. | Non-issue (parity) |
| 21 | **Test artifact storage migration** -- Prow stores artifacts in GCS (accessible via Spyglass); Konflux uses S3/OCI | Low | Artifact storage location changes but capability is equivalent. Konflux pipelines already push artifacts via `secure-git-push` to `opendatahub-io/odh-build-metadata`. S3 lifecycle policies may need configuration for retention. Overlaps with #3 (artifact visibility) and #12 (must-gather). | Acceptable |

### Summary of Objections

- **21 objections evaluated, 0 blocking**
- **Resolved (5):** #1 (provisioning reliability), #4 (kserve group trigger), #8 (omc ITS trigger), #18 (image tagging)
- **Resolved by workaround (1):** #14 (hardware constraints -- timeout tuning)
- **Non-issue / parity (5):** #5 (HyperShift topology), #9 (file-based skip), #10 (GA OCP only), #16 (k8s ecosystem), #20 (TestGrid)
- **Acceptable (5):** #2 (ChatOps -- `/retest` exists), #3 (artifact visibility), #17 (cost ownership), #19 (PR image publishing), #21 (artifact storage)
- **Manageable (2):** #7 (dual-CI transition), #15 (branch onboarding)
- **Open gaps (3):**
  - (a) **Tide/merge queue replacement** (#11) -- highest-severity open item; Mergify proposed but untested by us
  - (b) **Must-gather data** (#12) -- needs a Tekton task; not present in current pipeline
  - (c) **Retester** (#13) -- no native Konflux equivalent; manual retest via `/retest` comment
- **Needs re-evaluation (1):** #6 (strategic plan maturity assessment predates current PoC data)
- **What we know:** EaaS provisions clusters reliably at both 2-parallel (omc: 18/18) and 4-parallel (kserve: 12/12) scale, totaling 30 successful provisions with zero provisioning failures. This conclusively confirms Boskos pool contention as the root cause of Prow's 54% provisioning failure rate.
- **Team consensus (from Slack):** spolti proposed hybrid approach -- "keep using konflux and openshift-ci in parallel, delegate CI tests to konflux, keep Prow for tide/cherry-pick/merge." dchourasia agreed: "you can perfectly keep using it if it is benefiting you!"

## EaaS Provisioning Success Rate

This is the critical data point. If EaaS provisioning succeeds at ~90%+, the Prow 54% failure rate is confirmed as Boskos contention and Konflux EaaS becomes the clear path forward. If EaaS also fails at ~50%, the problem is HyperShift itself and only Hive cluster pools (standard IPI topology) would help.

### Data Collection Approaches

**Approach A: GitHub PR checks** (most accessible)

The omc `IntegrationTestScenario` (`odh-model-controller-ci-its-manual`) runs on `opendatahub-builds` component builds. Recent PRs to `opendatahub-io/odh-model-controller` should have Konflux check statuses visible on the PR. By examining recent PR check results, we can count pass/fail for the Konflux E2E pipeline.

Limitation: PR check status shows overall pass/fail but cannot distinguish provisioning failures from test failures without examining logs. However, if the overall pass rate is significantly higher than Prow's 37%, that itself is strong evidence.

**Approach B: Slack research**

Search `#wg-odh-e2e-stability`, `#forum-ocp-testplatform`, and Konflux-related channels for EaaS reliability data. The ODH operator team has comprehensive CI observability tooling that may include Konflux pipeline data.

**Approach C: Konflux UI / Tekton API** (requires access)

Browse the Konflux UI at `https://konflux-ui.apps.stone-prd-rh01.pg1f.p1.openshiftapps.com/ns/open-data-hub-tenant/applications/opendatahub-builds/pipelineruns` to view integration test pipeline run history. Alternatively, query PipelineRun objects via Tekton API on the Konflux cluster.

### Findings

#### GitHub PR Check Data (Approach A)

The `odh-model-controller-ci-its-manual` ITS runs on PRs to the `main` branch (not `incubating`). By querying all merged `main` PRs via GitHub API going back to Jan 2026, we found every PR that had a Konflux ITS check:

| PR | Date | ITS Result | Duration | Build Check |
|---|---|---|---|---|
| #750 | Mar 18 | SUCCESS | 52 min | SUCCESS |
| #738 | Mar 13 | SUCCESS | 46 min | SUCCESS |
| #737 | Mar 17 | SUCCESS | 50 min | SUCCESS |
| #729 | Mar 12 | SUCCESS | 53 min | SUCCESS |
| #722 | Mar 6 | SUCCESS | 49 min | SUCCESS |
| #695 | Feb 20 | SUCCESS | 47 min | SUCCESS |
| #690 | Feb 13 | SUCCESS | 52 min | SUCCESS |
| #689 | Feb 12 | SUCCESS | 45 min | SUCCESS |
| #682 | Feb 9 | SUCCESS | 47 min | SUCCESS |

**Result: 9/9 completed runs succeeded (100%).** One additional run (PR #733) was still `in_progress` when the PR was merged.

**Key observations:**

- **100% success rate** across 9 E2E runs vs Prow's **37%** over the same period
- **Consistent duration**: 45-53 minutes (tight range), suggesting stable provisioning -- no outliers from contention
- **ITS triggers automatically** despite the "manual" name: `test.appstudio.openshift.io/optional: "false"` means it runs when `odh-model-controller-ci` component build completes
- **ITS only runs on `main` branch PRs** -- several `main` PRs without ITS checks (e.g., #698) did not trigger a component build

**Sample size context:** 9 runs is every ITS E2E run that has occurred since the ITS was enabled (~early Feb 2026). The sample is small because it is structurally limited: most omc development happens on the `incubating` branch, and the ITS only triggers on `main` branch PRs when a component build completes. This is an exhaustive sample, not a random one -- we are not missing failures, we have looked at every run. The 100% rate should not be taken as absolute (EaaS provisioning can fail per Slack findings below), but the contrast with Prow's 37% is directionally conclusive: EaaS provisioning is substantially more reliable than Prow's `aws-opendatahub` Boskos path.

**What the omc ITS actually runs:** Each ITS run provisions **2 EaaS clusters in parallel** (one for `raw` tests, one for LLM tests), then clones `opendatahub-io/kserve release-v0.15` and runs **kserve's** test scripts (`run-e2e-tests.sh`). So 9 pipeline runs = 18 successful EaaS cluster provisions. The test code is kserve's E2E suite, not omc-specific tests. Only the omc container image comes from the PR.

**kserve group E2E data (`release-v0.15`):** PAC pipelines were first added to kserve on `release-v0.15` (PR #1094, merged Feb 24). The `kserve-group-test` provisions **4 parallel EaaS clusters** (graph, raw, predictor, LLM):

| PR | Date | kserve-group-test | Duration | Branch |
|---|---|---|---|---|
| #1094 | Feb 23 | **SUCCESS** | ~1h55m | release-v0.15 |
| #1153 | Mar 5 | **SUCCESS** | ~1h00m | release-v0.15 |
| #1176 | Mar 10 | **SUCCESS** | ~1h54m | release-v0.15 |
| #1178 | Mar 11 | **FAILURE** | ~4 min | release-v0.15 (pipeline error, not provisioning) |
| #1248 | Mar 20 | **FAILURE** | instant | release-v0.17 (config issue on new branch) |

**Result: 3/3 provisioning-relevant runs succeeded (12 cluster provisions at 4-parallel scale).** The 2 failures were pipeline/config errors (4 min and instant duration) that never reached the provisioning step. Not included on `master` -- Konflux is only on release branches.

**kserve on `release-v0.17`:** PAC pipelines were ported to `release-v0.17` (PR #1240, Mar 19). Component builds work (5/5 on every PR). The group E2E test has a configuration issue being debugged (PR #1248 instant failure).

#### Slack Research (Approach B)

Searches across `#konflux-users`, `#forum-konflux-vanguard`, `#forum-konflux-infrastructure`, and `#forum-konflux-devprod` revealed:

**EaaS provisioning failures do happen but are managed differently:**

- `#konflux-users` (March 2026): `ClusterTemplateInstance` timeout when provisioning HyperShift clusters is a known issue pattern. The common root cause is AWS account resource quota exhaustion on the EaaS backend.
- `#forum-konflux-vanguard`: The **Vanguard team** manages EaaS provisioning. Escalation path: `#forum-konflux-vanguard` -> JIRA project `KFLUXVNGD`.
- There is a documented SOP: `gitlab.cee.redhat.com/konflux/docs/sop/-/blob/main/eaas/hypershift-aws-provisioning-timeout.md`
- Provisioning issues are escalated to the EaaS/Vanguard team, who has direct access to the management cluster and AWS quotas -- unlike Prow's Boskos pools where "nobody is actively managing capacity."

**Konflux E2E flakiness is a different problem:**

- Konflux's *own* E2E tests (e.g., `infra-deployments`) have flakiness problems, but these are caused by etcd/containerd overload on kind clusters, not EaaS HyperShift provisioning. The Vanguard team (flacatus) achieved 9/10 success rate after tuning kind cluster resources.
- This is not relevant to our use case: we use EaaS HyperShift clusters (real OCP clusters), not kind clusters.

**Key takeaway:** EaaS provisioning is managed by a dedicated team (Vanguard) with direct AWS account access, documented SOPs, and an escalation path. This is qualitatively different from Prow's Boskos pools where capacity management is described as "blindly feeling around in the dark."

### Conclusion: Root Cause Confirmation

The data strongly supports the **Boskos pool contention hypothesis**:

| Metric | Prow (Boskos) | Konflux EaaS (omc, 2 clusters) | Konflux EaaS (kserve, 4 clusters) |
|---|---|---|---|
| Provisioning success rate | ~46% | ~100% (18/18 cluster provisions) | ~100% (12/12 cluster provisions) |
| Overall E2E success rate | 37% | 100% (9/9 pipeline runs) | 100% (3/3 provisioning-relevant runs) |
| Duration consistency | High variance (P50=29min pre-test, P99=2h) | Low variance (45-53 min total) | Low variance (1h00m-1h55m total) |
| Capacity management | "Blindly feeling around in the dark" | Dedicated team (Vanguard), SOPs, escalation path | Same |
| AWS account sharing | 47 jobs from 26 repos | Separate infrastructure | Same |

**Combined: 30 successful EaaS cluster provisions** (18 from omc at 2-parallel + 12 from kserve at 4-parallel) with **zero provisioning failures**. Both paths use HyperShift on AWS. The only difference from Prow is credential management and AWS account isolation. The 54% Prow provisioning failure rate is a Boskos pool contention problem, not a HyperShift inherent reliability problem.

## Migration Plan

Based on the [Konflux migration spike](https://docs.google.com/document/d/1Jy0hdcZeJGfoQDLlE_PZ5bpljIFRWlX7kgu7FzpC4ho/edit) and the findings above, the migration can follow a phased approach. The hybrid consensus (keep Prow for merge automation, delegate E2E to Konflux) means this is primarily an E2E test migration, not a full CI platform swap.

### Phase 1: Prerequisites (~1 week)

| Task | Effort | Status |
|---|---|---|
| ~~Fix `release-v0.17` group test config~~ | 1-2d | Done |
| Add llmisvc-controller tests to group pipeline | 1-2d | Not started |
| Verify must-gather support in EaaS template; create Tekton task if missing (#12) | 2-3d | Not started |
| Evaluate Mergify as Tide replacement (#11) | 2-3d | Not started |

### Phase 2: Parallel Run (~2 weeks)

| Task | Effort | Status |
|---|---|---|
| Run Konflux E2E as informational (non-blocking) alongside Prow | Ongoing | Not started |
| Compare daily: build success rate, test pass rate, must-gather artifacts, image tagging | Ongoing | Not started |
| Fix discrepancies between platforms | Variable | Not started |
| Monitor EaaS provisioning reliability at scale | Ongoing | Not started |

### Phase 3: Cutover (~1 week)

| Task | Effort | Status |
|---|---|---|
| Make Konflux E2E the PR gate (required check) | 1d | Not started |
| Disable Prow E2E jobs in `openshift/release` | 1d | Not started |
| Update CONTRIBUTING.md with Konflux workflow | 1d | Not started |
| Onboard future release branches (`release-vX.YY`) | 1d per branch | Ongoing |

### Cutover Criteria

Do not disable Prow E2E until **all** criteria are met:

- [ ] Konflux E2E pass rate >= 90% of Prow E2E pass rate (excluding provisioning failures)
- [ ] Must-gather collected on 100% of test failures
- [ ] Image tagging matches expected format (verified: `odh-v3.4` + `odh-stable` + `rhoai-init.mandatory-tag`)
- [ ] Merge automation solution in place (Mergify or hybrid Prow)
- [ ] Team trained on Konflux workflow (PAC, `/retest`, Konflux UI, manual PipelineRun creation)
- [ ] Rollback plan documented (re-enable Prow E2E jobs)

### Effort Estimate

| Phase | Estimate |
|---|---|
| Phase 1: Prerequisites | ~5 person-days |
| Phase 2: Parallel run | ~10 person-days (2 weeks elapsed, part-time monitoring) |
| Phase 3: Cutover | ~3 person-days |
| **Total** | **~18 person-days** |

This is lower than the spike document's estimate of ~30 person-days because image tagging (#18) and slash command parity (#2) are already resolved, and team training can happen during the parallel run phase.

## Sources

### Internal Documents

- **[Konflux Migration Spike](https://docs.google.com/document/d/1Jy0hdcZeJGfoQDLlE_PZ5bpljIFRWlX7kgu7FzpC4ho/edit)** -- Comprehensive audit of OpenShift-CI features vs Konflux capabilities, including image inventory, feature comparison matrix, gap analysis, migration task list with effort estimates, and cutover criteria. Source for objections #18-21 and migration plan.

### Slack

- **`#team-openshift-ai-devel` thread (Feb 3 - Feb 25, 2026):** [permalink](https://redhat-internal.slack.com/archives/C05NXTEHLGY/p1770193674407879) -- Extensive discussion between Konflux transition team (dchourasia) and model serving team (spolti, pierDipi, jlost, vadim) about obstacles, feature gaps, and resolution strategies. Source for objections #11-17.

### JIRA

| Issue | Summary | Status |
|---|---|---|
| [RHAISTRAT-903](https://issues.redhat.com/browse/RHAISTRAT-903) | E2E CI/CD Ecosystem across ODH & RHOAI (strategic umbrella) | **In Progress** |
| [RHAISTRAT-490](https://issues.redhat.com/browse/RHAISTRAT-490) | Phase 1 - ODH Nightlies Konflux Transition | **Closed** |
| [RHAISTRAT-622](https://issues.redhat.com/browse/RHAISTRAT-622) | Phase 2 - Branching & Auto-Sync Rethink | **In Progress** |
| [RHAISTRAT-647](https://issues.redhat.com/browse/RHAISTRAT-647) | Phase 3 | **New** |
| [RHAISTRAT-776](https://issues.redhat.com/browse/RHAISTRAT-776) | Phase 4 | **New** |
| [RHOAIENG-49255](https://issues.redhat.com/browse/RHOAIENG-49255) | Kserve e2e tests failing randomly on Openshift-CI & Konflux | **Closed** (same failures on both platforms) |
| [RHOAIENG-48215](https://issues.redhat.com/browse/RHOAIENG-48215) | Implement & enable Integration Group testing pipeline for kserve | **Closed** |
| [RHOAIENG-50090](https://issues.redhat.com/browse/RHOAIENG-50090) | Quality Gates Redefinement | **In Progress** |
| [RHOAIENG-33451](https://issues.redhat.com/browse/RHOAIENG-33451) | E2E CI/CD Ecosystem for ODH+RHOAI | **In Progress** |
| [KFLUXMIG-941](https://issues.redhat.com/browse/KFLUXMIG-941) | RHOAI Midstream Testing Builds enablement | **Closed** |

