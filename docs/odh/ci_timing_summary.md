# CI Timing Data Summary

Collected 490 builds across 6 job types.


## graph (pull-ci-opendatahub-io-kserve-master-e2e-graph)

- Builds collected: 99
- Completed (non-aborted): 47
- Success rate: 21/47 (45%)

| Phase | Median | P90 | P99 | Min | Max |
|---|---|---|---|---|---|
| Total job | 1h37m | 2h28m | 3h54m | 3m12s | 3h43m |
| Pre-test (ci-op + provision) | 30m56s | 52m04s | 1h28m | 12m17s | 1h22m |
| Test execution | 31m40s | 45m09s | 2h45m | 3m23s | 2h00m |
| Post-steps (gather + destroy) | 34m52s | 1h07m | 1h20m | 28m01s | 1h19m |


## service (pull-ci-opendatahub-io-kserve-master-e2e-llm-inference-service)

- Builds collected: 70
- Completed (non-aborted): 42
- Success rate: 1/42 (2%)

| Phase | Median | P90 | P99 | Min | Max |
|---|---|---|---|---|---|
| Total job | 1h15m | 2h00m | 3h35m | 3m18s | 3h24m |
| Pre-test (ci-op + provision) | 35m26s | 59m58s | 1h06m | 16m32s | 1h05m |
| Test execution | 6m54s | 1h52m | 1h53m | 5m55s | 1h53m |
| Post-steps (gather + destroy) | 36m56s | 1h01m | 1h11m | 32m01s | 1h09m |


## predictor (pull-ci-opendatahub-io-kserve-master-e2e-predictor)

- Builds collected: 99
- Completed (non-aborted): 46
- Success rate: 13/46 (28%)

| Phase | Median | P90 | P99 | Min | Max |
|---|---|---|---|---|---|
| Total job | 1h38m | 2h41m | 3h47m | 3m11s | 3h41m |
| Pre-test (ci-op + provision) | 29m15s | 52m25s | 1h33m | 12m16s | 1h21m |
| Test execution | 24m52s | 1h03m | 2h28m | 3m15s | 2h00m |
| Post-steps (gather + destroy) | 35m25s | 1h06m | 1h09m | 26m18s | 1h08m |


## raw (pull-ci-opendatahub-io-kserve-master-e2e-raw)

- Builds collected: 99
- Completed (non-aborted): 50
- Success rate: 26/50 (52%)

| Phase | Median | P90 | P99 | Min | Max |
|---|---|---|---|---|---|
| Total job | 1h19m | 2h38m | 3h45m | 3m10s | 3h41m |
| Pre-test (ci-op + provision) | 30m56s | 58m33s | 1h09m | 11m55s | 1h07m |
| Test execution | 20m59s | 30m49s | 2h00m | 3m19s | 2h00m |
| Post-steps (gather + destroy) | 33m23s | 40m33s | 1h09m | 29m19s | 1h08m |


## kserve (pull-ci-opendatahub-io-odh-model-controller-main-e2e-odh-kserve)

- Builds collected: 56
- Completed (non-aborted): 33
- Success rate: 11/33 (33%)

| Phase | Median | P90 | P99 | Min | Max |
|---|---|---|---|---|---|
| Total job | 1h02m | 2h23m | 2h41m | 1m29s | 2h41m |
| Pre-test (ci-op + provision) | 18m10s | 1h15m | 1h57m | 53s | 1h53m |
| Test execution | 15m16s | 17m45s | 24m11s | 2m46s | 20m56s |
| Post-steps (gather + destroy) | 30m51s | 36m20s | 43m32s | 24m12s | 39m54s |


## llmisvc (pull-ci-opendatahub-io-odh-model-controller-main-e2e-odh-llmisvc)

- Builds collected: 67
- Completed (non-aborted): 43
- Success rate: 10/43 (23%)

