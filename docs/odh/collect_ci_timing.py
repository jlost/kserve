#!/usr/bin/env python3
"""Collect step-level timing data from Prow/GCS for E2E CI jobs.

Scrapes Prow job history pages to enumerate recent builds, then
fetches per-step timing from GCS artifacts.  Outputs a CSV of raw
data and a markdown summary with percentile statistics.

Usage:
    python3 collect_ci_timing.py \
        [--jobs N] [--output-dir DIR] [--job-types TYPE,...]

Requires: requests (pip install requests)
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

import requests

GCS_BUCKET = "test-platform-results"
GCS_BASE = f"https://storage.googleapis.com/{GCS_BUCKET}"
GCS_API = (
    "https://storage.googleapis.com"
    f"/storage/v1/b/{GCS_BUCKET}/o"
)
PROW_HISTORY = (
    "https://prow.ci.openshift.org"
    "/job-history/gs/{bucket}/pr-logs/directory/{job_name}"
)

JOB_TYPES: dict[str, str] = {
    "pull-ci-opendatahub-io-kserve-master-e2e-predictor":
        "e2e-predictor",
    "pull-ci-opendatahub-io-kserve-master-e2e-graph":
        "e2e-graph",
    "pull-ci-opendatahub-io-kserve-master-e2e-raw":
        "e2e-raw",
    "pull-ci-opendatahub-io-kserve-master"
    "-e2e-llm-inference-service":
        "e2e-llm-inference-service",
    "pull-ci-opendatahub-io-odh-model-controller"
    "-main-e2e-odh-kserve":
        "e2e-odh-kserve",
    "pull-ci-opendatahub-io-odh-model-controller"
    "-main-e2e-odh-llmisvc":
        "e2e-odh-llmisvc",
}

KNOWN_STEPS = {
    "hypershift-hostedcluster-create-hostedcluster",
    "hypershift-hostedcluster-create-wait-for-olm",
    "hypershift-hostedcluster-destroy-hostedcluster",
    "hypershift-hostedcluster-dump-hostedcluster",
    "openshift-cluster-bot-rbac",
    "kserve-must-gather",
    "openshift-must-gather",
    "testlog-gather",
}

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ci-timing-collector/1.0"

_LOGS_DIR: Optional[Path] = None


@dataclass
class BuildTiming:
    job_type: str = ""
    build_id: str = ""
    pr_number: str = ""
    result: str = ""
    job_start: Optional[int] = None
    job_end: Optional[int] = None
    total_s: Optional[int] = None
    create_end: Optional[int] = None
    olm_end: Optional[int] = None
    test_end: Optional[int] = None
    destroy_end: Optional[int] = None
    pre_test_s: Optional[int] = None
    test_s: Optional[int] = None
    post_s: Optional[int] = None
    test_step_name: str = ""
    failure_category: str = ""
    failure_signals: str = ""
    log_fetched: bool = False


CSV_FIELDS = [f.name for f in fields(BuildTiming)]

_PATH_RE = re.compile(r'pr-logs/pull/[^"]+/\d+')
_PAGINATION_RE = re.compile(r"buildId=(\d+)")


def scrape_build_paths(
    job_name: str, count: int
) -> list[str]:
    """Scrape Prow history pages for GCS paths."""
    paths: list[str] = []
    url = PROW_HISTORY.format(
        bucket=GCS_BUCKET, job_name=job_name
    )

    seen: set[str] = set()
    while len(paths) < count:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text

        page_paths = _PATH_RE.findall(html)
        if not page_paths:
            break
        added = 0
        for p in page_paths:
            if p not in seen:
                seen.add(p)
                paths.append(p)
                added += 1
            if len(paths) >= count:
                break
        if added == 0:
            break

        m = _PAGINATION_RE.search(html)
        if not m:
            break
        url = PROW_HISTORY.format(
            bucket=GCS_BUCKET, job_name=job_name
        ) + f"?buildId={m.group(1)}"
        time.sleep(0.1)

    return paths[:count]


def _gcs_json(path: str) -> Optional[dict]:
    """Fetch a JSON file from GCS."""
    try:
        resp = SESSION.get(f"{GCS_BASE}/{path}", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _gcs_text(path: str) -> Optional[str]:
    """Fetch a text file from GCS."""
    try:
        resp = SESSION.get(
            f"{GCS_BASE}/{path}", timeout=60
        )
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def _read_or_fetch_log(
    gcs_path: str, cache_key: str
) -> Optional[str]:
    """Read log from disk cache or fetch from GCS.

    cache_key is a relative path like
    ``e2e-predictor/2034907249561833472.log``.
    """
    if _LOGS_DIR is not None:
        local = _LOGS_DIR / cache_key
        if local.exists():
            return local.read_text()
    text = _gcs_text(gcs_path)
    if text and _LOGS_DIR is not None:
        local = _LOGS_DIR / cache_key
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(text)
    return text


# Pattern tiers, checked in order.  First match wins.
#
# Tier 1 -- platform (out-of-domain, CI infrastructure)
# Tier 2 -- test (test code failures)
# Tier 3 -- setup (in-domain component installation)
# Tier 4 -- ambiguous (low-confidence, last resort)
#
# This ordering ensures that unambiguous platform
# failures are caught first, then clear test failures
# (so `connection refused` in diagnostic output does
# not mask `FAILED test_*`), then in-domain setup
# issues.

_PLATFORM_PATTERNS: list[
    tuple[str, list[re.Pattern]]
] = [
    ("platform:provision", [
        re.compile(
            r"timed out.*hostedclusters/", re.I
        ),
        re.compile(
            r"timed out.*clusterversions/", re.I
        ),
        re.compile(r"status code: 400"),
        re.compile(
            r"hostedcluster.*not found", re.I
        ),
    ]),
    ("platform:ci-infra", [
        re.compile(r"jq: error"),
        re.compile(
            r"executable file.*not found", re.I
        ),
    ]),
    ("platform:cluster-health", [
        re.compile(r"etcd leader changed"),
        re.compile(
            r"cluster operator.*degraded", re.I
        ),
        re.compile(r"node.*NotReady"),
        re.compile(
            r"nodes are not ready", re.I
        ),
    ]),
    ("platform:resource", [
        re.compile(r"Insufficient cpu", re.I),
        re.compile(r"Insufficient memory", re.I),
        re.compile(r"OOMKilled"),
        re.compile(r"FailedScheduling"),
        re.compile(r"Evicted"),
    ]),
]

_TEST_PATTERNS: list[
    tuple[str, list[re.Pattern]]
] = [
    ("test:collection", [
        re.compile(r"ERROR collecting"),
        re.compile(r"ModuleNotFoundError"),
        re.compile(r"ImportError"),
        re.compile(
            r"fixture '.*' not found", re.I
        ),
    ]),
    ("test:assertion", [
        re.compile(r"FAILED .*::test_"),
        re.compile(r"FAILED test_"),
        re.compile(r"\d+ failed.*\d+ passed"),
        re.compile(r"AssertionError"),
    ]),
]

_SETUP_PATTERNS: list[
    tuple[str, list[re.Pattern]]
] = [
    ("setup:install", [
        re.compile(
            r"Timed out.*waiting for CRD", re.I
        ),
        re.compile(
            r"failed calling webhook", re.I
        ),
        re.compile(
            r"Liveness probe failed.*"
            r"context dead", re.I
        ),
        re.compile(
            r"Readiness probe failed.*"
            r"connection refused", re.I
        ),
        re.compile(
            r"MountVolume\.SetUp failed", re.I
        ),
        re.compile(
            r"timed out.*waiting.*"
            r"(kuadrant|authorino)", re.I
        ),
    ]),
    ("setup:config", [
        re.compile(
            r"no objects passed to apply", re.I
        ),
        re.compile(
            r"lstat.*no such file or directory",
            re.I,
        ),
        re.compile(
            r"accumulating resources.*"
            r"evalsymlink failure", re.I
        ),
    ]),
]

_AMBIGUOUS_PATTERNS: list[
    tuple[str, list[re.Pattern]]
] = [
    ("platform:timeout", [
        re.compile(r"timed out.*waiting", re.I),
        re.compile(r"TimeoutError", re.I),
        re.compile(r"deadline exceeded", re.I),
        re.compile(
            r"did not become ready in time",
            re.I,
        ),
    ]),
    ("platform:image-pull", [
        re.compile(r"ImagePullBackOff", re.I),
        re.compile(r"ErrImagePull", re.I),
        re.compile(
            r"Failed to pull image", re.I
        ),
    ]),
]

_ALL_TIERS = [
    _PLATFORM_PATTERNS,
    _TEST_PATTERNS,
    _SETUP_PATTERNS,
    _AMBIGUOUS_PATTERNS,
]


def classify_failure(
    log_text: str,
) -> tuple[str, str]:
    """Classify a failure from its build log.

    Returns (category, comma-separated signals).
    Checks tiers in order: platform -> test ->
    setup -> ambiguous.  First match wins.
    """
    for tier in _ALL_TIERS:
        for cat, patterns in tier:
            hits = [
                p.pattern for p in patterns
                if p.search(log_text)
            ]
            if hits:
                return cat, ", ".join(hits)
    return "test:other", ""


def _gcs_list_prefixes(prefix: str) -> list[str]:
    """List sub-directory prefixes via GCS JSON API."""
    try:
        resp = SESSION.get(
            GCS_API,
            params={"prefix": prefix, "delimiter": "/"},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("prefixes", [])
    except Exception:
        pass
    return []


def _extract_build_id(gcs_path: str) -> str:
    return gcs_path.rstrip("/").rsplit("/", 1)[-1]


def _extract_pr(gcs_path: str) -> str:
    parts = gcs_path.split("/")
    try:
        idx = parts.index("pull")
        return parts[idx + 2]
    except (ValueError, IndexError):
        return ""


def collect_build_timing(
    gcs_path: str,
    test_as_name: str,
    skip_logs: bool = False,
) -> Optional[BuildTiming]:
    """Collect timing data for a single build."""
    bt = BuildTiming(
        build_id=_extract_build_id(gcs_path),
        pr_number=_extract_pr(gcs_path),
    )

    started = _gcs_json(f"{gcs_path}/started.json")
    finished = _gcs_json(f"{gcs_path}/finished.json")
    if not started or not finished:
        return None

    bt.job_start = started.get("timestamp")
    bt.job_end = finished.get("timestamp")
    bt.result = finished.get("result", "UNKNOWN")

    if bt.job_start and bt.job_end:
        bt.total_s = bt.job_end - bt.job_start

    artifact_pfx = (
        f"{gcs_path}/artifacts/{test_as_name}/"
    )
    step_dirs = _gcs_list_prefixes(artifact_pfx)
    step_names = {
        p.rstrip("/").rsplit("/", 1)[-1]
        for p in step_dirs
    }

    test_candidates = step_names - KNOWN_STEPS
    if test_candidates:
        bt.test_step_name = sorted(test_candidates)[0]

    for step in step_names:
        fin = _gcs_json(
            f"{artifact_pfx}{step}/finished.json"
        )
        if not fin:
            continue
        ts = fin.get("timestamp")
        if not ts:
            continue

        if step == (
            "hypershift-hostedcluster"
            "-create-hostedcluster"
        ):
            bt.create_end = ts
        elif step == (
            "hypershift-hostedcluster"
            "-create-wait-for-olm"
        ):
            bt.olm_end = ts
        elif step == (
            "hypershift-hostedcluster"
            "-destroy-hostedcluster"
        ):
            bt.destroy_end = ts
        elif step == bt.test_step_name:
            bt.test_end = ts

    test_start = bt.olm_end or bt.create_end
    if bt.create_end and bt.job_start:
        bt.pre_test_s = bt.create_end - bt.job_start
    if bt.test_end and test_start:
        bt.test_s = bt.test_end - test_start
    if bt.test_end and bt.job_end:
        bt.post_s = bt.job_end - bt.test_end

    if bt.result == "FAILURE" and not skip_logs:
        _classify_build(
            bt, artifact_pfx, step_names,
            test_as_name,
        )

    return bt


def _classify_build(
    bt: BuildTiming,
    artifact_pfx: str,
    step_names: set[str],
    test_as_name: str,
) -> None:
    """Fetch build log and classify the failure."""
    if not bt.test_step_name or bt.test_s is None:
        bt.failure_category = "platform:provision"
        log_step = _pick_failed_pre_step(
            artifact_pfx, step_names
        )
        if log_step:
            gcs_path = (
                f"{artifact_pfx}{log_step}"
                "/build-log.txt"
            )
            cache_key = (
                f"{test_as_name}/"
                f"{bt.build_id}.pre-{log_step}.log"
            )
            log = _read_or_fetch_log(
                gcs_path, cache_key
            )
            if log:
                bt.log_fetched = True
                cat, sig = classify_failure(log)
                if not cat.startswith("test:"):
                    bt.failure_category = cat
                    bt.failure_signals = sig
        return

    gcs_path = (
        f"{artifact_pfx}{bt.test_step_name}"
        "/build-log.txt"
    )
    cache_key = (
        f"{test_as_name}/{bt.build_id}.log"
    )
    log = _read_or_fetch_log(gcs_path, cache_key)
    if not log:
        bt.failure_category = "unknown:no-log"
        return
    bt.log_fetched = True
    cat, sig = classify_failure(log)
    bt.failure_category = cat
    bt.failure_signals = sig


PRE_STEPS_PRIORITY = [
    "hypershift-hostedcluster-create-wait-for-olm",
    "hypershift-hostedcluster-create-hostedcluster",
    "openshift-cluster-bot-rbac",
]


def _pick_failed_pre_step(
    artifact_pfx: str,
    step_names: set[str],
) -> Optional[str]:
    """Find the pre-step most likely to have failed."""
    for step in PRE_STEPS_PRIORITY:
        if step not in step_names:
            continue
        fin = _gcs_json(
            f"{artifact_pfx}{step}/finished.json"
        )
        if fin and fin.get("result") != "SUCCESS":
            return step
    for step in PRE_STEPS_PRIORITY:
        if step in step_names:
            return step
    return None


def write_csv(rows: list[BuildTiming], path: Path):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(
                {k: getattr(r, k) for k in CSV_FIELDS}
            )


def _fmt(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _pct_row(values: list[int], label: str) -> str:
    if not values:
        return f"| {label} | -- | -- | -- | -- | -- |"
    p50 = statistics.median(values)
    if len(values) >= 2:
        p90 = statistics.quantiles(values, n=10)[-1]
        p99 = statistics.quantiles(values, n=100)[-1]
    else:
        p90 = p99 = p50
    mn, mx = min(values), max(values)
    return (
        f"| {label} "
        f"| {_fmt(p50)} | {_fmt(p90)} "
        f"| {_fmt(p99)} | {_fmt(mn)} | {_fmt(mx)} |"
    )


def write_summary(
    rows: list[BuildTiming], path: Path
) -> None:
    lines: list[str] = []
    types = sorted({r.job_type for r in rows})
    lines.append("# CI Timing Data Summary\n")
    lines.append(
        f"Collected {len(rows)} builds "
        f"across {len(types)} job types.\n"
    )

    for jt in types:
        jt_rows = [r for r in rows if r.job_type == jt]
        done = [
            r for r in jt_rows
            if r.total_s is not None
            and r.result != "ABORTED"
        ]
        ok = sum(
            1 for r in done
            if r.result == "SUCCESS"
        )
        short = jt.rsplit("-", 1)[-1]
        lines.append(f"\n## {short} ({jt})\n")
        lines.append(
            f"- Builds collected: {len(jt_rows)}"
        )
        lines.append(
            f"- Completed (non-aborted): {len(done)}"
        )
        if done:
            pct = 100 * ok / len(done)
            lines.append(
                f"- Success rate: "
                f"{ok}/{len(done)} ({pct:.0f}%)"
            )
        _append_table(lines, done)

    lines.append("\n## Aggregate (all job types)\n")
    done = [
        r for r in rows
        if r.total_s is not None
        and r.result != "ABORTED"
    ]
    ok = sum(1 for r in done if r.result == "SUCCESS")
    lines.append(f"- Total completed: {len(done)}")
    if done:
        pct = 100 * ok / len(done)
        lines.append(
            f"- Overall success rate: "
            f"{ok}/{len(done)} ({pct:.0f}%)"
        )
    _append_table(lines, done)

    _append_classification(lines, rows, types)
    path.write_text("\n".join(lines))


def _append_table(
    lines: list[str], done: list[BuildTiming]
) -> None:
    lines.append("")
    lines.append(
        "| Phase | Median | P90 | P99 "
        "| Min | Max |"
    )
    lines.append("|---|---|---|---|---|---|")
    lines.append(_pct_row(
        [r.total_s for r in done if r.total_s],
        "Total job",
    ))
    lines.append(_pct_row(
        [r.pre_test_s for r in done if r.pre_test_s],
        "Pre-test (ci-op + provision)",
    ))
    lines.append(_pct_row(
        [r.test_s for r in done if r.test_s],
        "Test execution",
    ))
    lines.append(_pct_row(
        [r.post_s for r in done if r.post_s],
        "Post-steps (gather + destroy)",
    ))
    lines.append("")


def _append_classification(
    lines: list[str],
    rows: list[BuildTiming],
    types: list[str],
) -> None:
    """Add failure classification breakdown."""
    failed = [r for r in rows if r.result == "FAILURE"]
    if not failed:
        return

    has_cats = any(r.failure_category for r in failed)
    if not has_cats:
        return

    lines.append("\n---\n")
    lines.append("# Failure Classification\n")
    lines.append(
        f"Classified {len(failed)} FAILURE builds "
        "by build-log pattern matching.\n"
    )

    _class_table(lines, failed, "All job types")

    platform = sum(
        1 for r in failed
        if r.failure_category.startswith(
            "platform:"
        )
    )
    setup = sum(
        1 for r in failed
        if r.failure_category.startswith("setup:")
    )
    test = sum(
        1 for r in failed
        if r.failure_category.startswith("test:")
    )
    other = len(failed) - platform - setup - test
    lines.append(
        f"**Platform (out-of-domain): {platform} "
        f"({_pct(platform, failed)})**  "
    )
    lines.append(
        f"**Setup (in-domain infra): {setup} "
        f"({_pct(setup, failed)})**  "
    )
    lines.append(
        f"**Test: {test} "
        f"({_pct(test, failed)})**  "
    )
    if other:
        lines.append(
            f"**Unknown/no-log: {other} "
            f"({_pct(other, failed)})**"
        )
    lines.append("")

    kserve_fail = [
        r for r in failed if "kserve-master" in r.job_type
    ]
    omc_fail = [
        r for r in failed
        if "odh-model-controller" in r.job_type
    ]
    if kserve_fail:
        _class_table(
            lines, kserve_fail, "kserve jobs"
        )
    if omc_fail:
        _class_table(
            lines, omc_fail, "odh-model-controller jobs"
        )

    for jt in types:
        jt_fail = [
            r for r in failed if r.job_type == jt
        ]
        if not jt_fail:
            continue
        short = jt.rsplit("-", 1)[-1]
        _class_table(lines, jt_fail, short)


def _pct(n: int, total: list) -> str:
    if not total:
        return "0%"
    return f"{100 * n / len(total):.0f}%"


def _class_table(
    lines: list[str],
    failed: list[BuildTiming],
    label: str,
) -> None:
    from collections import Counter
    cats = Counter(
        r.failure_category or "unclassified"
        for r in failed
    )
    lines.append(f"\n### {label}\n")
    lines.append("| Category | Count | % |")
    lines.append("|---|---|---|")
    for cat, count in cats.most_common():
        pct = 100 * count / len(failed)
        lines.append(
            f"| {cat} | {count} | {pct:.0f}% |"
        )
    lines.append("")


def _collect_job_type(
    job_name: str,
    test_as_name: str,
    count: int,
    skip_logs: bool = False,
) -> list[BuildTiming]:
    print(
        f"  Enumerating builds for {job_name}...",
        file=sys.stderr,
    )
    paths = scrape_build_paths(job_name, count)
    print(
        f"  Found {len(paths)} builds, "
        "collecting timing...",
        file=sys.stderr,
    )
    results: list[BuildTiming] = []

    def _do(p: str) -> Optional[BuildTiming]:
        bt = collect_build_timing(
            p, test_as_name, skip_logs
        )
        if bt:
            bt.job_type = job_name
        return bt

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_do, p): p for p in paths}
        for fut in as_completed(futs):
            bt = fut.result()
            if bt:
                results.append(bt)
            else:
                bid = _extract_build_id(futs[fut])
                print(
                    f"    Skipped {bid} "
                    "(missing artifacts)",
                    file=sys.stderr,
                )

    results.sort(
        key=lambda r: r.job_start or 0, reverse=True
    )
    print(
        f"  Collected {len(results)} builds "
        f"for {job_name}",
        file=sys.stderr,
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect CI timing data from Prow/GCS"
    )
    parser.add_argument(
        "--jobs", type=int, default=100,
        help="Builds per job type (default: 100)",
    )
    parser.add_argument(
        "--output-dir", type=str, default=".",
        help="Output directory for CSV and summary",
    )
    parser.add_argument(
        "--job-types", type=str, default=None,
        help="Comma-separated short names (default: all)",
    )
    parser.add_argument(
        "--skip-logs", action="store_true",
        help="Skip build-log fetching (timing only)",
    )
    parser.add_argument(
        "--logs-dir", type=str, default="./logs",
        help="Directory for cached build logs "
        "(default: ./logs)",
    )
    parser.add_argument(
        "--no-save-logs", action="store_true",
        help="Do not save/cache build logs to disk",
    )
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    global _LOGS_DIR
    if not args.no_save_logs and not args.skip_logs:
        _LOGS_DIR = Path(args.logs_dir)
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    job_filter = None
    if args.job_types:
        job_filter = set(args.job_types.split(","))

    all_rows: list[BuildTiming] = []
    for job_name, test_as_name in JOB_TYPES.items():
        if job_filter and test_as_name not in job_filter:
            continue
        print(f"\n[{test_as_name}]", file=sys.stderr)
        rows = _collect_job_type(
            job_name, test_as_name, args.jobs,
            args.skip_logs,
        )
        all_rows.extend(rows)

    csv_path = out / "ci_timing_data.csv"
    write_csv(all_rows, csv_path)
    print(
        f"\nWrote {len(all_rows)} rows to {csv_path}",
        file=sys.stderr,
    )

    summary_path = out / "ci_timing_summary.md"
    write_summary(all_rows, summary_path)
    print(
        f"Wrote summary to {summary_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