| Phase | Median | P90 | P99 | Min | Max |
|---|---|---|---|---|---|
| Total job | 1h28m | 2h39m | 3h52m | 1m37s | 3h35m |
| Pre-test (ci-op + provision) | 22m00s | 1h44m | 2h47m | 51s | 2h31m |
| Test execution | 32m23s | 47m47s | 1h25m | 5m24s | 1h11m |
| Post-steps (gather + destroy) | 30m25s | 39m02s | 1h11m | 23m13s | 58m03s |


## Aggregate (all job types)

- Total completed: 261
- Overall success rate: 82/261 (31%)

| Phase | Median | P90 | P99 | Min | Max |
|---|---|---|---|---|---|
| Total job | 1h23m | 2h35m | 3h41m | 1m29s | 3h43m |
| Pre-test (ci-op + provision) | 29m27s | 59m53s | 2h01m | 51s | 2h31m |
| Test execution | 22m15s | 1h01m | 2h00m | 2m46s | 2h00m |
| Post-steps (gather + destroy) | 33m51s | 1h02m | 1h18m | 23m13s | 1h19m |


---

# Failure Classification

Classified 179 FAILURE builds by build-log pattern matching.


### All job types

| Category | Count | % |
|---|---|---|
| platform:provision | 94 | 53% |
| test:assertion | 51 | 28% |
| platform:ci-infra | 11 | 6% |
| setup:install | 10 | 6% |
| test:other | 6 | 3% |
| platform:timeout | 2 | 1% |
| setup:config | 2 | 1% |
| platform:cluster-health | 2 | 1% |
| test:collection | 1 | 1% |

**Platform (out-of-domain): 109 (61%)**  
**Setup (in-domain infra): 12 (7%)**  
**Test: 58 (32%)**  


### kserve jobs

| Category | Count | % |
|---|---|---|
| platform:provision | 61 | 49% |
| test:assertion | 36 | 29% |
| platform:ci-infra | 11 | 9% |
| setup:install | 9 | 7% |
| test:other | 5 | 4% |
| test:collection | 1 | 1% |
| platform:timeout | 1 | 1% |


### odh-model-controller jobs

| Category | Count | % |
|---|---|---|
| platform:provision | 33 | 60% |
| test:assertion | 15 | 27% |
| setup:config | 2 | 4% |
| platform:cluster-health | 2 | 4% |
| test:other | 1 | 2% |
| setup:install | 1 | 2% |
| platform:timeout | 1 | 2% |


### graph

| Category | Count | % |
|---|---|---|
| platform:provision | 13 | 50% |
| test:assertion | 7 | 27% |
| platform:ci-infra | 3 | 12% |
| setup:install | 2 | 8% |
| test:other | 1 | 4% |


### service

| Category | Count | % |
|---|---|---|
| platform:provision | 20 | 49% |
| test:assertion | 13 | 32% |
| setup:install | 3 | 7% |
| platform:ci-infra | 2 | 5% |
| test:collection | 1 | 2% |
| platform:timeout | 1 | 2% |
| test:other | 1 | 2% |


### predictor

| Category | Count | % |
|---|---|---|
| platform:provision | 14 | 42% |
| test:assertion | 13 | 39% |
| platform:ci-infra | 3 | 9% |
| setup:install | 2 | 6% |
| test:other | 1 | 3% |


### raw

| Category | Count | % |
|---|---|---|
| platform:provision | 14 | 58% |
| test:assertion | 3 | 12% |
| platform:ci-infra | 3 | 12% |
| setup:install | 2 | 8% |
| test:other | 2 | 8% |


### kserve

| Category | Count | % |
|---|---|---|
| platform:provision | 16 | 73% |
| test:assertion | 3 | 14% |
| setup:config | 2 | 9% |
| test:other | 1 | 5% |


### llmisvc

| Category | Count | % |
|---|---|---|
| platform:provision | 17 | 52% |
| test:assertion | 12 | 36% |
| platform:cluster-health | 2 | 6% |
| setup:install | 1 | 3% |
| platform:timeout | 1 | 3% |
